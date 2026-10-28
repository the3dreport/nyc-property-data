"""Owner identity consolidation + cross-NYC portfolio search."""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

import httpx

from . import cache
from .socrata import (
    BOROUGH_NAMES,
    DATASETS,
    fetch_acris,
    fetch_hpd_registrations_and_contacts,
    fetch_pluto,
    normalize_bbl,
    socrata_query,
    split_bbl,
)

ENTITY_STOPWORDS = re.compile(
    r"\b(LLC|L\.?L\.?C\.?|INC|INCORPORATED|CORP|CORPORATION|LP|L\.?P\.?|"
    r"LLP|LTD|LIMITED|CO|COMPANY|THE|TRUST|TR|N\.?A\.?)\b",
    re.I,
)
PUNCT = re.compile(r"[^\w\s]")
SPACE = re.compile(r"\s+")

HPD_OWNER_TYPES = {
    "CorporateOwner",
    "IndividualOwner",
    "HeadOfficer",
    "Officer",
    "Agent",
    "SiteManager",
    "JointOwner",
}

# Keep Socrata calls bounded
PLUTO_LIMIT = 40
ACRIS_PARTY_LIMIT = 30
HPD_CONTACT_LIMIT = 30
ACRIS_LEGAL_CHUNK = 20
PORTFOLIO_MAX = 60
CACHE_TTL = 600


def soql_escape(value: str) -> str:
    return value.replace("'", "''")


def normalize_owner_name(name: Optional[str]) -> str:
    if not name:
        return ""
    s = name.upper().strip()
    s = PUNCT.sub(" ", s)
    s = ENTITY_STOPWORDS.sub(" ", s)
    s = SPACE.sub(" ", s).strip()
    return s


def normalize_address(parts: list[Optional[str]]) -> str:
    raw = " ".join(p for p in parts if p)
    s = raw.upper().strip()
    s = PUNCT.sub(" ", s)
    s = SPACE.sub(" ", s).strip()
    # Drop apartment / floor noise for matching
    s = re.sub(r"\b(\d+(ST|ND|RD|TH)?\s*)?(FL|FLOOR|APT|SUITE|STE|#)\b.*$", "", s).strip()
    return s



GENERIC_OWNER_FRAGMENTS = (
    "HOUSING DEVELOPMENT FUND",
    "HOUSING AUTHORITY",
    "CITY OF NEW YORK",
    "NYC DEPARTMENT",
    "DEPARTMENT OF",
    "UNITED STATES",
    "PEOPLE OF THE STATE",
    "NEW YORK CITY",
)


def is_generic_owner(norm: str) -> bool:
    if not norm or len(norm) < 3:
        return True
    u = norm.upper()
    return any(g in u for g in GENERIC_OWNER_FRAGMENTS)

def name_tokens(norm: str) -> set[str]:
    return {t for t in norm.split() if len(t) > 1}


