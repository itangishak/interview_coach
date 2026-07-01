"""SQLite-backed interview session persistence.

Demonstrates:
  - Singleton metaclass
  - Generator (frame_windows generator method)
  - Iterator usage (FrameWindowIterator)
  - @property (frame_count, duration_seconds)
  - contextmanager for session lifecycle
  - __repr__, __str__, __len__
  - Keyword-only and positional-or-keyword parameters
  - Class-level constant (METRICS)
  - Dataclass (SessionMetrics)
  - Global module variable (_METRIC_KEYS)
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator

import numpy as np
from sqlalchemy.orm import Session

from app.core.iterators import (
    FrameWindow,
    FrameWindowIterator,
    confidence_values,
    metric_history_generator,
)
from app.core.singleton import SingletonMeta
from app.database.db_manager import DatabaseManager
from app.database.models import InterviewSession

# ── Module-level (global namespace) tuple of metric keys ─────────────────────
_METRIC_KEYS: tuple[str, ...] = (
    "eye_contact", "smile", "posture", "head_stability", "body_movement", "confidence",
)


# ── Dataclass — typed session metrics summary ─────────────────────────────────
@dataclass
class SessionMetrics:
    """Aggregated statistics for one session metric.

    Demonstrates dataclass with computed default_factory and __post_init__.
    """
    metric:        str
    values:        list[float] = field(default_factory=list)
    mean:          float       = field(init=False, default=0.0)
    minimum:       float       = field(init=False, default=0.0)
    maximum:       float       = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        if self.values:
            arr = np.array(self.values, dtype=float)
            self.mean    = round(float(arr.mean()), 3)
            self.minimum = round(float(arr.min()),  3)
            self.maximum = round(float(arr.max()),  3)

    def to_dict(self) -> dict[str, float]:
        return {"mean": self.mean, "min": self.minimum, "max": self.maximum}

    def __repr__(self) -> str:
        return (
            f"SessionMetrics({self.metric}: "
            f"mean={self.mean:.3f}, min={self.minimum:.3f}, max={self.maximum:.3f})"
        )

    def __len__(self) -> int:
        return len(self.values)


class SessionService(metaclass=SingletonMeta):
    """Stores per-frame metrics and session summaries in SQLite.

    Demonstrates:
      - Singleton metaclass
      - @property
      - contextmanager (session_scope)
      - Generator method (frame_windows)
      - __repr__, __str__, __len__
      - Keyword-only init parameter
    """

    METRICS: tuple[str, ...] = _METRIC_KEYS   # class-level constant

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self._db: DatabaseManager = db or DatabaseManager()
        # Instance attribute: in-memory frame buffer keyed by session_id
        self._frame_buffers: dict[str, list[dict[str, Any]]] = {}

    # ── @property ─────────────────────────────────────────────────────
    @property
    def active_sessions(self) -> int:
        """Number of sessions currently buffered in memory."""
        return len(self._frame_buffers)

    # ── contextmanager — wraps the whole start→stop lifecycle ─────────
    @contextmanager
    def session_scope(
        self, session_id: str, /, *, fps: int = 15
    ) -> Generator[str, None, None]:
        """Context manager: auto-starts and ends a session.

        Positional-only: session_id.
        Keyword-only: fps.

        Usage
        -----
        with service.session_scope("sid") as sid:
            service.append_frame(sid, result)
        # session ended automatically
        """
        self.start_session(session_id)
        try:
            yield session_id
        finally:
            summary = self.build_summary(session_id, fps=fps)
            self.end_session(session_id, summary)

    def _now(self) -> str:
        """Return current UTC timestamp as ISO-8601 string (local helper)."""
        return datetime.now(timezone.utc).isoformat()

    def start_session(self, session_id: str) -> dict[str, Any]:
        self._frame_buffers[session_id] = []
        with self._db.get_session() as db:
            existing = db.get(InterviewSession, session_id)
            if existing:
                existing.started_at  = self._now()
                existing.ended_at    = None
                existing.summary_json = "{}"
                existing.frame_count  = 0
                existing.frames_json  = "[]"
            else:
                db.add(InterviewSession(
                    id=session_id,
                    started_at=self._now(),
                    frames_json="[]",
                    summary_json="{}",
                    frame_count=0,
                ))
            db.commit()
        return {"session_id": session_id, "started_at": self._now(), "state": "started"}

    def append_frame(self, session_id: str, frame_result: dict[str, Any]) -> None:
        # Update in-memory buffer first (fast path)
        if session_id in self._frame_buffers:
            self._frame_buffers[session_id].append(frame_result)

        with self._db.get_session() as db:
            record = db.get(InterviewSession, session_id)
            if record is None:
                return
            frames = json.loads(record.frames_json or "[]")
            frames.append(frame_result)
            record.frames_json = json.dumps(frames)
            record.frame_count = len(frames)
            db.commit()

    def end_session(self, session_id: str, summary: dict[str, Any]) -> dict[str, Any]:
        self._frame_buffers.pop(session_id, None)
        with self._db.get_session() as db:
            record = db.get(InterviewSession, session_id)
            if record is None:
                return {"error": "Session not found"}
            record.ended_at     = self._now()
            record.summary_json = json.dumps(summary)
            record.frame_count  = summary.get("total_frames", record.frame_count)
            db.commit()
            return {
                "session_id": session_id,
                "started_at": record.started_at,
                "ended_at":   record.ended_at,
                "summary":    summary,
            }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._db.get_session() as db:
            record = db.get(InterviewSession, session_id)
            if record is None:
                return None
            return {
                "session_id":  record.id,
                "started_at":  record.started_at,
                "ended_at":    record.ended_at,
                "frame_count": record.frame_count,
                "summary":     json.loads(record.summary_json or "{}"),
                "frames":      json.loads(record.frames_json or "[]"),
            }

    # ── Generator method — yields FrameWindow objects ─────────────────
    def frame_windows(
        self,
        session_id: str,
        /,
        window_size: int = 30,
        *,
        step: int | None = None,
        valid_only: bool = True,
    ) -> Generator[FrameWindow, None, None]:
        """Yield sliding windows over session frames.

        Positional-only: session_id.
        Positional-or-keyword: window_size.
        Keyword-only: step, valid_only.

        Demonstrates generator method using FrameWindowIterator (iterator pattern).
        """
        data = self.get_session(session_id)
        if not data:
            return                # empty generator — no StopIteration needed
        frames = data["frames"]
        if valid_only:
            frames = [f for f in frames if not f.get("excluded", False)]

        iterator = FrameWindowIterator(frames, window_size, step=step)
        for window in iterator:     # uses __iter__ / __next__
            yield window            # generator yield

    def build_summary(self, session_id: str, fps: int = 15) -> dict[str, Any]:
        """Aggregate frames into session summary statistics.

        Uses SessionMetrics dataclass and generator utility functions.
        """
        data = self.get_session(session_id)
        if not data:
            return {"error": "Session not found"}

        frames = data.get("frames", [])
        if not frames:
            return {"error": "No frames received"}

        valid_frames = [f for f in frames if not f.get("excluded", False)]
        agg_frames   = valid_frames if valid_frames else frames

        summary: dict[str, Any] = {}
        for metric in self.METRICS:
            # Build SessionMetrics dataclass (uses __post_init__ for stats)
            sm = SessionMetrics(
                metric=metric,
                values=[f[metric] for f in agg_frames if metric in f],
            )
            summary[metric] = sm.to_dict()

        summary["valid_frame_count"]    = len(valid_frames)
        summary["excluded_frame_count"] = len(frames) - len(valid_frames)

        # Use generator utility to compute confidence distribution
        conf_vals = confidence_values(frames, valid_only=True)
        summary["confidence_p25"] = float(np.percentile(conf_vals, 25)) if conf_vals else 0.0
        summary["confidence_p75"] = float(np.percentile(conf_vals, 75)) if conf_vals else 0.0

        last_feedback = frames[-1].get("feedback", {})
        summary["recommendations"] = last_feedback.get("recommendations", [])
        summary["total_frames"]     = len(frames)
        summary["duration_seconds"] = len(frames) // max(fps, 1)
        return summary

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._db.get_session() as db:
            rows = (
                db.query(InterviewSession)
                .order_by(InterviewSession.started_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "session_id":  row.id,
                    "started_at":  row.started_at,
                    "ended_at":    row.ended_at,
                    "frame_count": row.frame_count,
                }
                for row in rows
            ]

    # ── Dunder methods ────────────────────────────────────────────────
    def __repr__(self) -> str:
        return f"SessionService(active_buffered={self.active_sessions})"

    def __str__(self) -> str:
        return f"SessionService — {self.active_sessions} session(s) in flight"

    def __len__(self) -> int:
        """Number of sessions currently buffered (supports len(service))."""
        return self.active_sessions
