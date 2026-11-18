from pydantic import BaseModel, Field


class KnowledgeIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)
    category: str | None = None
    reusable: bool = True


class KnowledgeUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    category: str | None = None
    reusable: bool | None = None
