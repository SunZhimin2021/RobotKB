from __future__ import annotations

from enum import Enum
from typing import Any, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceTier(str, Enum):
    OFFICIAL = "official"
    VENDOR = "vendor"
    COMMUNITY = "community"
    INTERNAL_DRAFT = "internal_draft"


class DocumentCategory(str, Enum):
    HARDWARE = "hardware"
    SOFTWARE = "software"
    DEVELOPMENT = "development"
    FAULT_HANDLING = "fault_handling"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    REVIEWING = "reviewing"
    VERIFIED = "verified"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


class MatchStatus(str, Enum):
    EXACT = "exact"
    SOFT = "soft"
    GRAPH_INFERRED = "graph_inferred"
    DEGRADED = "degraded"


class MatchedConstraint(BaseModel):
    field: str
    value: str
    status: MatchStatus
    note: str | None = None


class Constraint(BaseModel):
    chip: list[str] | None = None
    board: str | None = None
    ros_version: str | None = None
    kernel_range: str | None = None
    source_tier_min: SourceTier | None = None
    language: str | None = None

    @field_validator("chip", mode="before")
    @classmethod
    def coerce_chip_to_list(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class DocumentMeta(BaseModel):
    title: str
    category: DocumentCategory
    source_tier: SourceTier
    applicable_chips: list[str]
    applicable_boards: list[str] = Field(default_factory=list)
    ros_versions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    doc_version: str | None = None
    status: DocumentStatus = DocumentStatus.PENDING
    content_hash: str | None = None
    chunk_count: int | None = None
    import_timestamp: str | None = None
    author: str | None = None
    vendor: str | None = None
    valid_until: str | None = None


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    page: int
    section: str | None = None
    applicable_chips: list[str] = Field(default_factory=list)
    applicable_boards: list[str] = Field(default_factory=list)
    ros_versions: list[str] = Field(default_factory=list)
    source_tier: SourceTier | None = None
    status: DocumentStatus = DocumentStatus.PUBLISHED


class SearchRequest(BaseModel):
    query: str
    constraints: Constraint | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    include_superseded: bool = False
    allow_degradation: bool = True


class SearchResponse(BaseModel):
    query: str
    hits: list[dict[str, Any]] = Field(default_factory=list)
    degraded: bool = False
    degradation_note: str | None = None
    conflict_report: list[dict[str, Any]] | None = None

    @property
    def total(self) -> int:
        return len(self.hits)
