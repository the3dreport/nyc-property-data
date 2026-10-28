# Test results (2026-10-28, America/New_York)

Server: `http://127.0.0.1:8787` via `./start.sh` (uvicorn on port **8787**)

## Addresses tested

| Address | BBL | Highlights |
|---------|-----|------------|
| 350 5th Ave, Manhattan (Empire State) | 1008350041 | PLUTO, 9 assessments, 40 ACRIS docs, 40 permits, 25 jobs, 25 DOB + 25 ECB viols; HPD empty (commercial) |
| 234 Bergen St, Brooklyn (rowhouse) | 3003870031 | PLUTO owner FEUER WENDY, ACRIS 23, DOB permits/jobs, HPD 4 viols + registration + 2 contacts |
| 3620 Webster Ave, Bronx (multifamily) | 2033600077 | PLUTO, ACRIS 15, DOB permits/jobs/viols, HPD 40 viols + reg + 3 contacts |

## Dataset notes

- **Worked:** PLUTO `64uk-42ks`, Assessment `yjxr-fw8i`, ACRIS `8h5j-fqxa`/`bnx9-e6tj`/`636b-3b5g`, DOB permits `ipu4-2q9a`, jobs `ic3t-wcy2`, viols `3h2n-5cm9`, ECB `6bgk-3dad`, HPD viols `wvxf-dwi5`, regs `tesw-yqqr`, contacts `feu5-w2e2`, GeoSearch.
- **Failed / unavailable:** DOF `rgy2-tti8` / `qpsp-bm9z` return "non-tabular" — used `yjxr-fw8i` instead. HPD contacts Open Data has **no phone field**.
- **Quirk:** DOB BIS pads lot to **5** digits (`00041`); wrong padding silently under-returns rows.

## Follow-up 2026-10-28 (light theme + Owner tab)

- Light theme applied site-wide (`frontend/css/styles.css`).
- Owner tab: `GET /api/v1/property/{bbl}/owners` (lazy-loaded), TTL cache 10 min.
- Empire `1008350041`: 1 identity (SPV LLC), 0 other lots (expected).
- Brooklyn `3003870031`: 4 identities (PLUTO/ACRIS/HPD Wendy Feuer), 0 other lots in PLUTO.
- Bronx `2033600077`: 6 identities, **9 other** related lots (portfolio demo).

Fresh screenshots: `01-landing-light.png`, `02-property-empire-light.png`, `03-owner-brooklyn.png`, `04-owner-bronx-portfolio.png`
