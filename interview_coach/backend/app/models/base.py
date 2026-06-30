"""OOP base classes for recognizers and model artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generator, Optional


@dataclass
class PredictionResult:
    label: str
    confidence: float
    sign_type: str
    source: str = "model"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "sign_type": self.sign_type,
            "source": self.source,
            "metadata": self.metadata,
        }


class BaseRecognizer(ABC):
    """Abstract recognizer — concrete classes implement static/dynamic/mock paths."""

    def __init__(self, *, mode: str = "mock", confidence_threshold: float = 0.7, **options: Any):
        self.mode = mode
        self.confidence_threshold = confidence_threshold
        self.options = options

    @abstractmethod
    def predict(self, features: Any, /, *args, sign_type: str = "dynamic", **kwargs) -> PredictionResult:
        """Positional `features` plus optional keyword configuration per call."""

    @abstractmethod
    def is_ready(self) -> bool:
        raise NotImplementedError

    def predict_stream(self, feature_batches, /, **stream_options) -> Generator[PredictionResult, None, None]:
        """Generator — yield one prediction per batch."""
        for batch in feature_batches:
            yield self.predict(batch, **stream_options)