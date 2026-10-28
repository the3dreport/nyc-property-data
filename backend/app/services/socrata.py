"""NYC Open Data (Socrata) + GeoSearch clients."""
from __future__ import annotations

import asyncio
from typing import Any, Optional
import httpx
from ..config import settings

# Verified live dataset IDs (Oct 2026)
DATASETS = {
    "pluto": "64uk-42ks",
    "assessment": "yjxr-fw8i",
    "acris_legals": "8h5j-fqxa",
    "acris_master": "bnx9-e6tj",
    "acris_parties": "636b-3b5g",
    "dob_permits": "ipu4-2q9a",
    "dob_jobs": "ic3t-wcy2",
    "dob_violations": "3h2n-5cm9",
    "dob_ecb": "6bgk-3dad",
    "hpd_violations": "wvxf-dwi5",
    "hpd_registrations": "tesw-yqqr",
    "hpd_contacts": "feu5-w2e2",
}

BOROUGH_NAMES = {
    "1": "MANHATTAN",
    "2": "BRONX",
    "3": "BROOKLYN",
    "4": "QUEENS",
    "5": "STATEN ISLAND",
}
BOROUGH_SHORT = {"1": "MN", "2": "BX", "3": "BK", "4": "QN", "5": "SI"}


def normalize_bbl(raw: str) -> str:
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) < 10:
        raise ValueError(f"Invalid BBL: {raw}")
    # PLUTO sometimes returns float-like strings
    if len(digits) > 10:
        digits = digits[:10]
    return digits.zfill(10)


def split_bbl(bbl: str) -> tuple[str, str, str]:
    bbl = normalize_bbl(bbl)
    return bbl[0], bbl[1:6].lstrip("0") or "0", bbl[6:10].lstrip("0") or "0"


def pad_block(block: str) -> str:
    return str(block).zfill(5)


def pad_lot(lot: str) -> str:
    """ACRIS-style 4-digit lot (legacy helper)."""
    return str(lot).zfill(4)


def pad_lot_dob(lot: str) -> str:
    """DOB BIS pads lot to 5 characters (e.g. 00041)."""
    return str(lot).zfill(5)


async def _get_json(
    client: httpx.AsyncClient, url: str, params: Optional[dict] = None
) -> Any:
    r = await client.get(url, params=params or {})
    r.raise_for_status()
    return r.json()


async def geosearch(query: str, size: int = 8) -> list[dict]:
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        data = await _get_json(
            client,
            settings.geosearch_url,
            {"text": query, "size": size},
        )
    hits = []
    for f in data.get("features") or []:
        props = f.get("properties") or {}
        pad = (props.get("addendum") or {}).get("pad") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or [None, None]
        bbl = pad.get("bbl")
        if bbl:
            bbl = normalize_bbl(str(bbl).split(".")[0])
        hits.append(
            {
                "label": props.get("label") or props.get("name") or query,
                "address": props.get("name") or props.get("label") or query,
                "borough": props.get("borough"),
                "bbl": bbl,
                "bin": pad.get("bin"),
                "latitude": coords[1],
                "longitude": coords[0],
                "postalcode": props.get("postalcode"),
            }
        )
    return hits


async def socrata_query(
    dataset_id: str,
    params: dict,
    client: Optional[httpx.AsyncClient] = None,
) -> list[dict]:
    url = f"{settings.socrata_base}/{dataset_id}.json"
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=settings.http_timeout)
    try:
        return await _get_json(client, url, params)
    finally:
        if own:
            await client.aclose()


async def fetch_pluto(bbl: str, client: httpx.AsyncClient) -> dict:
    # PLUTO bbl is stored as float-like string e.g. 1008350041.00000000
    rows = await socrata_query(
        DATASETS["pluto"],
        {"$where": f"bbl={float(bbl)}", "$limit": "1"},
        client,
    )
    return {
        "source": "PLUTO (DCP)",
        "dataset_id": DATASETS["pluto"],
        "count": len(rows),
        "records": rows,
        "note": None if rows else "No PLUTO record for this BBL.",
    }