def fuzzy_name_score(a: str, b: str) -> float:
    """Simple token Jaccard; 1.0 exact normalized, ~0.5+ treated as fuzzy."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def confidence_label(score: float, via_address: bool = False) -> str:
    if via_address and score < 0.85:
        return "shared_address"
    if score >= 0.99:
        return "exact"
    if score >= 0.5:
        return "fuzzy"
    if via_address:
        return "shared_address"
    return "fuzzy"


def bbl_from_pluto_row(row: dict) -> Optional[str]:
    raw = row.get("bbl")
    if raw is None:
        return None
    try:
        return normalize_bbl(str(raw).split(".")[0])
    except ValueError:
        return None


def bbl_from_boro_block_lot(boro: Any, block: Any, lot: Any) -> Optional[str]:
    try:
        b = str(int(str(boro).strip()))
        blk = str(int(str(block).strip())).zfill(5)
        lt = str(int(str(lot).strip())).zfill(4)
        return normalize_bbl(b + blk + lt)
    except Exception:
        return None


async def _pluto_by_owner(
    client: httpx.AsyncClient, raw_name: str, norm: str
) -> list[dict]:
    hits: list[dict] = []
    # Prefer exact upper match on full PLUTO string, then LIKE on core tokens
    queries = []
    if raw_name:
        queries.append(f"upper(ownername)='{soql_escape(raw_name.upper())}'")
    if norm and len(norm) >= 4 and not is_generic_owner(norm):
        # Use leading token phrase for LIKE to stay selective
        like = soql_escape(norm[:48])
        queries.append(f"upper(ownername) like '%{like}%'")
    elif norm and is_generic_owner(norm) and raw_name:
        # Exact-only for very common institutional names
        pass

    seen = set()
    for where in queries:
        try:
            rows = await socrata_query(
                DATASETS["pluto"],
                {
                    "$where": where,
                    "$select": "bbl,address,borough,ownername,zipcode,latitude,longitude",
                    "$limit": str(PLUTO_LIMIT),
                },
                client,
            )
        except Exception:
            continue
        for row in rows:
            bbl = bbl_from_pluto_row(row)
            if not bbl or bbl in seen:
                continue
            seen.add(bbl)
            score = fuzzy_name_score(norm, normalize_owner_name(row.get("ownername")))
            if score < 0.45 and raw_name and row.get("ownername", "").upper() != raw_name.upper():
                continue
            hits.append(
                {
                    "bbl": bbl,
                    "address": row.get("address"),
                    "borough": BOROUGH_NAMES.get(
                        str(bbl[0]), row.get("borough")
                    ),
                    "matched_name": row.get("ownername"),
                    "match_source": "PLUTO ownername",
                    "confidence": confidence_label(score if score else 1.0),
                    "confidence_score": round(score or 1.0, 2),
                }
            )
        if len(hits) >= PLUTO_LIMIT:
            break
    return hits


async def _acris_grantee_portfolio(
    client: httpx.AsyncClient, raw_name: str, norm: str
) -> list[dict]:
    if not raw_name and not norm:
        return []
    # Search party_type 2 (typically grantee) by name
    clauses = []
    if raw_name:
        clauses.append(f"upper(name)='{soql_escape(raw_name.upper())}'")
        # Also try comma-flipped person form: "FEUER WENDY" -> "FEUER, WENDY%"
        parts = raw_name.upper().replace(",", " ").split()
        if len(parts) == 2:
            clauses.append(f"upper(name) like '{soql_escape(parts[0] + ', ' + parts[1])}%'")
    # LIKE only for longer org names (avoid huge person-name scans)
    if norm and len(norm) >= 8 and len(norm.split()) >= 3 and not is_generic_owner(norm):
        clauses.append(f"upper(name) like '%{soql_escape(norm[:40])}%'")
    parties: list[dict] = []
    for where_extra in clauses:
        where = f"party_type='2' AND {where_extra}"
        try:
            rows = await socrata_query(
                DATASETS["acris_parties"],
                {"$where": where, "$limit": str(ACRIS_PARTY_LIMIT)},
                client,
            )
            parties.extend(rows)
        except Exception:
            continue
        if parties:
            break

    # Keep names that fuzzy-match our identity
    filtered = []
    for p in parties:
        score = fuzzy_name_score(norm, normalize_owner_name(p.get("name")))
        if score >= 0.5 or (raw_name and (p.get("name") or "").upper() == raw_name.upper()):
            filtered.append((p, score if score else 1.0))
    if not filtered:
        return []

    doc_ids = list({p["document_id"] for p, _ in filtered if p.get("document_id")})[:ACRIS_PARTY_LIMIT]
    score_by_doc = {}
    name_by_doc = {}
    for p, sc in filtered:
        did = p.get("document_id")
        if not did:
            continue
        score_by_doc[did] = max(sc, score_by_doc.get(did, 0))
        name_by_doc[did] = p.get("name")

    # Filter to DEED-like docs when possible
    masters = []
    for i in range(0, len(doc_ids), ACRIS_LEGAL_CHUNK):
        chunk = doc_ids[i : i + ACRIS_LEGAL_CHUNK]
        id_list = ",".join(f"'{d}'" for d in chunk)
        try:
            masters.extend(
                await socrata_query(
                    DATASETS["acris_master"],
                    {
                        "$where": f"document_id in ({id_list})",
                        "$select": "document_id,doc_type,document_date",
                        "$limit": str(ACRIS_LEGAL_CHUNK),
                    },
                    client,
                )
            )
        except Exception:
            continue
    deed_types = {"DEED", "DEEDO", "REEB", "CORRD", "RPTT & RET"}
    deed_docs = {
        m["document_id"]
        for m in masters
        if (m.get("doc_type") or "").upper() in deed_types or "DEED" in (m.get("doc_type") or "").upper()
    }
    # If none flagged as deeds, still use all (name match on party_type 2)
    use_docs = list(deed_docs) if deed_docs else doc_ids

    legals = []
    for i in range(0, len(use_docs), ACRIS_LEGAL_CHUNK):
        chunk = use_docs[i : i + ACRIS_LEGAL_CHUNK]
        id_list = ",".join(f"'{d}'" for d in chunk)
        try:
            legals.extend(
                await socrata_query(
                    DATASETS["acris_legals"],
                    {
                        "$where": f"document_id in ({id_list})",
                        "$select": "document_id,borough,block,lot,street_number,street_name",
                        "$limit": "100",
                    },
                    client,
                )
            )
        except Exception:
            continue

    hits = []
    seen = set()
    for row in legals:
        bbl = bbl_from_boro_block_lot(row.get("borough"), row.get("block"), row.get("lot"))
        if not bbl or bbl in seen:
            continue
        seen.add(bbl)
        did = row.get("document_id")
        addr = " ".join(
            x for x in [row.get("street_number"), row.get("street_name")] if x
        )
        hits.append(
            {
                "bbl": bbl,
                "address": addr or None,
                "borough": BOROUGH_NAMES.get(str(row.get("borough"))),
                "matched_name": name_by_doc.get(did),
                "match_source": "ACRIS deed grantee",
                "confidence": confidence_label(score_by_doc.get(did, 0.7)),
                "confidence_score": round(score_by_doc.get(did, 0.7), 2),
            }
        )
    return hits


async def _hpd_portfolio(
    client: httpx.AsyncClient,
    names: list[str],
    norms: list[str],
    business_addrs: list[str],
) -> list[dict]:
    contacts: list[dict] = []
    clauses = []
    for raw in names:
        if not raw:
            continue
        u = soql_escape(raw.upper())
        clauses.append(f"upper(corporationname)='{u}'")
        # Person: first+last exact is hard; use last name LIKE carefully
    for norm in norms:
        if len(norm) < 4:
            continue
        like = soql_escape(norm[:40])
        clauses.append(f"upper(corporationname) like '%{like}%'")
        # Individual: match concatenated first+last roughly via last token
        tokens = norm.split()
        if len(tokens) >= 2:
            last = soql_escape(tokens[-1])
            first = soql_escape(tokens[0])
            clauses.append(
                f"(upper(lastname)='{last}' AND upper(firstname) like '{first}%')"
            )

    for addr in business_addrs:
        if len(addr) < 8:
            continue
        # Match street number + street name
        parts = addr.split()
        if len(parts) >= 2 and parts[0].isdigit():
            hn, st = soql_escape(parts[0]), soql_escape(" ".join(parts[1:3]))
            clauses.append(
                f"(businesshousenumber='{hn}' AND upper(businessstreetname) like '{st}%')"
            )

    # Deduplicate clauses, cap queries
    seen_c = set()
    uniq_clauses = []
    for c in clauses:
        if c not in seen_c:
            seen_c.add(c)
            uniq_clauses.append(c)
    uniq_clauses = uniq_clauses[:6]

    for clause in uniq_clauses:
        try:
            rows = await socrata_query(
                DATASETS["hpd_contacts"],
                {"$where": clause, "$limit": str(HPD_CONTACT_LIMIT)},
                client,
            )
            contacts.extend(rows)
        except Exception:
            continue

    # Filter to owner-ish types
    contacts = [
        c
        for c in contacts
        if (c.get("type") in HPD_OWNER_TYPES) or not c.get("type")
    ]
    if not contacts:
        return []

    reg_ids = list({c["registrationid"] for c in contacts if c.get("registrationid")})[:40]
    regs = []
    for i in range(0, len(reg_ids), 20):
        chunk = reg_ids[i : i + 20]
        id_list = ",".join(f"'{r}'" for r in chunk)
        try:
            regs.extend(
                await socrata_query(
                    DATASETS["hpd_registrations"],
                    {
                        "$where": f"registrationid in ({id_list})",
                        "$limit": "40",
                    },
                    client,
                )
            )
        except Exception:
            continue

    reg_by_id = {r["registrationid"]: r for r in regs if r.get("registrationid")}
    # Map registrationid -> best contact match meta
    contact_meta: dict[str, dict] = {}
    norm_set = [n for n in norms if n]
    addr_set = [a for a in business_addrs if a]

    for c in contacts:
        rid = c.get("registrationid")
        if not rid:
            continue
        display = c.get("corporationname") or " ".join(
            x for x in [c.get("firstname"), c.get("lastname")] if x
        )
        cnorm = normalize_owner_name(display)
        score = max((fuzzy_name_score(cnorm, n) for n in norm_set), default=0.0)
        caddr = normalize_address(
            [
                c.get("businesshousenumber"),
                c.get("businessstreetname"),
                c.get("businesscity"),
            ]
        )
        via_addr = any(
            caddr and a and (caddr == a or caddr.startswith(a[:12]) or a.startswith(caddr[:12]))
            for a in addr_set
        )
        prev = contact_meta.get(rid)
        if not prev or score > prev["score"] or (via_addr and not prev.get("via_addr")):
            contact_meta[rid] = {
                "score": score,
                "via_addr": via_addr,
                "name": display,
                "type": c.get("type"),
            }

    hits = []
    seen = set()
    for rid, reg in reg_by_id.items():
        bbl = bbl_from_boro_block_lot(reg.get("boroid"), reg.get("block"), reg.get("lot"))
        if not bbl or bbl in seen:
            continue
        seen.add(bbl)
        meta = contact_meta.get(rid, {"score": 0.5, "via_addr": False, "name": None})
        conf = confidence_label(meta["score"], via_address=meta.get("via_addr"))
        addr = " ".join(
            x for x in [reg.get("housenumber"), reg.get("streetname")] if x
        )
        hits.append(
            {
                "bbl": bbl,
                "address": addr or None,
                "borough": reg.get("boro") or BOROUGH_NAMES.get(str(reg.get("boroid"))),
                "matched_name": meta.get("name"),
                "match_source": f"HPD contact ({meta.get('type') or 'unknown'})",
                "confidence": conf,
                "confidence_score": round(meta.get("score") or (0.6 if meta.get("via_addr") else 0.5), 2),
            }
        )
    return hits


def merge_portfolio(current_bbl: str, groups: list[list[dict]]) -> list[dict]:
    by_bbl: dict[str, dict] = {}
    rank = {"exact": 3, "fuzzy": 2, "shared_address": 1}

    for group in groups:
        for hit in group:
            bbl = hit.get("bbl")
            if not bbl:
                continue
            sources = [hit.get("match_source")]
            if bbl in by_bbl:
                existing = by_bbl[bbl]
                sources = list(
                    dict.fromkeys(existing.get("match_sources", []) + sources)
                )
                # Keep best confidence
                if rank.get(hit["confidence"], 0) > rank.get(existing["confidence"], 0):
                    existing["confidence"] = hit["confidence"]
                    existing["confidence_score"] = hit.get("confidence_score")
                    existing["matched_name"] = hit.get("matched_name") or existing.get(
                        "matched_name"
                    )
                if not existing.get("address") and hit.get("address"):
                    existing["address"] = hit["address"]
                if not existing.get("borough") and hit.get("borough"):
                    existing["borough"] = hit["borough"]
                existing["match_sources"] = sources
                existing["match_source"] = " · ".join(sources)
                existing["is_current"] = bbl == current_bbl
            else:
                by_bbl[bbl] = {
                    **hit,
                    "match_sources": sources,
                    "match_source": hit.get("match_source"),
                    "is_current": bbl == current_bbl,
                    "url": f"/property?bbl={bbl}",
                }

    items = list(by_bbl.values())
    items.sort(
        key=lambda x: (
            0 if x.get("is_current") else 1,
            -rank.get(x.get("confidence"), 0),
            x.get("borough") or "",
            x.get("address") or "",
        )
    )
    return items[:PORTFOLIO_MAX]



async def ensure_deed_grantee(
    client: httpx.AsyncClient, boro: str, block: str, lot: str, identities: list[dict]
) -> list[dict]:
    """If no deed grantee yet, pull a few DEED docs for this lot directly."""
    if any(i.get("source") == "ACRIS" for i in identities):
        return identities
    try:
        legals = await socrata_query(
            DATASETS["acris_legals"],
            {"borough": boro, "block": block, "lot": lot, "$limit": "30", "$select": "document_id"},
            client,
        )
        doc_ids = [r["document_id"] for r in legals if r.get("document_id")][:30]
        if not doc_ids:
            return identities
        id_list = ",".join(f"'{d}'" for d in doc_ids)
        masters = await socrata_query(
            DATASETS["acris_master"],
            {
                "$where": f"document_id in ({id_list}) AND (upper(doc_type) like '%DEED%' OR doc_type='REEB')",
                "$order": "document_date DESC",
                "$limit": "3",
            },
            client,
        )
        if not masters:
            return identities
        m = masters[0]
        parties = await socrata_query(
            DATASETS["acris_parties"],
            {"$where": f"document_id='{m['document_id']}' AND party_type='2'", "$limit": "5"},
            client,
        )
        fake_acris = {
            "records": [
                {
                    "document_id": m.get("document_id"),
                    "doc_type": m.get("doc_type"),
                    "document_date": m.get("document_date"),
                    "parties": parties,
                }
            ]
        }
        extra = extract_identities(None, fake_acris, {"records": []})
        # merge
        names = {normalize_owner_name(i["name"]) for i in identities}
        for e in extra:
            if e["normalized"] not in names:
                identities.append(e)
    except Exception:
        pass
    return identities


def extract_identities(
    pluto_row: Optional[dict],
    acris_section: dict,
    hpd_contacts_section: dict,
) -> list[dict]:
    identities = []
    seen = set()

    def add(name: str, role: str, source: str, address: Optional[str] = None, extra: Optional[dict] = None):
        if not name or not name.strip():
            return
        key = (normalize_owner_name(name), normalize_address([address]) if address else "")
        if key in seen and not address:
            return
        seen.add(key)
        identities.append(
            {
                "name": name.strip(),
                "normalized": normalize_owner_name(name),
                "role": role,
                "source": source,
                "address": address,
                **(extra or {}),
            }
        )

    if pluto_row and pluto_row.get("ownername"):
        add(pluto_row["ownername"], "Tax lot owner", "PLUTO")

    # Latest DEED grantee (party_type 2)
    deeds = [
        r
        for r in (acris_section.get("records") or [])
        if "DEED" in (r.get("doc_type") or "").upper()
        or (r.get("doc_type") or "").upper() in {"REEB", "CORRD"}
    ]
    # records already sorted newest-first
    for deed in deeds[:3]:
        parties = deed.get("parties") or []
        grantees = [p for p in parties if str(p.get("party_type")) == "2"]
        if not grantees:
            # fallback: if only one party list, skip
            continue
        for g in grantees:
            addr = ", ".join(
                x
                for x in [
                    g.get("address_1"),
                    g.get("city"),
                    g.get("state"),
                    g.get("zip"),
                ]
                if x
            )
            add(
                g.get("name") or "",
                "ACRIS deed grantee",
                "ACRIS",
                addr or None,
                {
                    "document_id": deed.get("document_id"),
                    "document_date": deed.get("document_date"),
                    "doc_type": deed.get("doc_type"),
                },
            )
        break  # only latest deed

    for c in hpd_contacts_section.get("records") or []:
        ctype = c.get("type") or ""
        if ctype not in HPD_OWNER_TYPES:
            continue
        name = c.get("corporationname") or " ".join(
            x for x in [c.get("firstname"), c.get("lastname")] if x
        )
        addr = ", ".join(
            x
            for x in [
                c.get("businesshousenumber"),
                c.get("businessstreetname"),
                c.get("businessapartment"),
                c.get("businesscity"),
                c.get("businessstate"),
                c.get("businesszip"),
            ]
            if x
        )
        role = {
            "CorporateOwner": "Corporate owner",
            "IndividualOwner": "Individual owner",
            "HeadOfficer": "Head officer",
            "Officer": "Officer",
            "Agent": "Managing agent",
            "SiteManager": "Site manager",
            "JointOwner": "Joint owner",
        }.get(ctype, ctype)
        add(name, role, "HPD registration", addr or None, {"contact_type": ctype})

    return identities


async def build_owner_dossier(bbl: str) -> dict:
    bbl = normalize_bbl(bbl)
    cache_key = f"owners:{bbl}"
    cached = cache.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    boro, block, lot = split_bbl(bbl)
    async with httpx.AsyncClient(timeout=45.0) as client:
        pluto, acris, hpd_pair = await asyncio.gather(
            fetch_pluto(bbl, client),
            fetch_acris(boro, block, lot, client),
            fetch_hpd_registrations_and_contacts(boro, block, lot, client),
        )
        _regs, hpd_contacts = hpd_pair
        pluto_row = pluto["records"][0] if pluto["records"] else None
        identities = extract_identities(pluto_row, acris, hpd_contacts)
        identities = await ensure_deed_grantee(client, boro, block, lot, identities)

        # Build search seeds
        raw_names = []
        norms = []
        addrs = []
        for ident in identities:
            if ident.get("name"):
                raw_names.append(ident["name"])
            if ident.get("normalized"):
                norms.append(ident["normalized"])
            if ident.get("address"):
                na = normalize_address([ident["address"]])
                if na:
                    addrs.append(na)
        # Dedupe preserving order
        def uniq(seq):
            out, s = [], set()
            for x in seq:
                if x not in s:
                    s.add(x)
                    out.append(x)
            return out

        raw_names, norms, addrs = uniq(raw_names), uniq(norms), uniq(addrs)

        # Primary search name = PLUTO owner or first identity
        primary_raw = (pluto_row or {}).get("ownername") or (raw_names[0] if raw_names else "")
        primary_norm = normalize_owner_name(primary_raw) or (norms[0] if norms else "")

        # Prefer specific (non-generic) names for ACRIS / HPD expansion
        search_raw = primary_raw
        search_norm = primary_norm
        for ident in identities:
            n = ident.get("normalized") or ""
            if n and not is_generic_owner(n):
                search_raw = ident.get("name") or search_raw
                search_norm = n
                break

        hpd_names = [n for n in raw_names if not is_generic_owner(normalize_owner_name(n))][:3]
        hpd_norms = [n for n in norms if not is_generic_owner(n)][:3]
        if not hpd_names:
            hpd_names, hpd_norms = raw_names[:2], norms[:2]

        pluto_hits, acris_hits, hpd_hits = await asyncio.gather(
            _pluto_by_owner(client, primary_raw, primary_norm),
            _acris_grantee_portfolio(client, search_raw, search_norm),
            _hpd_portfolio(client, hpd_names, hpd_norms, addrs[:2]),
        )

        # Also search PLUTO for other strong identity names (e.g. corporate owner ≠ PLUTO name)
        extra_pluto = []
        for ident in identities[1:4]:
            n = ident.get("normalized") or ""
            if not n or n == primary_norm or is_generic_owner(n):
                continue
            if fuzzy_name_score(n, primary_norm) >= 0.85:
                continue
            # Prefer corporate / deed identities over agents for extra PLUTO sweeps
            if ident.get("role") in {"Managing agent", "Site manager", "Officer"}:
                continue
            extra_pluto.append(
                _pluto_by_owner(client, ident.get("name") or "", n)
            )
        if extra_pluto:
            extras = await asyncio.gather(*extra_pluto)
            for e in extras:
                pluto_hits.extend(e)

    portfolio = merge_portfolio(bbl, [pluto_hits, acris_hits, hpd_hits])
    other_count = sum(1 for p in portfolio if not p.get("is_current"))

    result = {
        "bbl": bbl,
        "identities": identities,
        "portfolio": portfolio,
        "portfolio_count": len(portfolio),
        "other_properties_count": other_count,
        "notes": [
            "Matches are heuristic (name normalization + token overlap + shared HPD mailing address).",
            "Single-purpose LLCs often hide common ownership — skip-tracing / corporate filings needed for true UBOs.",
            "HPD Open Data contacts do not include phone numbers.",
            "Results capped for performance; not a complete ownership graph.",
        ],
        "cached": False,
    }
    cache.set(cache_key, result, CACHE_TTL)
    return result
