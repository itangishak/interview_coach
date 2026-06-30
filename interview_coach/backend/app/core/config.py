"""Application configuration — Singleton + Descriptor pattern."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.core.descriptors import BoundedFloat, PositiveInt
from app.core.singleton import SingletonMeta


class AppSettings(BaseModel):
    name: str = "AI Interview Coach"
    version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000


class InterviewSettings:
    """Validated interview analysis thresholds."""

    window_size = PositiveInt(30)
    target_fps = PositiveInt(15)
    eye_contact_good = BoundedFloat(0.0, 1.0)
    smile_good = BoundedFloat(0.0, 1.0)

    def __init__(
        self,
        window_size: int = 30,
        target_fps: int = 15,
        eye_contact_good: float = 0.7,
        smile_good: float = 0.4,
    ):
        self.window_size = window_size
        self.target_fps = target_fps
        self.eye_contact_good = eye_contact_good
        self.smile_good = smile_good


class Settings(metaclass=SingletonMeta):
    """Singleton settings loader — one shared config for the whole app."""

    def __init__(self, config_path: str | Path | None = None):
        root = Path(__file__).resolve().parents[2]
        self.config_path = Path(config_path) if config_path else root / "config.yaml"
        self._raw: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        with open(self.config_path, "r", encoding="utf-8") as handle:
            self._raw = yaml.safe_load(handle) or {}

        app_cfg = self._raw.get("app", {})
        self.app = AppSettings(**app_cfg)

        interview_cfg = self._raw.get("interview", {})
        self.interview = InterviewSettings(
            window_size=interview_cfg.get("window_size", 30),
            target_fps=interview_cfg.get("target_fps", 15),
            eye_contact_good=interview_cfg.get("eye_contact_good", 0.7),
            smile_good=interview_cfg.get("smile_good", 0.4),
        )

        self.mediapipe = self._raw.get("mediapipe", {})
        self.database = self._raw.get("database", {})
        self.paths = self._raw.get("paths", {})
        self.calibration_available = self._calibration_available()

    def _calibration_available(self) -> bool:
        interview_dir = Path(self.paths.get("checkpoints_interview", "./checkpoints/interview"))
        return (interview_dir / "confidence_model.pt").exists()


def get_settings(*, config_path: str | Path | None = None, **overrides: Any) -> Settings:
    """Factory with optional keyword overrides for tests and scripts."""
    settings = Settings(config_path=config_path)
    for key, value in overrides.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    return settings