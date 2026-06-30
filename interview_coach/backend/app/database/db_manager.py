"""Database manager — Singleton for SQLite access."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.singleton import SingletonMeta
from app.database.models import Base, User


class DatabaseManager(metaclass=SingletonMeta):
    def __init__(self, database_url: str | None = None):
        settings = get_settings()
        self.database_url = database_url or settings.database.get("url", "sqlite:///./interview_coach.db")
        self.engine = create_engine(self.database_url, echo=settings.database.get("echo", False))
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def create_user(self, name: str, preferred_voice: str = "female") -> User:
        with self.get_session() as session:
            user = User(
                name=name,
                preferred_voice=preferred_voice,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def list_users(self) -> list[User]:
        with self.get_session() as session:
            return list(session.query(User).all())