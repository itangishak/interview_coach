"""Unit tests for InterviewAnalyzer metric functions."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from app.services.feedback_engine import FeedbackEngine
from app.services.interview_analyzer import InterviewAnalyzer
from app.services.session_service import SessionService


def _make_face_landmarks(coords: dict[int, tuple[float, float]]):
    landmarks = []
    max_idx = max(coords.keys(), default=0)
    for i in range(max_idx + 1):
        x, y = coords.get(i, (0.5, 0.5))
        landmarks.append(SimpleNamespace(x=x, y=y))
    return SimpleNamespace(landmark=landmarks)


def _centered_face_landmarks():
    return _make_face_landmarks(
        {
            33: (0.40, 0.45),
            133: (0.48, 0.45),
            362: (0.52, 0.45),
            263: (0.60, 0.45),
            468: (0.44, 0.45),
            473: (0.56, 0.45),
            61: (0.42, 0.62),
            291: (0.58, 0.62),
            13: (0.50, 0.66),
            14: (0.50, 0.70),
        }
    )


def _off_center_gaze_landmarks():
    return _make_face_landmarks(
        {
            33: (0.40, 0.45),
            133: (0.48, 0.45),
            362: (0.52, 0.45),
            263: (0.60, 0.45),
            468: (0.47, 0.45),
            473: (0.59, 0.45),
            61: (0.42, 0.62),
            291: (0.58, 0.62),
            13: (0.50, 0.66),
            14: (0.50, 0.70),
        }
    )


def _smiling_face_landmarks():
    return _make_face_landmarks(
        {
            33: (0.40, 0.45),
            133: (0.48, 0.45),
            362: (0.52, 0.45),
            263: (0.60, 0.45),
            468: (0.44, 0.45),
            473: (0.56, 0.45),
            61: (0.38, 0.60),
            291: (0.62, 0.60),
            13: (0.50, 0.66),
            14: (0.50, 0.68),
        }
    )


def _pose_landmarks(upright: bool = True, level_shoulders: bool = True):
    lm = [SimpleNamespace(x=0.5, y=0.5, visibility=1.0) for _ in range(33)]
    lm[0] = SimpleNamespace(x=0.5, y=0.30 if upright else 0.55, visibility=1.0)
    lm[11] = SimpleNamespace(x=0.42, y=0.45, visibility=1.0)
    lm[12] = SimpleNamespace(x=0.58, y=0.45 if level_shoulders else 0.52, visibility=1.0)
    return SimpleNamespace(landmark=lm)


class TestIrisEyeContact:
    def test_centered_iris_scores_high(self):
        score = InterviewAnalyzer.iris_eye_contact_score(_centered_face_landmarks())
        assert score >= 0.85

    def test_off_center_iris_scores_lower(self):
        centered = InterviewAnalyzer.iris_eye_contact_score(_centered_face_landmarks())
        off_center = InterviewAnalyzer.iris_eye_contact_score(_off_center_gaze_landmarks())
        assert off_center < centered

    def test_missing_face_returns_zero(self):
        assert InterviewAnalyzer.iris_eye_contact_score(None) == 0.0


class TestSmileScore:
    def test_smiling_scores_higher_than_neutral(self):
        neutral = InterviewAnalyzer.raw_smile_score(_centered_face_landmarks())
        smiling = InterviewAnalyzer.raw_smile_score(_smiling_face_landmarks())
        assert smiling > neutral

    def test_missing_face_returns_zero(self):
        assert InterviewAnalyzer.raw_smile_score(None) == 0.0


class TestTemporalMetrics:
    def test_stable_head_scores_high(self):
        positions = [np.array([0.5, 0.5], dtype=np.float32) for _ in range(10)]
        score = InterviewAnalyzer.head_stability_from_positions(positions, window_size=10)
        assert score >= 0.9

    def test_jittery_head_scores_lower(self):
        stable = [np.array([0.5, 0.5], dtype=np.float32) for _ in range(10)]
        jittery = [np.array([0.5 + (i % 3) * 0.02, 0.5], dtype=np.float32) for i in range(10)]
        stable_score = InterviewAnalyzer.head_stability_from_positions(stable, window_size=10)
        jitter_score = InterviewAnalyzer.head_stability_from_positions(jittery, window_size=10)
        assert jitter_score < stable_score

    def test_combined_movement_penalizes_variance(self):
        still_shoulders = [np.array([0.5, 0.45], dtype=np.float32) for _ in range(10)]
        still_head = [np.array([0.5, 0.35], dtype=np.float32) for _ in range(10)]
        moving_shoulders = [
            np.array([0.5 + 0.03 * (i % 2), 0.45], dtype=np.float32) for i in range(10)
        ]
        still_score = InterviewAnalyzer.body_movement_from_buffers(
            still_shoulders, still_head, [0.001] * 10, window_size=10
        )
        moving_score = InterviewAnalyzer.body_movement_from_buffers(
            moving_shoulders, still_head, [0.02] * 10, window_size=10
        )
        assert moving_score < still_score


class TestPosture:
    def test_upright_level_posture_scores_high(self):
        score = InterviewAnalyzer.posture_score(_pose_landmarks(upright=True, level_shoulders=True))
        assert score >= 0.7

    def test_slouched_posture_scores_lower(self):
        upright = InterviewAnalyzer.posture_score(_pose_landmarks(upright=True))
        slouched = InterviewAnalyzer.posture_score(_pose_landmarks(upright=False))
        assert slouched < upright


class TestFeedbackEngine:
    def test_generates_recommendations_for_weak_metrics(self):
        feedback = FeedbackEngine().generate(
            eye_contact=0.2,
            smile=0.1,
            posture=0.3,
            head_stability=0.2,
            body_movement=0.2,
            confidence=35.0,
        )
        assert len(feedback["recommendations"]) >= 3
        assert feedback["eye_contact"]["status"] == "Needs improvement"

    def test_strong_metrics_get_positive_feedback(self):
        feedback = FeedbackEngine().generate(
            eye_contact=0.9,
            smile=0.8,
            posture=0.85,
            head_stability=0.9,
            body_movement=0.85,
            confidence=88.0,
        )
        assert "Great job" in feedback["recommendations"][0]


class TestSessionService:
    def test_session_lifecycle(self, tmp_path, monkeypatch):
        db_url = f"sqlite:///{tmp_path / 'test.db'}"
        from app.database.db_manager import DatabaseManager

        db = DatabaseManager(database_url=db_url)
        service = SessionService(db=db)

        session_id = "test-session-1"
        service.start_session(session_id)
        service.append_frame(session_id, {"eye_contact": 0.8, "confidence": 75.0})
        service.append_frame(session_id, {"eye_contact": 0.9, "confidence": 80.0})

        summary = service.build_summary(session_id, fps=15)
        assert summary["total_frames"] == 2
        assert summary["eye_contact"]["mean"] == pytest.approx(0.85, abs=0.01)

        service.end_session(session_id, summary)
        record = service.get_session(session_id)
        assert record is not None
        assert record["frame_count"] == 2
        assert record["ended_at"] is not None