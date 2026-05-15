from pydantic import BaseModel, Field


class RerankRequest(BaseModel):
    query: str
    passages: list[str] = Field(..., min_length=1, max_length=20)
    top_n: int = Field(default=5, ge=1, le=20)


class RerankResponse(BaseModel):
    # Relevance score for each passage (same order as input)
    scores: list[float]
    # Indices of passages sorted by score descending, length = min(top_n, len(passages))
    ranked_indices: list[int]
    elapsed_ms: float
