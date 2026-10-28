# NYC Property Data (PropertyShark-style prototype)

Public-facing prototype for researching NYC tax lots using live city Open Data.

## Quick start

```bash
cd /workspace/nyc-property
./start.sh
# → http://127.0.0.1:8787
```

Or manually:

```bash
cd /workspace/nyc-property
.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8787
```

## Stack

- **Backend:** FastAPI (`backend/app`) proxies NYC Planning GeoSearch + Socrata Open Data, joins ACRIS Legals/Master/Parties.
- **Frontend:** Static HTML/CSS/JS with Leaflet map; landing page search + property dossier tabs.
- **Auth / paid tier:** Stubbed in `backend/app/auth_stub.py` and `config.py` (`feature_auth`, `feature_paid_tier`). Landing has Log in / Sign up CTAs.

## API

- `GET /api/v1/search?q=350+5th+Ave,+Manhattan`
- `GET /api/v1/property/{bbl}`
- `GET /api/health`

## Data sources (verified live)

| Section | Dataset ID |
|---------|------------|
| PLUTO | `64uk-42ks` |
| DOF Assessment | `yjxr-fw8i` |
| ACRIS Legals / Master / Parties | `8h5j-fqxa` / `bnx9-e6tj` / `636b-3b5g` |
| DOB Permits | `ipu4-2q9a` |
| DOB Jobs | `ic3t-wcy2` |
| DOB Violations | `3h2n-5cm9` |
| DOB ECB | `6bgk-3dad` |
| HPD Violations | `wvxf-dwi5` |
| HPD Registrations / Contacts | `tesw-yqqr` / `feu5-w2e2` |
| Address → BBL | GeoSearch `geosearch.planninglabs.nyc` |

**Note:** HPD Registration Contacts Open Data does **not** include phone numbers.
