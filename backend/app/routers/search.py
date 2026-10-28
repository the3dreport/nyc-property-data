from fastapi import APIRouter, HTTPException, Query
from ..models.schemas import SearchHit, SearchResponse
from ..services import socrata

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search_address(q: str = Query(..., min_length=2, max_length=200)):
    """Resolve a street address (or partial) via NYC Planning GeoSearch → BBL."""
    try:
        hits = await socrata.geosearch(q)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Geosearch failed: {e}") from e
    # Prefer results that have a BBL
    hits = [h for h in hits if h.get("bbl")] or hits
    return SearchResponse(
        query=q,
        results=[SearchHit(**h) for h in hits],
    )
