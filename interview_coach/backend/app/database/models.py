from sqlalchemy import BLOB, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    preferred_voice: Mapped[str] = mapped_column(String(20), default="female")
    face_embedding: Mapped[bytes | None] = mapped_column(BLOB, nullable=True)
    created_at: Mapped[str] = mapped_column(Text)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    frames_json: Mapped[str] = mapped_column(Text, default="[]")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    frame_count: Mapped[int] = mapped_column(Integer, default=0)


class UserProfile(Base):
    """Persistent per-user neutral baseline and camera-offset calibration.

    baseline_json  — median metric values from completed calibration sessions
                     e.g. {"eye_contact": 0.82, "smile": 0.12, ...}
    camera_offset_json — per-user camera-above-screen pitch offset (degrees)
                     e.g. {"pitch_deg": -8.5}
    session_count  — number of completed sessions contributing to the baseline
    updated_at     — ISO timestamp of last update
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    baseline_json: Mapped[str] = mapped_column(Text, default="{}")
    camera_offset_json: Mapped[str] = mapped_column(Text, default="{}")
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(Text, default="")