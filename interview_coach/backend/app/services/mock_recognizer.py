"""Mock recognizer for demo mode while real checkpoints are training."""

from __future__ import annotations

import itertools
import random
import time
from typing import Any, Generator, Iterable

from app.core.decorators import log_inference, timed
from app.core.iterators import VocabularyIterator
from app.models.base import BaseRecognizer, PredictionResult
from app.utils.constants import DEMO_DYNAMIC_SIGNS, DEMO_STATIC_SIGNS


class MockRecognizer(BaseRecognizer):
    """Cycles through demo vocabulary to keep the UI alive during training."""

    def __init__(
        self,
        dynamic_labels: Iterable[str] | None = None,
        static_labels: Iterable[str] | None = None,
        *,
        mode: str = "mock",
        confidence_threshold: float = 0.7,
        **options: Any,
    ):
        super().__init__(mode=mode, confidence_threshold=confidence_threshold, **options)
        self._dynamic_labels = list(dynamic_labels or DEMO_DYNAMIC_SIGNS)
        self._static_labels = list(static_labels or DEMO_STATIC_SIGNS)
        self._dynamic_cycle = itertools.cycle(self._dynamic_labels)
        self._static_cycle = itertools.cycle(self._static_labels)

    def is_ready(self) -> bool:
        return True

    @timed
    @log_inference
    def predict(self, features: Any, /, *args, sign_type: str = "dynamic", **kwargs) -> PredictionResult:
        label = next(self._dynamic_cycle if sign_type == "dynamic" else self._static_cycle)
        confidence = round(random.uniform(self.confidence_threshold, 0.98), 2)
        return PredictionResult(
            label=label,
            confidence=confidence,
            sign_type=sign_type,
            source="mock",
            metadata={"features_received": features is not None, **kwargs},
        )

    def demo_stream(self, *, every_seconds: float = 2.5, max_items: int | None = None, **labels) -> Generator[PredictionResult, None, None]:
        """Generator — periodic demo predictions for WebSocket clients."""
        dynamic = list(labels.get("dynamic_labels", self._dynamic_labels))
        static = list(labels.get("static_labels", self._static_labels))
        merged = [("dynamic", label) for label in dynamic] + [("static", label) for label in static]
        random.shuffle(merged)

        count = 0
        for sign_type, label in itertools.cycle(merged):
            yield PredictionResult(
                label=label,
                confidence=round(random.uniform(0.72, 0.96), 2),
                sign_type=sign_type,
                source="mock-stream",
            )
            count += 1
            if max_items is not None and count >= max_items:
                break
            time.sleep(every_seconds)

    def vocabulary(self, sign_type: str | None = None) -> VocabularyIterator:
        labels = self._dynamic_labels if sign_type == "dynamic" else self._static_labels
        if sign_type is None:
            labels = self._dynamic_labels + self._static_labels
        return VocabularyIterator(labels, sign_type=sign_type)