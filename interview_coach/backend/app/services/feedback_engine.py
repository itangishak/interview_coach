"""Human-readable coaching feedback from analyzer metrics."""

from __future__ import annotations

from typing import Any


class FeedbackEngine:
    """Maps numeric metric scores to status labels and coaching recommendations."""

    def __init__(self, thresholds: dict[str, dict[str, float]] | None = None) -> None:
        self.thresholds = thresholds or {}

    @staticmethod
    def _label(value: float, higher_is_better: bool = True) -> str:
        if higher_is_better:
            if value >= 0.7:
                return "Good"
            if value >= 0.4:
                return "Okay"
            return "Needs improvement"
        if value >= 0.7:
            return "Needs improvement"
        if value >= 0.4:
            return "Okay"
        return "Good"

    def generate(
        self,
        *,
        eye_contact: float,
        smile: float,
        posture: float,
        head_stability: float,
        body_movement: float,
        confidence: float,
    ) -> dict[str, Any]:
        recommendations: list[str] = []

        if eye_contact < 0.5:
            recommendations.append("Look at the camera more often to improve eye contact.")
        if smile < 0.2:
            recommendations.append("Smile occasionally to appear more approachable.")
        if posture < 0.5:
            recommendations.append("Sit up straight and keep your shoulders level.")
        if head_stability < 0.4:
            recommendations.append("Try to keep your head steady while speaking.")
        if body_movement < 0.4:
            recommendations.append("Reduce excessive body movement.")

        if not recommendations:
            recommendations.append("Great job! Keep your current composure.")

        return {
            "eye_contact": {"score": round(eye_contact, 2), "status": self._label(eye_contact)},
            "smile": {"score": round(smile, 2), "status": self._label(smile)},
            "posture": {"score": round(posture, 2), "status": self._label(posture)},
            "head_stability": {
                "score": round(head_stability, 2),
                "status": self._label(head_stability),
            },
            "body_movement": {
                "score": round(body_movement, 2),
                "status": self._label(body_movement, higher_is_better=False),
            },
            "confidence": {
                "score": round(confidence, 1),
                "status": self._label(confidence / 100.0),
            },
            "recommendations": recommendations,
        }