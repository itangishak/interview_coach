"""Facade that routes predictions to mock or real recognizers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.core.decorators import timed
from app.models.base import BaseRecognizer, PredictionResult
from app.services.mock_recognizer import MockRecognizer
from app.services.sentence_assembler import SentenceAssembler


class PredictionService:
    """OOP service object coordinating recognizer + sentence assembly."""

    def __init__(
        self,
        recognizer: Optional[BaseRecognizer] = None,
        sentence_assembler: Optional[SentenceAssembler] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.recognizer = recognizer or MockRecognizer(
            mode="mock",
            confidence_threshold=self.settings.recognition.dynamic_confidence,
        )
        self.sentence = sentence_assembler or SentenceAssembler()
        self.mode = "demo" if self.settings.demo_mode else "live"

    @classmethod
    def from_settings(cls, settings: Settings | None = None, **kwargs: Any) -> "PredictionService":
        settings = settings or get_settings()
        recognizer = MockRecognizer(
            confidence_threshold=settings.recognition.dynamic_confidence,
            mode="mock" if settings.demo_mode else "live",
        )
        return cls(recognizer=recognizer, settings=settings, **kwargs)

    def status(self) -> dict[str, Any]:
        dynamic_ckpt = Path(self.settings.paths.get("checkpoints_dynamic", "./checkpoints/dynamic")) / "model.pt"
        static_ckpt = Path(self.settings.paths.get("checkpoints_static", "./checkpoints/static")) / "model.pt"
        return {
            "mode": self.mode,
            "demo_mode": self.settings.demo_mode,
            "recognizer_ready": self.recognizer.is_ready(),
            "checkpoints": {
                "dynamic": dynamic_ckpt.exists(),
                "static": static_ckpt.exists(),
            },
            "app": self.settings.app.model_dump(),
            "sentence": self.sentence.text,
        }

    @timed
    def predict_and_assemble(
        self,
        features,
        /,
        *,
        sign_type: str = "dynamic",
        append_to_sentence: bool = True,
        **predict_kwargs: Any,
    ) -> dict[str, Any]:
        result = self.recognizer.predict(features, sign_type=sign_type, **predict_kwargs)
        sentence = self.sentence.text
        if append_to_sentence and result.confidence >= self.recognizer.confidence_threshold:
            sentence = self.sentence.add_sign(result.label)
        payload = result.as_dict()
        payload["sentence"] = sentence
        payload["demo_mode"] = self.settings.demo_mode
        return payload