async def fetch_assessment(boro: str, block: str, lot: str, client: httpx.AsyncClient) -> dict:
    where = f"boro='{boro}' AND block={block} AND lot={lot}"
    try:
        rows = await socrata_query(
            DATASETS["assessment"],
            {"$where": where, "$order": "year DESC", "$limit": "12"},
            client,
        )
        return {
            "source": "DOF Property Valuation & Assessment",
            "dataset_id": DATASETS["assessment"],
            "count": len(rows),
            "records": rows,
            "note": None if rows else "No assessment rows found.",
        }
    except Exception as e:
        return {
            "source": "DOF Property Valuation & Assessment",
            "dataset_id": DATASETS["assessment"],
            "count": 0,
            "records": [],
            "error": str(e),
        }


async def fetch_acris(boro: str, block: str, lot: str, client: httpx.AsyncClient) -> dict:
    try:
        legals = await socrata_query(
            DATASETS["acris_legals"],
            {
                "borough": boro,
                "block": block,
                "lot": lot,
                "$limit": "40",
                "$select": "document_id,borough,block,lot,street_number,street_name,property_type,good_through_date",
            },
            client,
        )
        doc_ids = list({r["document_id"] for r in legals if r.get("document_id")})
        masters: list[dict] = []
        parties: list[dict] = []
        if doc_ids:
            # Batch in chunks of 20 for SoQL IN
            for i in range(0, min(len(doc_ids), 40), 20):
                chunk = doc_ids[i : i + 20]
                id_list = ",".join(f"'{d}'" for d in chunk)
                m, p = await asyncio.gather(
                    socrata_query(
                        DATASETS["acris_master"],
                        {
                            "$where": f"document_id in ({id_list})",
                            "$limit": "40",
                            "$order": "document_date DESC",
                        },
                        client,
                    ),
                    socrata_query(
                        DATASETS["acris_parties"],
                        {
                            "$where": f"document_id in ({id_list})",
                            "$limit": "100",
                        },
                        client,
                    ),
                )
                masters.extend(m)
                parties.extend(p)

        party_by_doc: dict[str, list] = {}
        for p in parties:
            party_by_doc.setdefault(p.get("document_id", ""), []).append(
                {
                    "party_type": p.get("party_type"),
                    "name": p.get("name"),
                    "address_1": p.get("address_1"),
                    "city": p.get("city"),
                    "state": p.get("state"),
                    "zip": p.get("zip"),
                }
            )

        master_by_id = {m["document_id"]: m for m in masters if m.get("document_id")}
        combined = []
        for lid in doc_ids:
            m = master_by_id.get(lid, {"document_id": lid})
            combined.append(
                {
                    "document_id": lid,
                    "doc_type": m.get("doc_type"),
                    "document_date": m.get("document_date"),
                    "recorded_datetime": m.get("recorded_datetime"),
                    "document_amt": m.get("document_amt"),
                    "crfn": m.get("crfn"),
                    "parties": party_by_doc.get(lid, []),
                }
            )
        # Sort by document_date desc when present
        combined.sort(key=lambda x: x.get("document_date") or "", reverse=True)

        return {
            "source": "ACRIS Real Property (Legals + Master + Parties)",
            "dataset_id": f"{DATASETS['acris_legals']}/{DATASETS['acris_master']}/{DATASETS['acris_parties']}",
            "count": len(combined),
            "records": combined[:40],
            "note": None
            if combined
            else "No ACRIS documents linked to this tax lot.",
        }
    except Exception as e:
        return {
            "source": "ACRIS Real Property",
            "dataset_id": DATASETS["acris_legals"],
            "count": 0,
            "records": [],
            "error": str(e),
        }


async def fetch_dob_permits(boro: str, block: str, lot: str, client: httpx.AsyncClient) -> dict:
    bname = BOROUGH_NAMES.get(boro, "MANHATTAN")
    where = f"borough='{bname}' AND block='{pad_block(block)}' AND lot='{pad_lot_dob(lot)}'"
    try:
        rows = await socrata_query(
            DATASETS["dob_permits"],
            {"$where": where, "$limit": "40", "$order": "filing_date DESC"},
            client,
        )
        return {
            "source": "DOB Permit Issuance",
            "dataset_id": DATASETS["dob_permits"],
            "count": len(rows),
            "records": rows,
            "note": None if rows else "No DOB permits found.",
        }
    except Exception as e:
        return {
            "source": "DOB Permit Issuance",
            "dataset_id": DATASETS["dob_permits"],
            "count": 0,
            "records": [],
            "error": str(e),
        }


