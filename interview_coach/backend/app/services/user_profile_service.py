"""Persistent per-user baseline and camera-offset profiles.

Demonstrates:
  - Singleton metaclass
  - __repr__, __str__, __len__
  - @property (profile_count)
  - Keyword-only parameters
  - Dataclass (UserProfileData) for typed returns
  - Generator (iter_profiles)
  - Global module constants (_BASELINE_BLEND, _FEATURE_NAMES)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator

import numpy as np

from app.core.singleton import SingletonMeta
from app.database.db_manager import DatabaseManager
from app.database.models import UserProfile

# ── Module-level (global namespace) constants ─────────────────────────────────
_BASELINE_BLEND: float = 0.30   # α: new session contributes 30% of updated baseline
_FEATURE_NAMES: tuple[str, ...] = (
    "eye_contact", "smile", "posture", "head_stability", "body_movement",
)


# ── Dataclass — typed return value ────────────────────────────────────────────
@dataclass(slots=True)
class UserProfileData:
    """Typed container for a user's persisted profile.

    Demonstrates dataclass with __post_init__ validation.
    """
    user_id:           str
    baseline:          dict[str, float] = field(default_factory=dict)
    camera_offset_deg: float            = 0.0
    session_count:     int              = 0

    def __post_init__(self) -> None:
        # Validate camera offset is a real number in a sensible range
        if not (-90.0 <= self.camera_offset_deg <= 90.0):
            raise ValueError(f"camera_offset_deg out of range: {self.camera_offset_deg}")

    def __repr__(self) -> str:
        return (
            f"UserProfileData(user={self.user_id!r}, "
            f"sessions={self.session_count}, "
            f"offset={self.camera_offset_deg}°)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline":          self.baseline,
            "camera_offset_deg": self.camera_offset_deg,
            "session_count":     self.session_count,
        }


class UserProfileService(metaclass=SingletonMeta):
    """CRUD wrapper around UserProfile rows.

    Demonstrates:
      - Singleton metaclass
      - @property (profile_count)
      - Generator method (iter_profiles)
      - __repr__, __str__, __len__
      - Keyword-only parameter in update_camera_offset
    """

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self._db: DatabaseManager = db or DatabaseManager()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── @property ─────────────────────────────────────────────────────
    @property
    def profile_count(self) -> int:
        """Total number of user profiles stored in the database."""
        with self._db.get_session() as db:
            return db.query(UserProfile).count()

    # ── Read ─────────────────────────────────────────────────────────
    def get_profile(self, user_id: str) -> dict[str, Any]:
        """Return the profile for user_id, or empty defaults if not found."""
        with self._db.get_session() as db:
            row = db.get(UserProfile, user_id)
            if row is None:
                return {"baseline": {}, "camera_offset_deg": 0.0, "session_count": 0}
            return {
                "baseline": json.loads(row.baseline_json or "{}"),
                "camera_offset_deg": json.loads(row.camera_offset_json or "{}").get("pitch_deg", 0.0),
                "session_count": row.session_count,
            }

    def get_profile_typed(self, user_id: str, /) -> UserProfileData:
        """Return a typed UserProfileData object (positional-only: user_id)."""
        raw = self.get_profile(user_id)
        return UserProfileData(
            user_id           = user_id,
            baseline          = raw["baseline"],
            camera_offset_deg = float(raw["camera_offset_deg"]),
            session_count     = int(raw["session_count"]),
        )

    # ── Generator method ──────────────────────────────────────────────
    def iter_profiles(self) -> Generator[UserProfileData, None, None]:
        """Generator: yield each stored profile as a typed UserProfileData.

        Demonstrates generator method using yield.
        """
        with self._db.get_session() as db:
            rows = db.query(UserProfile).all()
        for row in rows:
            yield UserProfileData(
                user_id           = row.user_id,
                baseline          = json.loads(row.baseline_json or "{}"),
                camera_offset_deg = json.loads(row.camera_offset_json or "{}").get("pitch_deg", 0.0),
                session_count     = row.session_count or 0,
            )

    # ── Write ─────────────────────────────────────────────────────────
    def update_baseline(self, user_id: str, new_baseline: dict[str, float]) -> None:
        """Blend a new session baseline into the stored rolling average (EMA)."""
        with self._db.get_session() as db:
            row = db.get(UserProfile, user_id)
            if row is None:
                row = UserProfile(
                    user_id            = user_id,
                    baseline_json      = json.dumps(new_baseline),
                    camera_offset_json = "{}",
                    session_count      = 1,
                    updated_at         = self._now(),
                )
                db.add(row)
            else:
                stored = json.loads(row.baseline_json or "{}")
                if not stored:
                    merged = new_baseline
                else:
                    merged: dict[str, float] = {}
                    for k in _FEATURE_NAMES:
                        old = stored.get(k)
                        new = new_baseline.get(k)
                        if old is None and new is None:
                            continue
                        elif old is None:
                            merged[k] = float(new)          # type: ignore[arg-type]
                        elif new is None:
                            merged[k] = float(old)
                        else:
                            merged[k] = round(
                                (1.0 - _BASELINE_BLEND) * float(old) + _BASELINE_BLEND * float(new),
                                4,
                            )
                row.baseline_json = json.dumps(merged)
                row.session_count = (row.session_count or 0) + 1
                row.updated_at    = self._now()
            db.commit()

    def update_camera_offset(
        self,
        user_id: str,
        /,
        *,
        pitch_deg: float,
    ) -> None:
        """Store or update the camera pitch offset.

        Positional-only: user_id.
        Keyword-only: pitch_deg.
        """
        with self._db.get_session() as db:
            row = db.get(UserProfile, user_id)
            if row is None:
                row = UserProfile(
                    user_id            = user_id,
                    baseline_json      = "{}",
                    camera_offset_json = json.dumps({"pitch_deg": round(pitch_deg, 2)}),
                    session_count      = 0,
                    updated_at         = self._now(),
                )
                db.add(row)
            else:
                row.camera_offset_json = json.dumps({"pitch_deg": round(pitch_deg, 2)})
                row.updated_at         = self._now()
            db.commit()

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return list of all profiles as plain dicts (REST response)."""
        return [p.to_dict() | {"user_id": p.user_id} for p in self.iter_profiles()]

    # ── Dunder methods ────────────────────────────────────────────────
    def __repr__(self) -> str:
        return f"UserProfileService(profiles={self.profile_count})"

    def __str__(self) -> str:
        return f"UserProfileService — {self.profile_count} user profile(s) stored"

    def __len__(self) -> int:
        return self.profile_count
