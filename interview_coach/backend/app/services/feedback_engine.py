"""Coaching feedback engine.

Demonstrates:
  - Base class (BaseFeedbackEngine) with concrete default behavior
  - Subclass (CoachingFeedbackEngine) overriding generate() — polymorphism
  - __init_subclass__ hook
  - __repr__, __str__, __len__ (pool size)
  - Closure (make_threshold_checker in decorators module, reused here)
  - @property: pool_sizes
  - Keyword-only parameters in generate()
  - Generator expression in _iter_recommendations()
  - Global module constants (message pools)
  - Callable type hint for label_fn
"""
from __future__ import annotations

import random
from typing import Any, Callable, Generator

# ── Module-level (global namespace) message pools ────────────────────────────
_EYE_MSGS: dict[int, list[str]] = {
    0: [
        "Keep your gaze on the camera — it reads as direct eye contact to the interviewer.",
        "Try to look at the camera lens rather than the screen; it shows confidence.",
        "Frequent glances away can signal nervousness. Anchor your gaze to the camera.",
    ],
    1: [
        "Eye contact is decent — aim to hold it a little longer during key points.",
        "Your gaze is drifting occasionally. Try to return to the camera between sentences.",
    ],
    2: [
        "Excellent eye contact — you're projecting confidence.",
        "Strong, steady gaze. That's exactly what interviewers respond to.",
    ],
}

_SMILE_MSGS: dict[int, list[str]] = {
    0: [
        "A natural smile makes you appear more engaged and approachable — try one.",
        "You look tense. Even a slight smile signals warmth and enthusiasm.",
        "Interviewers respond well to warmth. Let your expression open up a little.",
    ],
    1: [
        "You're smiling occasionally — try to let it come through more naturally.",
        "Your expression is neutral. A touch more warmth will help build rapport.",
    ],
    2: [
        "Great expression — you look warm and engaged.",
        "Natural, genuine smile. That builds immediate rapport.",
    ],
}

_POSTURE_MSGS: dict[int, list[str]] = {
    0: [
        "Sit up straight — slouching projects low energy, even over video.",
        "Check your posture: shoulders back, spine tall.",
        "Lean slightly forward to show engagement, but keep your back straight.",
    ],
    1: [
        "Your posture is slightly off. Try to level your shoulders.",
        "You're almost upright — a small adjustment will make a big difference.",
    ],
    2: [
        "Good posture — you look composed and professional.",
        "Upright and level. That communicates confidence before you say a word.",
    ],
}

_HEAD_MSGS: dict[int, list[str]] = {
    0: [
        "Try to keep your head steady when answering — excessive movement is distracting.",
        "Head movement can make you look uncertain. Stay still while making key points.",
    ],
    1: [
        "Head movement is moderate. Try to anchor it a little more while speaking.",
    ],
    2: [
        "Good head stability — your delivery looks composed.",
        "Steady head position. That reads as calm and authoritative.",
    ],
}

_MOVEMENT_MSGS: dict[int, list[str]] = {
    0: [
        "You're moving quite a lot. Still, controlled body language projects confidence.",
        "Try to reduce fidgeting — it draws attention away from what you're saying.",
        "Still body language signals calm. Put your hands in your lap if needed.",
    ],
    1: [
        "Body movement is slightly elevated. Try to settle into your chair.",
    ],
    2: [
        "Calm, composed body language. That's a strong non-verbal signal.",
        "Very little unnecessary movement — you look relaxed and in control.",
    ],
}

_ALL_GOOD: list[str] = [
    "Great composure all round — keep this up.",
    "Everything looks strong. Stay consistent through the tough questions.",
    "Excellent presence. You're projecting confidence and warmth.",
]

_FACE_NOT_VISIBLE: list[str] = [
    "Your face isn't clearly visible — centre yourself in the frame.",
    "Move closer to the camera or improve lighting so your face is visible.",
]

_CALIBRATING: list[str] = [
    "Calibrating to your neutral baseline — stay still for a moment.",
]

# Mapping from metric key to its message pool
_POOLS: dict[str, dict[int, list[str]]] = {
    "eye_contact":    _EYE_MSGS,
    "smile":          _SMILE_MSGS,
    "posture":        _POSTURE_MSGS,
    "head_stability": _HEAD_MSGS,
    "body_movement":  _MOVEMENT_MSGS,
}


