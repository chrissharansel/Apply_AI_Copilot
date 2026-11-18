from typing import Any, Literal
from pydantic import BaseModel, Field


class StartSession(BaseModel):
    url: str = Field(max_length=2048)
    resume_id: str | None = None


class AnswerIn(BaseModel):
    qid: str
    action: Literal["answer", "skip", "done"] = "answer"
    answer: Any = None
    save: Literal["reusable", "job_only", "no"] = "no"


class ApproveIn(BaseModel):
    edits: dict[str, Any] = {}
