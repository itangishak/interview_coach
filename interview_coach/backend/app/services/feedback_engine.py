"""Coaching feedback engine — varied, context-aware messages (Flaw E fix)."""

from __future__ import annotations

import random
from typing import Any, Callable


# ── Message pools — indexed by severity (0=bad, 1=okay, 2=good) ──────────────

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

_ALL_GOOD = [
    "Great composure all round — keep this up.",
    "Everything looks strong. Stay consistent through the tough questions.",
    "Excellent presence. You're projecting confidence and warmth.",
]

_FACE_NOT_VISIBLE = [
    "Your face isn't clearly visible — centre yourself in the frame.",
    "Move closer to the camera or improve lighting so your face is visible.",
]

_CALIBRATING = [
    "Calibrating to your neutral baseline — stay still for a moment.",
]


class FeedbackEngine:
    """
    Maps metric scores to varied, context-aware coaching text.
    Uses message pools so output is not the same string every call.

    Thresholds are read from the ``thresholds`` dict passed at construction
    (sourced from interview_config.json via InterviewAnalyzer._load_config).
    Both _severity() and the static _label() helper respect these values so
    that changing the JSON file changes feedback labels without code edits.
    """

    # Hardcoded fallbacks used only when the config doesn't supply a value
    _DEFAULT_GOOD = 0.70
    _DEFAULT_OKAY = 0.40

    def __init__(self, thresholds: dict[str, dict[str, float]] | None = None) -> None:
        self.thresholds = thresholds or {}
        # Track which pool index was last chosen per metric to avoid repeating
        self._last_idx: dict[str, int] = {}

    # ── Threshold helpers ─────────────────────────────────────────────
    def _good_t(self, metric: str) -> float:
        return float(self.thresholds.get(metric, {}).get("good", self._DEFAULT_GOOD))

    def _okay_t(self, metric: str) -> float:
        return float(self.thresholds.get(metric, {}).get("okay", self._DEFAULT_OKAY))

    # ── Label helper (uses config thresholds) ─────────────────────────
    def _label(self, metric: str, value: float, higher_is_better: bool = True) -> str:
        good_t = self._good_t(metric)
        okay_t = self._okay_t(metric)
        if higher_is_better:
            if value >= good_t: return "Good"
            if value >= okay_t: return "Okay"
            return "Needs improvement"
        # Inverted: high value = good (less movement)
        if value >= good_t: return "Good"
        if value >= okay_t: return "Okay"
        return "Needs improvement"

    def _pick(self, key: str, pool: list[str]) -> str:
        """Pick a message from pool, avoiding immediate repetition."""
        if len(pool) == 1:
            return pool[0]
        last = self._last_idx.get(key, -1)
        choices = [i for i in range(len(pool)) if i != last]
        idx = random.choice(choices)
        self._last_idx[key] = idx
        return pool[idx]

    def _severity(self, metric: str, value: float) -> int:
        """0 = bad, 1 = okay, 2 = good — uses config thresholds."""
        if value >= self._good_t(metric): return 2
        if value >= self._okay_t(metric): return 1
        return 0

    # ── Public API ───────────────────────────────────────────────────
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
        """
        Parameters
        ----------
        label_fn : hysteresis-aware label function from InterviewAnalyzer.
                   Falls back to self._label (config-threshold aware) if None.
        """
        # If no hysteresis function given, fall back to config-aware label
        lf = label_fn or (lambda k, v, h: self._label(k, v, h))

        recommendations: list[str] = []

        if not face_visible:
            recommendations.append(self._pick("face", _FACE_NOT_VISIBLE))
        elif calibrating:
            recommendations.append(_CALIBRATING[0])
        else:
            # _severity now uses config thresholds per metric
            sev_eye  = self._severity("eye_contact",    eye_contact)
            sev_sm   = self._severity("smile",          smile)
            sev_ps   = self._severity("posture",        posture)
            sev_hs   = self._severity("head_stability", head_stability)
            sev_mv   = self._severity("body_movement",  body_movement)

            if sev_eye  < 2: recommendations.append(self._pick("eye",      _EYE_MSGS[sev_eye]))
            if sev_sm   < 2: recommendations.append(self._pick("smile",    _SMILE_MSGS[sev_sm]))
            if sev_ps   < 2: recommendations.append(self._pick("posture",  _POSTURE_MSGS[sev_ps]))
            if sev_hs   < 2: recommendations.append(self._pick("head",     _HEAD_MSGS[sev_hs]))
            if sev_mv   < 2: recommendations.append(self._pick("movement", _MOVEMENT_MSGS[sev_mv]))

            if not recommendations:
                recommendations.append(self._pick("all_good", _ALL_GOOD))

        return {
            "eye_contact": {
                "score":  round(eye_contact, 2),
                "status": lf("eye_contact", eye_contact, True),
            },
            "smile": {
                "score":  round(smile, 2),
                "status": lf("smile", smile, True),
            },
            "posture": {
                "score":  round(posture, 2),
                "status": lf("posture", posture, True),
            },
            "head_stability": {
                "score":  round(head_stability, 2),
                "status": lf("head_stability", head_stability, True),
            },
            "body_movement": {
                "score":  round(body_movement, 2),
                "status": lf("body_movement", body_movement, True),
            },
            "confidence": {
                "score":  round(confidence, 1),
                "status": lf("confidence", confidence / 100.0, True),
            },
            "recommendations": recommendations,
        }
