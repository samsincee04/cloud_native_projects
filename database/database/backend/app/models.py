from pydantic import BaseModel, field_validator


class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 100

    @field_validator("text")
    @classmethod
    def text_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text must be non-empty")
        return v


class SummarizeResponse(BaseModel):
    summary: str
    model: str
    truncated: bool


class SummaryRow(BaseModel):
    id: int
    summary: str
    model: str
    truncated: bool
    latency_ms: int | None
    created_at: str


class SummariesResponse(BaseModel):
    summaries: list[SummaryRow]
