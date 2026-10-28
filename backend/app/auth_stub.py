"""
Auth / accounts stub for the future public product.

When feature_auth is enabled:
  - Require JWT / session on /api/v1/property/*
  - Attach current_user via Depends(get_current_user)
  - Enforce free-tier daily caps; unlock unlimited on paid plan

This module is intentionally a no-op today so the prototype stays open.
"""
from typing import Optional
from fastapi import Depends, HTTPException, Request
from .config import settings


class User:
    def __init__(self, id: str, email: str, plan: str = "free"):
        self.id = id
        self.email = email
        self.plan = plan  # free | pro | enterprise


async def get_current_user_optional(request: Request) -> Optional[User]:
    if not settings.feature_auth:
        return None
    # Future: parse Authorization Bearer / session cookie
    auth = request.headers.get("Authorization")
    if not auth:
        return None
    raise HTTPException(status_code=501, detail="Auth not implemented yet")


async def require_user(user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if not settings.feature_auth:
        return User(id="anonymous", email="anon@local", plan="pro")
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


async def check_quota(user: User, action: str) -> None:
    """Future: Redis/DB counter for free_searches_per_day / free_property_views_per_day."""
    if not settings.feature_paid_tier:
        return
    if user.plan != "free":
        return
    # Placeholder — no enforcement yet
    return
