from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "agent.state",
    "transcript.partial",
    "transcript.final",
    "research.started",
    "research.completed",
    "research.expired",
    "research.failed",
    "answer.card",
    "control.dismiss",
    "control.research",
    "control.speak",
    "control.stop",
]


class RoomEvent(BaseModel):
    type: EventType
    ts_ms: int = Field(ge=0)
    payload: dict[str, Any]

    @classmethod
    def now(cls, event_type: EventType, payload: BaseModel | dict[str, Any]) -> RoomEvent:
        body = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        return cls(type=event_type, ts_ms=time.time_ns() // 1_000_000, payload=body)


class TranscriptPayload(BaseModel):
    event_id: str
    speaker_id: str
    speaker_name: str
    track_sid: str
    text: str
    sequence: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int | None = Field(default=None, ge=0)


class ResearchPayload(BaseModel):
    job_id: str
    asker_id: str
    asker_name: str
    query: str
    route: Literal["INSTANT", "QUICK"] = "QUICK"
    status: Literal["searching", "completed", "expired", "failed"]
    created_at_ms: int = Field(ge=0)
    deadline_at_ms: int = Field(ge=0)


class Citation(BaseModel):
    title: str
    url: str
    snippet: str = ""


class AnswerPayload(BaseModel):
    job_id: str
    asker_id: str
    asker_name: str
    question: str
    concise_answer: str
    full_answer: str
    confidence: float = Field(ge=0, le=1)
    citations: list[Citation]
    expired: bool = False
    speak: bool = False
