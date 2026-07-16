from typing import List

from pydantic import BaseModel, Field, field_validator

from app.services.fact_constants import ALLOWED_FACT_TYPES, ALLOWED_STATUSES


class AIFact(BaseModel):
    subject: str
    action: str
    object: str
    fact_type: str
    status: str
    country: str = "unknown"
    technology: List[str] = Field(default_factory=list)
    organization: List[str] = Field(default_factory=list)
    category: str = "Industry Signal"
    importance: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    summary: str
    evidence_sentence: str

    @field_validator("subject", "action", "object", "summary", "evidence_sentence")
    @classmethod
    def required_text(cls, value):
        if not value or not value.strip():
            raise ValueError("field must not be empty")
        return value.strip()

    @field_validator("fact_type")
    @classmethod
    def valid_fact_type(cls, value):
        value = value.strip().lower()
        if value not in ALLOWED_FACT_TYPES:
            raise ValueError(f"unsupported fact_type: {value}")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        value = value.strip().lower()
        if value not in ALLOWED_STATUSES:
            raise ValueError(f"unsupported status: {value}")
        return value

    @field_validator("technology", "organization")
    @classmethod
    def unique_strings(cls, values):
        unique = []
        for value in values:
            clean_value = str(value).strip()
            if clean_value and clean_value not in unique:
                unique.append(clean_value)
        return unique


class AIFactExtraction(BaseModel):
    article_id: int
    facts: List[AIFact] = Field(default_factory=list)

