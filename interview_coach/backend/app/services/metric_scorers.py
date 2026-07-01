"""Metric scorer class hierarchy for the interview coach.

Demonstrates:
  - Abstract Base Class (ABC / abstractmethod)
  - Inheritance (FaceMetricScorer, PoseMetricScorer extend BaseMetricScorer)
  - Polymorphism (each subclass overrides score())
  - OOP: class attributes, instance attributes, properties
  - @classmethod, @staticmethod, @property
  - __repr__, __str__, __slots__
  - Keyword-only and positional parameters
  - Closures via make_threshold_checker / make_ema_fn factory functions
  - Decorator usage (@validate_score)
  - Dataclass for typed metric results
  - Global constants (module namespace)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from app.core.decorators import validate_score

# ── Module-level (global namespace) constants ─────────────────────────────────
_FEATURE_NAMES: tuple[str, ...] = (
    "eye_contact", "smile", "posture", "head_stability", "body_movement",
)

# Default good/okay thresholds used when no config is loaded
_DEFAULT_GOOD: float = 0.70
_DEFAULT_OKAY: float = 0.40


# ─────────────────────────────────────────────────────────────────────────────
# Closure factories — produce callable objects from outer-scope variables
# ─────────────────────────────────────────────────────────────────────────────

def make_threshold_checker(
    good: float = _DEFAULT_GOOD,
    okay: float = _DEFAULT_OKAY,
) -> Callable[[float], str]:
    """Closure factory: returns a function that maps a value to a label string.

    Demonstrates:
      - Closure (inner function captures good, okay from outer scope)
      - Factory function pattern
      - Default positional-or-keyword arguments
    """
    # good, okay are free variables — captured by the inner closure
    def check(value: float) -> str:          # inner function = closure
        if value >= good:
            return "Good"
        if value >= okay:
            return "Okay"
        return "Needs improvement"
    check.__doc__ = f"Threshold checker: good≥{good}, okay≥{okay}"
    return check


def make_ema_fn(*, alpha: float = 0.30) -> Callable[[float, float], float]:
    """Closure factory: returns a stateless EMA step function.

    Keyword-only arg: alpha.
    Demonstrates closure capturing alpha.
    """
    def ema_step(prev: float, new_val: float) -> float:    # closure: alpha captured
        return alpha * new_val + (1.0 - alpha) * prev
    ema_step.__doc__ = f"EMA step with α={alpha}"
    return ema_step


# ─────────────────────────────────────────────────────────────────────────────
# Dataclass — typed result returned by every scorer
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class MetricResult:
    """Immutable result from one metric scorer for one frame.

    __slots__ reduces memory footprint on the hot path.
    """
    metric:   str
    raw:      float | None   # raw value before EMA; None = not measurable
    smoothed: float          # EMA-smoothed value emitted to client
    label:    str            # "Good" | "Okay" | "Needs improvement"
    valid:    bool           # False when detection gated this frame

    def __repr__(self) -> str:
        raw_s = f"{self.raw:.3f}" if self.raw is not None else "N/A"
        return (
            f"MetricResult({self.metric}: raw={raw_s}, "
            f"smoothed={self.smoothed:.3f}, label={self.label!r}, valid={self.valid})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the wire format expected by the frontend."""
        return {
            "metric":   self.metric,
            "score":    round(self.smoothed, 3),
            "label":    self.label,
            "valid":    self.valid,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Abstract Base Class
# ─────────────────────────────────────────────────────────────────────────────

class BaseMetricScorer(ABC):
    """Abstract scorer.  All concrete metrics inherit from this class.

    Demonstrates:
      - ABC / abstractmethod (score must be overridden)
      - Class attribute: metric_name (overridden in each subclass)
      - Instance attribute: _ema_state, _label_fn
      - @property: name, ema_value
      - @classmethod: from_config
      - @staticmethod: normalize_to_unit_range
      - __repr__, __str__
      - __init__ with positional-or-keyword and keyword-only args
    """

    # ── Class attribute (overridden by each concrete subclass) ────────
    metric_name: str = "base"

    def __init__(
        self,
        alpha: float = 0.30,
        *,
        good_threshold: float = _DEFAULT_GOOD,
        okay_threshold: float = _DEFAULT_OKAY,
    ) -> None:
        """
        Parameters
        ----------
        alpha           : EMA decay factor  (positional-or-keyword)
        good_threshold  : score above which label is "Good"  (keyword-only)
        okay_threshold  : score above which label is "Okay"  (keyword-only)
        """
        # Instance attributes
        self._alpha: float          = alpha
        self._ema_state: float      = 0.5          # seed
        self._ema_fn                = make_ema_fn(alpha=alpha)       # closure stored
        self._label_fn              = make_threshold_checker(         # closure stored
            good=good_threshold, okay=okay_threshold
        )
        # Store thresholds as plain attributes for inspection / serialization
        self.good_threshold: float  = good_threshold
        self.okay_threshold: float  = okay_threshold

    # ── Abstract method: MUST be overridden (polymorphism entry point) ──
    @abstractmethod
    def score(self, *args: Any, **kwargs: Any) -> float | None:
        """Compute raw metric score from raw landmark data.

        Returns float in [0, 1] or None when detection is not available.
        Subclasses must override this method.
        """

    # ── Concrete template method: update EMA and return MetricResult ────
    def update(self, raw: float | None, *, valid: bool = True) -> MetricResult:
        """Update internal EMA with raw score and return a MetricResult.

        Keyword-only arg: valid.
        """
        if raw is not None and valid:
            self._ema_state = self._ema_fn(self._ema_state, raw)   # uses closure
        # Even when invalid: emit the frozen EMA (internal state kept)
        label = self._label_fn(self._ema_state)
        return MetricResult(
            metric=self.metric_name,
            raw=raw,
            smoothed=self._ema_state,
            label=label,
            valid=valid,
        )

    def reset(self, *, seed: float = 0.5) -> None:
        """Reset EMA state.  Keyword-only arg: seed."""
        self._ema_state = seed

    # ── @property ──────────────────────────────────────────────────────
    @property
    def name(self) -> str:
        """Read-only metric name."""
        return self.metric_name

    @property
    def ema_value(self) -> float:
        """Current smoothed EMA value."""
        return self._ema_state

    # ── @classmethod ───────────────────────────────────────────────────
    @classmethod
    def from_config(cls, cfg: dict[str, Any], /) -> "BaseMetricScorer":
        """Named constructor: build from a config dict.

        Positional-only arg: cfg (note the /).
        Demonstrates @classmethod + positional-only parameter.
        """
        thresholds = cfg.get("thresholds", {}).get(cls.metric_name, {})
        return cls(
            alpha=float(cfg.get("ema_alpha", 0.30)),
            good_threshold=float(thresholds.get("good", _DEFAULT_GOOD)),
            okay_threshold=float(thresholds.get("okay", _DEFAULT_OKAY)),
        )

    # ── @staticmethod ──────────────────────────────────────────────────
    @staticmethod
    def normalize_to_unit_range(
        value: float,
        /,
        lo: float = 0.0,
        hi: float = 1.0,
    ) -> float:
        """Clamp value to [lo, hi] and scale to [0, 1].

        Positional-only: value.
        Demonstrates @staticmethod + positional-only first argument.
        """
        if hi <= lo:
            return 0.0
        return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))

    # ── Dunder methods ─────────────────────────────────────────────────
    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"metric={self.metric_name!r}, "
            f"α={self._alpha}, "
            f"ema={self._ema_state:.3f})"
        )

    def __str__(self) -> str:
        label = self._label_fn(self._ema_state)
        return f"{self.metric_name}: {self._ema_state:.0%} ({label})"


