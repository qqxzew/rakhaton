"""Pydantic models for the JSON the language model must return."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ModalityText = Literal["CT", "MR", "PET/CT", "PET", "RTG", "SONO", "MAMO", "SCINT", "UNKNOWN"]


class CurrentStudy(BaseModel):
    modality: str | None = None
    regions: list[str] = Field(default_factory=list)
    region_text: str | None = None


class LlmReference(BaseModel):
    modality: str = "UNKNOWN"
    regions: list[str] = Field(default_factory=list)
    date_text: str | None = None
    date_iso: str | None = None
    site_text: str | None = None
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> object:
        if isinstance(v, (int, float)):
            return min(1.0, max(0.0, float(v)))
        return v


class PriorExtraction(BaseModel):
    current_study: CurrentStudy = Field(default_factory=CurrentStudy)
    references: list[LlmReference] = Field(default_factory=list)


class RelativeTiming(BaseModel):
    value: int
    unit: Literal["days", "weeks", "months", "years"]


class LlmPlannedExam(BaseModel):
    modality: str = "UNKNOWN"
    regions: list[str] = Field(default_factory=list)
    date_iso: str | None = None
    relative: RelativeTiming | None = None
    site_text: str | None = None
    kind: Literal["imaging", "mdt", "rt_planning"] = "imaging"
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> object:
        if isinstance(v, (int, float)):
            return min(1.0, max(0.0, float(v)))
        return v


class PlannedExtraction(BaseModel):
    planned: list[LlmPlannedExam] = Field(default_factory=list)
