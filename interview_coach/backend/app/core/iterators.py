"""Custom iterators and generators for the interview-coach backend.

Demonstrates:
  - Iterator protocol (__iter__ / __next__ with StopIteration)
  - Generator function (yield)
  - Generator expression
  - __len__, __repr__, __getitem__ (sequence protocol)
  - Keyword-only and positional parameters
  - Dataclass used as iterator item container
  - Global and local variable scoping
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Generator, Iterator


# ── Dataclass — item yielded by FrameWindowIterator ──────────────────────────
@dataclass(slots=True)
class FrameWindow:
    """A slice of consecutive analysis frames with summary statistics.

    Attributes
    ----------
    frames    : list of raw frame dicts
    start_idx : first absolute frame index in session
    mean      : pre-computed mean confidence for the window
    """
    frames:    list[dict[str, Any]]
    start_idx: int
    mean:      float = field(init=False)

    def __post_init__(self) -> None:
        confs = [f.get("confidence", 0.0) for f in self.frames]
        # Local variable — does not shadow any outer name
        self.mean = sum(confs) / len(confs) if confs else 0.0

    def __repr__(self) -> str:
        return (
            f"FrameWindow(start={self.start_idx}, "
            f"n={len(self.frames)}, mean_conf={self.mean:.1f})"
        )


# ── Iterator — slides a fixed window over a frame list ───────────────────────
class FrameWindowIterator:
    """Sliding-window iterator over a list of analysis frame dicts.

    Demonstrates the iterator protocol (__iter__ / __next__).

    Parameters (positional-or-keyword)
    ----------
    frames     : full list of frame result dicts
    window_size: number of frames per window (positional-or-keyword)

    Keyword-only
    ------------
    step : stride between windows (default = window_size → non-overlapping)
    """

    def __init__(
        self,
        frames: list[dict[str, Any]],
        window_size: int,
        *,
        step: int | None = None,
    ) -> None:
        self._frames      = frames
        self._window_size = window_size
        self._step        = step if step is not None else window_size
        self._pos         = 0          # local instance state

    # Iterator protocol
    def __iter__(self) -> "FrameWindowIterator":
        self._pos = 0
        return self

    def __next__(self) -> FrameWindow:
        if self._pos + self._window_size > len(self._frames):
            raise StopIteration
        window = FrameWindow(
            frames=self._frames[self._pos : self._pos + self._window_size],
            start_idx=self._pos,
        )
        self._pos += self._step
        return window

    # Sequence helpers
    def __len__(self) -> int:
        if len(self._frames) < self._window_size:
            return 0
        return (len(self._frames) - self._window_size) // self._step + 1

    def __repr__(self) -> str:
        return (
            f"FrameWindowIterator(total_frames={len(self._frames)}, "
            f"window={self._window_size}, step={self._step}, "
            f"windows={len(self)})"
        )


# ── Iterator — iterates over tokens in a sentence string ─────────────────────
class SentenceTokenIterator:
    """Iterates word-by-word over a sentence string.

    Demonstrates __iter__ / __next__ / __len__ / __getitem__.
    """

    def __init__(self, sentence: str, /, *, sep: str = " ") -> None:
        # Positional-only: sentence (note the / in signature)
        self._tokens: list[str] = [t for t in sentence.split(sep) if t]
        self._idx: int = 0

    def __iter__(self) -> "SentenceTokenIterator":
        self._idx = 0
        return self

    def __next__(self) -> str:
        if self._idx >= len(self._tokens):
            raise StopIteration
        token = self._tokens[self._idx]
        self._idx += 1
        return token

    def __len__(self) -> int:
        return len(self._tokens)

    def __getitem__(self, idx: int) -> str:
        return self._tokens[idx]

    def __repr__(self) -> str:
        return f"SentenceTokenIterator(tokens={self._tokens!r})"


# ── Generator function — yields metric history snapshots ─────────────────────
def metric_history_generator(
    frames: list[dict[str, Any]],
    metric: str,
    /,
    *,
    skip_excluded: bool = True,
) -> Generator[tuple[int, float], None, None]:
    """Generator that yields (frame_index, metric_value) pairs.

    Positional-only: frames, metric.
    Keyword-only:    skip_excluded.

    Uses 'yield' — each call resumes from where it paused (lazy evaluation).
    """
    for idx, frame in enumerate(frames):
        if skip_excluded and frame.get("excluded", False):
            continue
        value = frame.get(metric)
        if value is not None:
            yield idx, float(value)    # generator: suspends here each iteration


# ── Generator function — chunked frame sender for WebSocket replay ────────────
def frame_chunk_generator(
    frames: list[dict[str, Any]],
    chunk_size: int = 10,
) -> Generator[list[dict[str, Any]], None, None]:
    """Yield frames in chunks of chunk_size.

    Demonstrates generator with local variable and early termination.
    """
    total = len(frames)
    start = 0                          # local variable
    while start < total:
        end = min(start + chunk_size, total)
        yield frames[start:end]        # generator yield
        start = end


# ── Generator expression helper — exposed as a utility ───────────────────────
def confidence_values(
    frames: list[dict[str, Any]],
    /,
    *,
    valid_only: bool = True,
) -> list[float]:
    """Return confidence values as a list.

    Uses a generator expression (not a full function) internally.

    Positional-only: frames.
    Keyword-only:    valid_only.
    """
    # Generator expression — lazy sequence comprehension
    gen = (
        float(f["confidence"])
        for f in frames
        if "confidence" in f and (not valid_only or not f.get("excluded", False))
    )
    return list(gen)
