from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=10_000)

    @field_validator("session_id")
    @classmethod
    def safe_session_id(cls, value: str) -> str:
        if not all(character.isalnum() or character in "-_" for character in value):
            raise ValueError("session_id may contain only letters, numbers, '-' and '_'")
        return value


class FeedbackRequest(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
