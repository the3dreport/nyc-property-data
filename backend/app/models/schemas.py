from typing import Any, Optional
from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    label: str
    address: str
    borough: Optional[str] = None
    bbl: Optional[str] = None
    bin: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    postalcode: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]


class SectionResult(BaseModel):
    source: str
    dataset_id: Optional[str] = None
    count: int = 0
    records: list[dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None
    error: Optional[str] = None


class PropertyResponse(BaseModel):
    bbl: str
    borough_code: str
    block: str
    lot: str
    summary: dict[str, Any] = Field(default_factory=dict)
    pluto: SectionResult
    assessment: SectionResult
    acris: SectionResult
    dob_permits: SectionResult
    dob_jobs: SectionResult
    dob_violations: SectionResult
    dob_ecb: SectionResult
    hpd_violations: SectionResult
    hpd_registrations: SectionResult
    hpd_contacts: SectionResult
