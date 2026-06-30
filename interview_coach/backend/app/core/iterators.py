"""Iterators — lazy traversal over vocabulary, landmarks, and sentence tokens."""

from __future__ import annotations

from typing import Iterator, List, Sequence


class VocabularyIterator:
    """Iterate over sign labels, optionally filtered by sign type."""

    def __init__(self, labels: Sequence[str], sign_type: str | None = None):
        self._labels = list(labels)
        self._sign_type = sign_type
        self._index = 0

    def __iter__(self) -> Iterator[dict]:
        return self

    def __next__(self) -> dict:
        if self._index >= len(self._labels):
            raise StopIteration
        label = self._labels[self._index]
        self._index += 1
        return {
            "label": label,
            "index": self._index - 1,
            "sign_type": self._sign_type or "unknown",
        }


class LandmarkBatchIterator:
    """Yield fixed-size batches from a landmark sequence without copying the full list."""

    def __init__(self, frames: Sequence[Sequence[float]], batch_size: int = 8):
        self._frames = frames
        self._batch_size = max(1, batch_size)
        self._cursor = 0

    def __iter__(self) -> Iterator[List[Sequence[float]]]:
        return self

    def __next__(self) -> List[Sequence[float]]:
        if self._cursor >= len(self._frames):
            raise StopIteration
        batch = self._frames[self._cursor : self._cursor + self._batch_size]
        self._cursor += self._batch_size
        return list(batch)


class SentenceTokenIterator:
    """Iterate words in an assembled sentence one at a time."""

    def __init__(self, sentence: str):
        self._tokens = [token for token in sentence.split() if token]
        self._index = 0

    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        if self._index >= len(self._tokens):
            raise StopIteration
        token = self._tokens[self._index]
        self._index += 1
        return token