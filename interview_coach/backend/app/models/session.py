"""Pydantic schemas for interview session API responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricSummary(BaseModel):
    mean: float = 0.0
    min: float = 0.0
    max: float = 0.0


class SessionSummary(BaseModel):
    session_id: str
    started_at: str
    ended_at: str | None = None
    total_frames: int = 0
    duration_seconds: int = 0
    eye_contact: MetricSummary | None = None
    smile: MetricSummary | None = None
    posture: MetricSummary | None = None
    head_stability: MetricSummary | None = None
    body_movement: MetricSummary | None = None
    confidence: MetricSummary | None = None
    recommendations: list[str] = Field(default_factory=list)


class SessionDetail(BaseModel):
    session_id: str
    started_at: str
    ended_at: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    frame_count: int = 0