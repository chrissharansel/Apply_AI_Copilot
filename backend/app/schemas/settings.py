from typing import Literal
from pydantic import BaseModel, Field


class UserSettings(BaseModel):
    ai_answers: Literal["auto", "ask"] = "auto"            # auto = draft free-text answers; ask = I write them (AI draft on request)
    tone: Literal["professional", "friendly", "concise", "confident"] = "professional"
    writing_notes: str = Field("", max_length=1500)        # standing style instructions for AI-written answers
    max_words: int = Field(150, ge=40, le=400)
    semantic_reuse: bool = True                            # reuse saved answers for similarly-worded questions
    show_browser: bool = True                              # visible window (needed for CAPTCHA/login help)
    auto_advance: bool = True                              # click Next/Continue by itself; off = pause after each step
