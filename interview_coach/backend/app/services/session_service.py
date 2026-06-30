"""SQLite-backed interview session persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.core.singleton import SingletonMeta
from app.database.db_manager import DatabaseManager
from app.database.models import InterviewSession


class SessionService(metaclass=SingletonMeta):
    """Stores per-frame metrics and session summaries in SQLite."""

    METRICS = ("eye_contact", "smile", "posture", "head_stability", "body_movement", "confidence")

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self._db = db or DatabaseManager()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def start_session(self, session_id: str) -> dict[str, Any]:
        with self._db.get_session() as db:
            existing = db.get(InterviewSession, session_id)
            if existing:
                existing.started_at = self._now()
                existing.ended_at = None
                existing.summary_json = "{}"
                existing.frame_count = 0
                existing.frames_json = "[]"
            else:
                db.add(
                    InterviewSession(
                        id=session_id,
                        started_at=self._now(),
                        frames_json="[]",
                        summary_json="{}",
                        frame_count=0,
                    )
                )
            db.commit()
        return {"session_id": session_id, "started_at": self._now(), "state": "started"}

    def append_frame(self, session_id: str, frame_result: dict[str, Any]) -> None:
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
        with self._db.get_session() as db:
            record = db.get(InterviewSession, session_id)
            if record is None:
                return {"error": "Session not found"}
            record.ended_at = self._now()
            record.summary_json = json.dumps(summary)
            record.frame_count = summary.get("total_frames", record.frame_count)
            db.commit()
            return {
                "session_id": session_id,
                "started_at": record.started_at,
                "ended_at": record.ended_at,
                "summary": summary,
            }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._db.get_session() as db:
            record = db.get(InterviewSession, session_id)
            if record is None:
                return None
            return {
                "session_id": record.id,
                "started_at": record.started_at,
                "ended_at": record.ended_at,
                "frame_count": record.frame_count,
                "summary": json.loads(record.summary_json or "{}"),
                "frames": json.loads(record.frames_json or "[]"),
            }

    def build_summary(self, session_id: str, fps: int = 15) -> dict[str, Any]:
        data = self.get_session(session_id)
        if not data:
            return {"error": "Session not found"}

        frames = data.get("frames", [])
        if not frames:
            return {"error": "No frames received"}

        summary: dict[str, Any] = {}
        for metric in self.METRICS:
            values = [f[metric] for f in frames if metric in f]
            summary[metric] = {
                "mean": round(float(np.mean(values)), 3) if values else 0.0,
                "min": round(float(np.min(values)), 3) if values else 0.0,
                "max": round(float(np.max(values)), 3) if values else 0.0,
            }

        last_feedback = frames[-1].get("feedback", {})
        summary["recommendations"] = last_feedback.get("recommendations", [])
        summary["total_frames"] = len(frames)
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
                    "session_id": row.id,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                    "frame_count": row.frame_count,
                }
                for row in rows
            ]