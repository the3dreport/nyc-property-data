from fastapi import APIRouter, Depends, HTTPException
from ..auth_stub import User, check_quota, require_user
from ..models.schemas import PropertyResponse
from ..services import socrata
from ..services import owners as owners_svc

router = APIRouter(tags=["property"])


@router.get("/property/{bbl}", response_model=PropertyResponse)
async def get_property(bbl: str, user: User = Depends(require_user)):
    """Assemble a PropertyShark-style dossier for one NYC BBL from live Open Data."""
    await check_quota(user, "property_view")
    try:
        data = await socrata.build_property(bbl)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream data error: {e}") from e
    return PropertyResponse(**data)


@router.get("/property/{bbl}/owners")
async def get_property_owners(bbl: str, user: User = Depends(require_user)):
    """Consolidate owner identities and find other NYC holdings (lazy Owner tab)."""
    await check_quota(user, "owner_portfolio")
    try:
        return await owners_svc.build_owner_dossier(bbl)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Owner lookup failed: {e}") from e
