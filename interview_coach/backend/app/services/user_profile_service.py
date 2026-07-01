"""Persistent per-user baseline and camera-offset profiles.

Why this exists
---------------
The 2-second in-session calibration (Flaw E fix) only lasts one session.
This service persists the baseline across sessions so the analyzer can load
a prior baseline immediately, without requiring the user to sit still for 2 s
every time.

It also stores a per-user camera-above-screen pitch offset (degrees).
The webcam typically sits 8-12° above the centre of the monitor, so genuine
eye contact with the on-screen interviewer is geometrically "looking slightly
down." Without compensation, the iris metric penalizes this correct behavior.
The offset is estimated during calibration when the user is asked to look
directly at the interviewer's face on screen, and stored here.

API
---
get_profile(user_id)           → dict with "baseline" and "camera_offset_deg"
update_baseline(user_id, ...)  → merge new session baseline into rolling average
update_camera_offset(user_id, pitch_deg)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.core.singleton import SingletonMeta
from app.database.db_manager import DatabaseManager
from app.database.models import UserProfile

# Exponential smoothing weight for merging new baselines into the stored one.
# α=0.3 means the new session contributes 30 % of the updated baseline.
_BASELINE_BLEND = 0.30

_FEATURE_NAMES = ["eye_contact", "smile", "posture", "head_stability", "body_movement"]


class UserProfileService(metaclass=SingletonMeta):
    """CRUD wrapper around UserProfile rows."""

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self._db = db or DatabaseManager()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Read ─────────────────────────────────────────────────────────
    def get_profile(self, user_id: str) -> dict[str, Any]:
        """Return the profile for user_id, or empty defaults if not found."""
        with self._db.get_session() as db:
            row = db.get(UserProfile, user_id)
            if row is None:
                return {
                    "baseline": {},
                    "camera_offset_deg": 0.0,
                    "session_count": 0,
                }
            return {
                "baseline": json.loads(row.baseline_json or "{}"),
                "camera_offset_deg": json.loads(row.camera_offset_json or "{}").get(
                    "pitch_deg", 0.0
                ),
                "session_count": row.session_count,
            }

    # ── Write ────────────────────────────────────────────────────────
    def update_baseline(
        self, user_id: str, new_baseline: dict[str, float]
    ) -> None:
        """Blend a new session baseline into the stored rolling average.

        On first call: stored = new_baseline.
        On subsequent calls: stored = (1-α)*stored + α*new  (EMA blend).
        This means the long-term profile evolves gradually rather than
        jumping to whatever the latest session looked like.
        """
        with self._db.get_session() as db:
            row = db.get(UserProfile, user_id)
            if row is None:
                row = UserProfile(
                    user_id=user_id,
                    baseline_json=json.dumps(new_baseline),
                    camera_offset_json="{}",
                    session_count=1,
                    updated_at=self._now(),
                )
                db.add(row)
            else:
                stored = json.loads(row.baseline_json or "{}")
                if not stored:
                    # No prior baseline — use the new one directly
                    merged = new_baseline
                else:
                    merged = {}
                    for k in _FEATURE_NAMES:
                        old = stored.get(k)
                        new = new_baseline.get(k)
                        if old is None and new is None:
                            continue
                        elif old is None:
                            merged[k] = float(new)   # type: ignore[arg-type]
                        elif new is None:
                            merged[k] = float(old)
                        else:
                            merged[k] = round(
                                (1.0 - _BASELINE_BLEND) * float(old)
                                + _BASELINE_BLEND * float(new),
                                4,
                            )
                row.baseline_json = json.dumps(merged)
                row.session_count = (row.session_count or 0) + 1
                row.updated_at = self._now()
            db.commit()

    def update_camera_offset(self, user_id: str, pitch_deg: float) -> None:
        """Store or update the camera pitch offset for a user."""
        with self._db.get_session() as db:
            row = db.get(UserProfile, user_id)
            if row is None:
                row = UserProfile(
                    user_id=user_id,
                    baseline_json="{}",
                    camera_offset_json=json.dumps({"pitch_deg": round(pitch_deg, 2)}),
                    session_count=0,
                    updated_at=self._now(),
                )
                db.add(row)
            else:
                row.camera_offset_json = json.dumps({"pitch_deg": round(pitch_deg, 2)})
                row.updated_at = self._now()
            db.commit()

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._db.get_session() as db:
            rows = db.query(UserProfile).all()
            return [
                {
                    "user_id": r.user_id,
                    "session_count": r.session_count,
                    "updated_at": r.updated_at,
                    "baseline": json.loads(r.baseline_json or "{}"),
                    "camera_offset_deg": json.loads(
                        r.camera_offset_json or "{}"
                    ).get("pitch_deg", 0.0),
                }
                for r in rows
            ]
