"""App configuration. Auth / paid-tier flags are stubs for a future public launch."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "NYC Property Data"
    api_prefix: str = "/api/v1"
    socrata_base: str = "https://data.cityofnewyork.us/resource"
    geosearch_url: str = "https://geosearch.planninglabs.nyc/v2/search"
    http_timeout: float = 30.0

    # Future: turn on when accounts are wired up
    feature_auth: bool = False
    feature_paid_tier: bool = False
    # Free tier soft caps (enforced later)
    free_searches_per_day: int = 25
    free_property_views_per_day: int = 10

    class Config:
        env_prefix = "NYCP_"


settings = Settings()