# ─────────────────────────────────────────────────────────────────────────────
# Concrete subclasses — polymorphic score() implementations
# ─────────────────────────────────────────────────────────────────────────────

class EyeContactScorer(BaseMetricScorer):
    """Iris-gaze eye contact scorer.

    Inherits from BaseMetricScorer; overrides score() (polymorphism).
    """

    metric_name = "eye_contact"

    def __init__(
        self,
        alpha: float = 0.30,
        *,
        good_threshold: float = 0.70,
        okay_threshold: float = 0.40,
    ) -> None:
        super().__init__(alpha, good_threshold=good_threshold, okay_threshold=okay_threshold)

    @validate_score(lo=0.0, hi=1.0)
    def score(                          # type: ignore[override]
        self,
        iris_offset: float,
        /,
    ) -> float:
        """Compute eye contact score from normalized iris offset.

        Positional-only: iris_offset.
        Decorated with @validate_score.
        """
        return 1.0 - iris_offset


class SmileScorer(BaseMetricScorer):
    """Combined mouth + cheek-squint smile scorer.

    Inherits from BaseMetricScorer; overrides score() (polymorphism).
    Overrides reset() to set a different seed (smile starts at 0).
    """

    metric_name = "smile"

    def __init__(
        self,
        alpha: float = 0.45,          # faster EMA for smile
        *,
        good_threshold: float = 0.50,
        okay_threshold: float = 0.20,
    ) -> None:
        super().__init__(alpha, good_threshold=good_threshold, okay_threshold=okay_threshold)
        self._ema_state = 0.0          # smile starts low (override parent seed)

    @validate_score(lo=0.0, hi=1.0)
    def score(                          # type: ignore[override]
        self,
        mouth_score: float,
        squint_score: float,
        /,
        squint_weight: float = 0.30,
    ) -> float:
        """Blend mouth geometry score and cheek squint score.

        Positional-only: mouth_score, squint_score.
        Positional-or-keyword: squint_weight.
        """
        return (1.0 - squint_weight) * mouth_score + squint_weight * squint_score

    def reset(self, *, seed: float = 0.0) -> None:          # polymorphic override
        """Override parent reset: smile seed is 0, not 0.5."""
        super().reset(seed=seed)