# ─────────────────────────────────────────────────────────────────────────────
# Base class
# ─────────────────────────────────────────────────────────────────────────────

class BaseFeedbackEngine:
    """Base feedback engine providing threshold helpers and message picking.

    Subclasses may override generate() for different coaching styles.
    Demonstrates:
      - Base class with concrete methods
      - __init_subclass__ (runs when a subclass is defined)
      - @property pool_sizes
      - __repr__, __str__, __len__
    """

    # Hardcoded fallbacks used when config doesn't supply a value
    _DEFAULT_GOOD: float = 0.70
    _DEFAULT_OKAY: float = 0.40

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Called automatically when a subclass is defined.

        Demonstrates __init_subclass__ hook.
        """
        super().__init_subclass__(**kwargs)
        # Register subclass name for introspection (not required, just illustrative)
        if not hasattr(BaseFeedbackEngine, "_subclasses"):
            BaseFeedbackEngine._subclasses: list[str] = []
        BaseFeedbackEngine._subclasses.append(cls.__name__)

    def __init__(self, thresholds: dict[str, dict[str, float]] | None = None) -> None:
        self.thresholds: dict[str, dict[str, float]] = thresholds or {}
        self._last_idx: dict[str, int] = {}      # anti-repeat state per pool key

    # ── Threshold helpers ─────────────────────────────────────────────
    def _good_t(self, metric: str) -> float:
        return float(self.thresholds.get(metric, {}).get("good", self._DEFAULT_GOOD))

    def _okay_t(self, metric: str) -> float:
        return float(self.thresholds.get(metric, {}).get("okay", self._DEFAULT_OKAY))

    def _label(self, metric: str, value: float, higher_is_better: bool = True) -> str:
        """Map value to label using per-metric config thresholds."""
        good_t, okay_t = self._good_t(metric), self._okay_t(metric)
        if value >= good_t:
            return "Good"
        if value >= okay_t:
            return "Okay"
        return "Needs improvement"

    def _severity(self, metric: str, value: float) -> int:
        """0 = bad, 1 = okay, 2 = good — uses config thresholds."""
        if value >= self._good_t(metric):
            return 2
        if value >= self._okay_t(metric):
            return 1
        return 0

    def _pick(self, key: str, pool: list[str]) -> str:
        """Pick a message avoiding immediate repetition (closure over _last_idx)."""
        if len(pool) == 1:
            return pool[0]
        last   = self._last_idx.get(key, -1)
        choices = [i for i in range(len(pool)) if i != last]
        idx    = random.choice(choices)
        self._last_idx[key] = idx
        return pool[idx]

    # ── Generator method — yields recommendation strings ──────────────
    def _iter_recommendations(
        self,
        scores: dict[str, float],
        /,
    ) -> Generator[str, None, None]:
        """Generator: yield one recommendation per metric below "Good".

        Positional-only: scores dict.
        Demonstrates generator method using yield.
        """
        for key, pool in _POOLS.items():
            value = scores.get(key, 0.0)
            sev   = self._severity(key, value)
            if sev < 2:
                yield self._pick(key, pool[sev])   # generator yield

    def generate(
        self,
        *,
        eye_contact:    float,
        smile:          float,
        posture:        float,
        head_stability: float,
        body_movement:  float,
        confidence:     float,
        face_visible:   bool = True,
        calibrating:    bool = False,
        label_fn: Callable[[str, float, bool], str] | None = None,
    ) -> dict[str, Any]:
        """Generate feedback payload.  All parameters are keyword-only.

        label_fn: optional hysteresis-aware label from InterviewAnalyzer.
        """
        lf = label_fn or (lambda k, v, h: self._label(k, v, h))

        if not face_visible:
            recs = [self._pick("face", _FACE_NOT_VISIBLE)]
        elif calibrating:
            recs = [_CALIBRATING[0]]
        else:
            scores = {
                "eye_contact":    eye_contact,
                "smile":          smile,
                "posture":        posture,
                "head_stability": head_stability,
                "body_movement":  body_movement,
            }
            # Use generator; convert to list
            recs = list(self._iter_recommendations(scores))
            if not recs:
                recs = [self._pick("all_good", _ALL_GOOD)]

        return {
            "eye_contact":    {"score": round(eye_contact, 2),    "status": lf("eye_contact",    eye_contact,    True)},
            "smile":          {"score": round(smile, 2),          "status": lf("smile",          smile,          True)},
            "posture":        {"score": round(posture, 2),        "status": lf("posture",        posture,        True)},
            "head_stability": {"score": round(head_stability, 2), "status": lf("head_stability", head_stability, True)},
            "body_movement":  {"score": round(body_movement, 2),  "status": lf("body_movement",  body_movement,  True)},
            "confidence":     {"score": round(confidence, 1),     "status": lf("confidence",     confidence / 100.0, True)},
            "recommendations": recs,
        }

    # ── @property ─────────────────────────────────────────────────────
    @property
    def pool_sizes(self) -> dict[str, int]:
        """Return total pool size (all severities) per metric."""
        return {
            key: sum(len(msgs) for msgs in pool.values())
            for key, pool in _POOLS.items()
        }

    # ── Dunder methods ────────────────────────────────────────────────
    def __repr__(self) -> str:
        return f"{type(self).__name__}(thresholds={list(self.thresholds.keys())})"

    def __str__(self) -> str:
        total = sum(self.pool_sizes.values())
        return f"{type(self).__name__} — {total} coaching messages across {len(_POOLS)} metrics"

    def __len__(self) -> int:
        """Total number of messages across all pools."""
        return sum(self.pool_sizes.values())


# ─────────────────────────────────────────────────────────────────────────────
# Subclass — polymorphic override of generate()
# ─────────────────────────────────────────────────────────────────────────────

class CoachingFeedbackEngine(BaseFeedbackEngine):
    """Production coaching engine.

    Inherits BaseFeedbackEngine; overrides generate() to add priority ordering
    (eye contact most important, body movement least).

    Demonstrates:
      - Inheritance (super().__init__)
      - Polymorphism (generate() override)
      - super() usage
      - Additional instance attribute (_priority)
    """

    # Class attribute — priority order (highest first)
    _PRIORITY: tuple[str, ...] = (
        "eye_contact", "posture", "head_stability", "smile", "body_movement",
    )

    def __init__(self, thresholds: dict[str, dict[str, float]] | None = None) -> None:
        super().__init__(thresholds)                          # call parent __init__
        # Additional instance attribute not in parent
        self._generate_count: int = 0

    def generate(                                             # polymorphic override
        self,
        *,
        eye_contact:    float,
        smile:          float,
        posture:        float,
        head_stability: float,
        body_movement:  float,
        confidence:     float,
        face_visible:   bool = True,
        calibrating:    bool = False,
        label_fn: Callable[[str, float, bool], str] | None = None,
    ) -> dict[str, Any]:
        """Override: orders recommendations by _PRIORITY list."""
        self._generate_count += 1

        # Delegate the structure building to parent, then re-order recs
        result = super().generate(
            eye_contact    = eye_contact,
            smile          = smile,
            posture        = posture,
            head_stability = head_stability,
            body_movement  = body_movement,
            confidence     = confidence,
            face_visible   = face_visible,
            calibrating    = calibrating,
            label_fn       = label_fn,
        )

        if face_visible and not calibrating:
            scores = {
                "eye_contact":    eye_contact,
                "smile":          smile,
                "posture":        posture,
                "head_stability": head_stability,
                "body_movement":  body_movement,
            }
            # Rebuild recs in priority order using generator expression
            ordered = [
                self._pick(key, _POOLS[key][self._severity(key, scores[key])])
                for key in self._PRIORITY
                if self._severity(key, scores[key]) < 2
            ]
            result["recommendations"] = ordered or [self._pick("all_good", _ALL_GOOD)]

        return result

    @property
    def generate_count(self) -> int:
        """How many times generate() has been called this session."""
        return self._generate_count

    def reset_count(self) -> None:
        """Reset the call counter (e.g. on new session)."""
        self._generate_count = 0

    def __repr__(self) -> str:
        return (
            f"CoachingFeedbackEngine("
            f"calls={self._generate_count}, "
            f"thresholds={list(self.thresholds.keys())})"
        )


# ── Backward-compatible alias: existing code imports FeedbackEngine ───────────
FeedbackEngine = CoachingFeedbackEngine
