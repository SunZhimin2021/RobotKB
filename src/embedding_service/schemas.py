from enum import Enum
from pydantic import BaseModel, Field


class EmbedType(str, Enum):
    DENSE = "dense"
    SPARSE = "sparse"
    BOTH = "both"


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=64)
    type: EmbedType = EmbedType.DENSE


class SparseVector(BaseModel):
    # token_id → weight mapping
    indices: list[int]
    values: list[float]


class EmbedResponse(BaseModel):
    # [N, embedding_dim] — present when type is "dense" or "both"
    dense: list[list[float]] | None = None
    # N sparse vectors — present when type is "sparse" or "both"
    sparse: list[SparseVector] | None = None
    elapsed_ms: float