class PostureScorer(BaseMetricScorer):
    """Shoulder tilt + lean penalty posture scorer.

    Inherits from BaseMetricScorer; overrides score() (polymorphism).
    """

    metric_name = "posture"

    def __init__(
        self,
        alpha: float = 0.30,
        *,
        good_threshold: float = 0.70,
        okay_threshold: float = 0.50,
    ) -> None:
        super().__init__(alpha, good_threshold=good_threshold, okay_threshold=okay_threshold)
        self._ema_state = 0.8          # posture starts high

    @validate_score(lo=0.0, hi=1.0)
    def score(                          # type: ignore[override]
        self,
        tilt_norm: float,
        lean_penalty: float = 0.0,
        /,
        hip_penalty: float = 0.0,
    ) -> float:
        """Combine tilt, lean, and hip penalties.

        Positional-only: tilt_norm, lean_penalty.
        Positional-or-keyword: hip_penalty.
        """
        raw = (1.0 - tilt_norm) * (1.0 - lean_penalty) * (1.0 - hip_penalty)
        return float(np.clip(raw, 0.0, 1.0))


class HeadStabilityScorer(BaseMetricScorer):
    """Nose-position variance head stability scorer.

    Inherits from BaseMetricScorer; overrides score() (polymorphism).
    """

    metric_name = "head_stability"

    def __init__(
        self,
        alpha: float = 0.30,
        *,
        good_threshold: float = 0.70,
        okay_threshold: float = 0.40,
        stability_coeff: float = 0.06,
    ) -> None:
        super().__init__(alpha, good_threshold=good_threshold, okay_threshold=okay_threshold)
        self._stability_coeff: float = stability_coeff
        self._ema_state = 1.0          # stability starts high

    @validate_score(lo=0.0, hi=1.0)
    def score(                          # type: ignore[override]
        self,
        std: float,
        icd: float = 0.12,
        /,
    ) -> float:
        """Score from normalized position standard deviation.

        Positional-only: std, icd.
        """
        std_norm = std / (icd * self._stability_coeff + 1e-6)
        return 1.0 - std_norm


class BodyMovementScorer(BaseMetricScorer):
    """Combined shoulder + head variance body movement scorer.

    Inherits from BaseMetricScorer; overrides score() (polymorphism).
    """

    metric_name = "body_movement"

    # Class attributes for normalization anchors — shared by all instances
    FLOOR: float = 0.0003
    CEIL:  float = 0.018

    def __init__(
        self,
        alpha: float = 0.30,
        *,
        good_threshold: float = 0.70,
        okay_threshold: float = 0.40,
    ) -> None:
        super().__init__(alpha, good_threshold=good_threshold, okay_threshold=okay_threshold)
        self._ema_state = 1.0          # movement starts high (still)

    @validate_score(lo=0.0, hi=1.0)
    def score(                          # type: ignore[override]
        self,
        combined: float,
        /,
    ) -> float:
        """Score from combined normalized variance.

        Positional-only: combined.
        Uses class attributes FLOOR / CEIL.
        """
        denom = max(self.CEIL - self.FLOOR, 1e-8)
        return 1.0 - (combined - self.FLOOR) / denom

    @classmethod
    def set_anchors(cls, *, floor: float, ceil: float) -> None:
        """Update class-level normalization anchors.

        Keyword-only args: floor, ceil.
        Demonstrates @classmethod mutating class attributes.
        """
        cls.FLOOR = floor
        cls.CEIL  = ceil


# ─────────────────────────────────────────────────────────────────────────────
# Factory: build all scorers from a config dict
# ─────────────────────────────────────────────────────────────────────────────

def build_scorers(cfg: dict[str, Any]) -> dict[str, BaseMetricScorer]:
    """Build one scorer instance per feature using @classmethod from_config.

    Returns a name → scorer mapping.

    Demonstrates:
      - Polymorphic construction via @classmethod
      - Dictionary comprehension
      - Calling from_config on each concrete subclass
    """
    classes: list[type[BaseMetricScorer]] = [
        EyeContactScorer,
        SmileScorer,
        PostureScorer,
        HeadStabilityScorer,
        BodyMovementScorer,
    ]
    return {cls.metric_name: cls.from_config(cfg) for cls in classes}