async def fetch_dob_jobs(boro: str, block: str, lot: str, client: httpx.AsyncClient) -> dict:
    bname = BOROUGH_NAMES.get(boro, "MANHATTAN")
    where = f"borough='{bname}' AND block='{pad_block(block)}' AND lot='{pad_lot_dob(lot)}'"
    try:
        rows = await socrata_query(
            DATASETS["dob_jobs"],
            {"$where": where, "$limit": "25", "$order": "pre__filing_date DESC"},
            client,
        )
        return {
            "source": "DOB Job Application Filings",
            "dataset_id": DATASETS["dob_jobs"],
            "count": len(rows),
            "records": rows,
            "note": None if rows else "No DOB job filings found (pre-DOB NOW).",
        }
    except Exception as e:
        return {
            "source": "DOB Job Application Filings",
            "dataset_id": DATASETS["dob_jobs"],
            "count": 0,
            "records": [],
            "error": str(e),
        }


async def fetch_dob_violations(boro: str, block: str, lot: str, client: httpx.AsyncClient) -> dict:
    where = f"boro='{boro}' AND block='{pad_block(block)}' AND lot='{pad_lot_dob(lot)}'"
    try:
        rows = await socrata_query(
            DATASETS["dob_violations"],
            {"$where": where, "$limit": "25", "$order": "issue_date DESC"},
            client,
        )
        return {
            "source": "DOB Violations",
            "dataset_id": DATASETS["dob_violations"],
            "count": len(rows),
            "records": rows,
            "note": None if rows else "No DOB violations found.",
        }
    except Exception as e:
        return {
            "source": "DOB Violations",
            "dataset_id": DATASETS["dob_violations"],
            "count": 0,
            "records": [],
            "error": str(e),
        }


async def fetch_dob_ecb(boro: str, block: str, lot: str, client: httpx.AsyncClient) -> dict:
    where = f"boro='{boro}' AND block='{pad_block(block)}' AND lot='{pad_lot_dob(lot)}'"
    try:
        rows = await socrata_query(
            DATASETS["dob_ecb"],
            {"$where": where, "$limit": "25", "$order": "issue_date DESC"},
            client,
        )
        return {
            "source": "DOB ECB / OATH Violations",
            "dataset_id": DATASETS["dob_ecb"],
            "count": len(rows),
            "records": rows,
            "note": None if rows else "No ECB violations found.",
        }
    except Exception as e:
        return {
            "source": "DOB ECB / OATH Violations",
            "dataset_id": DATASETS["dob_ecb"],
            "count": 0,
            "records": [],
            "error": str(e),
        }


async def fetch_hpd_violations(boro: str, block: str, lot: str, client: httpx.AsyncClient) -> dict:
    where = f"boroid='{boro}' AND block='{block}' AND lot='{lot}'"
    try:
        rows = await socrata_query(
            DATASETS["hpd_violations"],
            {"$where": where, "$limit": "40", "$order": "inspectiondate DESC"},
            client,
        )
        return {
            "source": "HPD Housing Maintenance Code Violations",
            "dataset_id": DATASETS["hpd_violations"],
            "count": len(rows),
            "records": rows,
            "note": None
            if rows
            else "No HPD violations (common for non-rental / 1–2 family owner-occupied).",
        }
    except Exception as e:
        return {
            "source": "HPD Violations",
            "dataset_id": DATASETS["hpd_violations"],
            "count": 0,
            "records": [],
            "error": str(e),
        }


