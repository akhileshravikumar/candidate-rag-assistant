from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Query(StrictModel):
    question: str = Field(min_length=3, max_length=600)
    candidate_ids: list[str] = Field(default_factory=list, max_length=15)
    mode: Literal["qa", "shortlist"] = "qa"


class Citation(StrictModel):
    chunk_id: str
    quote: str


class Finding(StrictModel):
    candidate_id: str
    text: str
    requirement_ids: list[str]
    citations: list[Citation]


class Unknown(StrictModel):
    candidate_id: str
    topic: str


class Answer(StrictModel):
    status: Literal["answered", "abstained", "refused"]
    findings: list[Finding]
    unknowns: list[Unknown]
    shortlist: list[str]