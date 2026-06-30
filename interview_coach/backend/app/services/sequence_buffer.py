"""Rolling temporal buffer for dynamic sign sequences."""

from __future__ import annotations

from collections import deque
from typing import Deque, Iterable, List

import numpy as np

from app.core.iterators import LandmarkBatchIterator


class SequenceBuffer:
    def __init__(self, max_frames: int = 40, motion_threshold: float = 0.02, pause_frames: int = 10):
        self.max_frames = max_frames
        self.motion_threshold = motion_threshold
        self.pause_frames = pause_frames
        self._frames: Deque[np.ndarray] = deque(maxlen=max_frames)
        self._pause_counter = 0

    def add_frame(self, landmarks: Iterable[float]) -> None:
        frame = np.asarray(landmarks, dtype=np.float32)
        self._frames.append(frame)
        motion = self._estimate_motion(frame)
        if motion < self.motion_threshold:
            self._pause_counter += 1
        else:
            self._pause_counter = 0

    def _estimate_motion(self, frame: np.ndarray) -> float:
        if not self._frames:
            return 1.0
        previous = self._frames[-1]
        return float(np.mean(np.abs(frame - previous)))

    def is_ready_for_prediction(self) -> bool:
        return len(self._frames) >= self.max_frames // 2 and self._pause_counter >= self.pause_frames

    def as_array(self) -> np.ndarray:
        if not self._frames:
            return np.zeros((0, 0), dtype=np.float32)
        return np.stack(list(self._frames), axis=0)

    def batches(self, batch_size: int = 8) -> LandmarkBatchIterator:
        return LandmarkBatchIterator(self._frames, batch_size=batch_size)

    def clear(self) -> None:
        self._frames.clear()
        self._pause_counter = 0