async def fetch_hpd_registrations_and_contacts(
    boro: str, block: str, lot: str, client: httpx.AsyncClient
) -> tuple[dict, dict]:
    where = f"boroid='{boro}' AND block='{block}' AND lot='{lot}'"
    try:
        regs = await socrata_query(
            DATASETS["hpd_registrations"],
            {"$where": where, "$limit": "10"},
            client,
        )
        contacts: list[dict] = []
        if regs:
            reg_ids = [r["registrationid"] for r in regs if r.get("registrationid")]
            if reg_ids:
                id_list = ",".join(f"'{i}'" for i in reg_ids)
                contacts = await socrata_query(
                    DATASETS["hpd_contacts"],
                    {"$where": f"registrationid in ({id_list})", "$limit": "50"},
                    client,
                )
        reg_section = {
            "source": "HPD Multiple Dwelling Registrations",
            "dataset_id": DATASETS["hpd_registrations"],
            "count": len(regs),
            "records": regs,
            "note": None
            if regs
            else "No HPD registration (typically only required for rentals with 3+ units or non-owner-occupied 1–2 family).",
        }
        contact_note = (
            "HPD Registration Contacts Open Data does not publish phone numbers "
            "(names, roles, and business mailing addresses only). "
            "Phone skip-tracing requires a paid data-broker API."
            if contacts
            else None
        )
        if not contacts and regs:
            contact_note = "Registration found but no contact rows returned."
        elif not contacts:
            contact_note = "No HPD registration contacts."
        contact_section = {
            "source": "HPD Registration Contacts",
            "dataset_id": DATASETS["hpd_contacts"],
            "count": len(contacts),
            "records": contacts,
            "note": contact_note,
        }
        return reg_section, contact_section
    except Exception as e:
        err = {
            "source": "HPD Registrations",
            "dataset_id": DATASETS["hpd_registrations"],
            "count": 0,
            "records": [],
            "error": str(e),
        }
        err2 = {
            "source": "HPD Registration Contacts",
            "dataset_id": DATASETS["hpd_contacts"],
            "count": 0,
            "records": [],
            "error": str(e),
        }
        return err, err2


def summarize_pluto(row: Optional[dict], bbl: str, boro: str, block: str, lot: str) -> dict:
    if not row:
        return {
            "bbl": bbl,
            "borough": BOROUGH_NAMES.get(boro),
            "block": block,
            "lot": lot,
            "address": None,
        }
    return {
        "bbl": bbl,
        "borough": BOROUGH_NAMES.get(boro) or row.get("borough"),
        "block": block,
        "lot": lot,
        "address": row.get("address"),
        "zipcode": row.get("zipcode"),
        "ownername": row.get("ownername"),
        "ownertype": row.get("ownertype"),
        "bldgclass": row.get("bldgclass"),
        "landuse": row.get("landuse"),
        "zonedist1": row.get("zonedist1"),
        "zonedist2": row.get("zonedist2"),
        "yearbuilt": row.get("yearbuilt"),
        "yearalter1": row.get("yearalter1"),
        "numfloors": row.get("numfloors"),
        "unitsres": row.get("unitsres"),
        "unitstotal": row.get("unitstotal"),
        "lotarea": row.get("lotarea"),
        "bldgarea": row.get("bldgarea"),
        "assessland": row.get("assessland"),
        "assesstot": row.get("assesstot"),
        "exempttot": row.get("exempttot"),
        "builtfar": row.get("builtfar"),
        "residfar": row.get("residfar"),
        "commfar": row.get("commfar"),
        "landmark": row.get("landmark"),
        "latitude": float(row["latitude"]) if row.get("latitude") else None,
        "longitude": float(row["longitude"]) if row.get("longitude") else None,
        "bin": None,
    }


async def build_property(bbl: str) -> dict:
    bbl = normalize_bbl(bbl)
    boro, block, lot = split_bbl(bbl)
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        (
            pluto,
            assessment,
            acris,
            permits,
            jobs,
            dob_v,
            ecb,
            hpd_v,
            hpd_pair,
        ) = await asyncio.gather(
            fetch_pluto(bbl, client),
            fetch_assessment(boro, block, lot, client),
            fetch_acris(boro, block, lot, client),
            fetch_dob_permits(boro, block, lot, client),
            fetch_dob_jobs(boro, block, lot, client),
            fetch_dob_violations(boro, block, lot, client),
            fetch_dob_ecb(boro, block, lot, client),
            fetch_hpd_violations(boro, block, lot, client),
            fetch_hpd_registrations_and_contacts(boro, block, lot, client),
        )
    hpd_reg, hpd_contacts = hpd_pair
    pluto_row = pluto["records"][0] if pluto["records"] else None
    summary = summarize_pluto(pluto_row, bbl, boro, block, lot)
    return {
        "bbl": bbl,
        "borough_code": boro,
        "block": block,
        "lot": lot,
        "summary": summary,
        "pluto": pluto,
        "assessment": assessment,
        "acris": acris,
        "dob_permits": permits,
        "dob_jobs": jobs,
        "dob_violations": dob_v,
        "dob_ecb": ecb,
        "hpd_violations": hpd_v,
        "hpd_registrations": hpd_reg,
        "hpd_contacts": hpd_contacts,
    }
