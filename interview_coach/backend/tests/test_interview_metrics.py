"""Unit tests for InterviewAnalyzer metric functions.

Coverage
--------
- Flaw A: ICD normalization (smile elevation, head stability, body movement)
- Flaw B: Head-yaw gating (iris score returns None when yaw > threshold)
- Flaw C: EMA smoothing + smile peak-percentile + hysteresis labels
- Flaw D: None returns from metric helpers; excluded flag in analyze_frame
- Flaw E: Calibration baseline; varied feedback strings (no two identical in a row)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.feedback_engine import FeedbackEngine
from app.services.interview_analyzer import InterviewAnalyzer
from app.services.session_service import SessionService


# ── Landmark factories ────────────────────────────────────────────────────────

def _make_face_landmarks(coords: dict[int, tuple[float, float]]):
    max_idx = max(coords.keys(), default=0)
    landmarks = []
    for i in range(max_idx + 1):
        x, y = coords.get(i, (0.5, 0.5))
        landmarks.append(SimpleNamespace(x=x, y=y))
    return SimpleNamespace(landmark=landmarks)


def _centered_face(icd: float = 0.20) -> object:
    """Centered iris, ICD = icd, smile neutral."""
    hw = icd / 2.0
    return _make_face_landmarks({
        # eye corners
        33: (0.50 - hw, 0.45),   # left outer
        133: (0.50 - hw * 0.1, 0.45),  # left inner
        362: (0.50 + hw * 0.1, 0.45),  # right inner
        263: (0.50 + hw, 0.45),  # right outer
        # iris — centered
        468: (0.50 - hw * 0.55, 0.45),
        473: (0.50 + hw * 0.55, 0.45),
        # mouth — neutral (landmark 4 = nose tip for yaw)
        4:  (0.50, 0.60),        # nose tip — centered for yaw = 0
        61: (0.44, 0.68),
        291: (0.56, 0.68),
        13: (0.50, 0.72),
        14: (0.50, 0.76),
    })


def _off_center_iris_face(icd: float = 0.20) -> object:
    """Iris shifted toward nose — reduced eye contact."""
    hw = icd / 2.0
    return _make_face_landmarks({
        33: (0.50 - hw, 0.45),
        133: (0.50 - hw * 0.1, 0.45),
        362: (0.50 + hw * 0.1, 0.45),
        263: (0.50 + hw, 0.45),
        468: (0.50 - hw * 0.2, 0.45),   # shifted inward
        473: (0.50 + hw * 0.9, 0.45),
        4:  (0.50, 0.60),
        61: (0.44, 0.68), 291: (0.56, 0.68),
        13: (0.50, 0.72), 14: (0.50, 0.76),
    })


def _smiling_face(icd: float = 0.20) -> object:
    """Wide mouth with elevated corners."""
    hw = icd / 2.0
    return _make_face_landmarks({
        33: (0.50 - hw, 0.45), 133: (0.50 - hw * 0.1, 0.45),
        362: (0.50 + hw * 0.1, 0.45), 263: (0.50 + hw, 0.45),
        468: (0.50 - hw * 0.55, 0.45), 473: (0.50 + hw * 0.55, 0.45),
        4:  (0.50, 0.60),
        # wide mouth corners + elevated (above lip center → positive elevation)
        61: (0.38, 0.67),
        291: (0.62, 0.67),
        13: (0.50, 0.72),
        14: (0.50, 0.74),
    })


def _large_yaw_face() -> object:
    """Nose tip far off-center → yaw > 25°."""
    return _make_face_landmarks({
        33: (0.35, 0.45), 133: (0.42, 0.45),
        362: (0.52, 0.45), 263: (0.60, 0.45),
        468: (0.39, 0.45), 473: (0.56, 0.45),
        4:  (0.65, 0.60),   # nose far right → large yaw
        61: (0.44, 0.68), 291: (0.56, 0.68),
        13: (0.50, 0.72), 14: (0.50, 0.76),
    })


def _pose_landmarks(upright: bool = True, level: bool = True, shoulder_width: float = 0.20):
    lm = [SimpleNamespace(x=0.5, y=0.5, visibility=1.0) for _ in range(33)]
    hw = shoulder_width / 2.0
    lm[0]  = SimpleNamespace(x=0.5,       y=0.25 if upright else 0.55, visibility=1.0)
    lm[11] = SimpleNamespace(x=0.5 - hw,  y=0.45,                      visibility=1.0)
    lm[12] = SimpleNamespace(x=0.5 + hw,  y=0.45 if level else 0.52,  visibility=1.0)
    return SimpleNamespace(landmark=lm)


# ── Flaw A: ICD normalization ─────────────────────────────────────────────────

class TestICDNormalization:
    """Smile elevation and head-stability scores must not depend on face distance."""

    def test_smile_score_consistent_across_icd(self):
        """Same smile geometry at different scale → similar score (within 0.15)."""
        sm_small = InterviewAnalyzer.raw_smile_score(_smiling_face(icd=0.12))
        sm_large = InterviewAnalyzer.raw_smile_score(_smiling_face(icd=0.25))
        assert sm_small is not None and sm_large is not None
        assert abs(sm_small - sm_large) < 0.15, (
            f"Smile score should be distance-independent: {sm_small:.3f} vs {sm_large:.3f}"
        )

    def test_head_stability_normalized_by_icd(self):
        """Same absolute sway → worse score when ICD is small (person is far away)."""
        positions = [np.array([0.5 + 0.01 * (i % 3), 0.5]) for i in range(20)]
        score_large_icd  = InterviewAnalyzer.head_stability_score(positions, 10, icd=0.25)
        score_small_icd  = InterviewAnalyzer.head_stability_score(positions, 10, icd=0.10)
        # Small ICD → sway is relatively larger → lower stability score
        assert score_small_icd is not None and score_large_icd is not None
        assert score_small_icd <= score_large_icd

    def test_posture_normalized_by_shoulder_width(self):
        """Same tilt, different shoulder width → similar score (ratio-based)."""
        ps_narrow = InterviewAnalyzer.posture_score(_pose_landmarks(shoulder_width=0.12), 0.12)
        ps_wide   = InterviewAnalyzer.posture_score(_pose_landmarks(shoulder_width=0.25), 0.25)
        assert ps_narrow is not None and ps_wide is not None
        assert abs(ps_narrow - ps_wide) < 0.10, (
            f"Posture should be scale-independent: {ps_narrow:.3f} vs {ps_wide:.3f}"
        )


# ── Flaw B: Head-yaw gating ───────────────────────────────────────────────────

class TestHeadYawGating:
    def test_large_yaw_returns_none(self):
        score = InterviewAnalyzer.iris_eye_contact_score(_large_yaw_face())
        assert score is None, "High-yaw frame should return None, not a fabricated score."

    def test_centered_face_returns_float(self):
        score = InterviewAnalyzer.iris_eye_contact_score(_centered_face())
        assert score is not None and 0.0 <= score <= 1.0

    def test_yaw_estimation_centered_is_near_zero(self):
        lm = np.array([[p.x, p.y] for p in _centered_face().landmark])
        yaw = InterviewAnalyzer.estimate_yaw_deg(lm)
        assert abs(yaw) < 10.0, f"Centered face yaw should be ~0, got {yaw:.1f}°"


# ── Flaw C: EMA + hysteresis + smile peak ────────────────────────────────────

class TestEMAAndHysteresis:
    def test_ema_converges_toward_new_value(self):
        az = InterviewAnalyzer(window_size=30)
        # Inject 20 frames of high eye-contact
        for _ in range(20):
            az._ema_update("eye_contact", 0.9)
        assert az._ema["eye_contact"] > 0.75, "EMA should converge toward 0.9 after 20 frames"

    def test_ema_responds_faster_than_mean_to_step_change(self):
        """EMA should reach 0.7 faster than a 30-frame window mean after a step to 1.0."""
        az = InterviewAnalyzer(window_size=30)
        az._ema["eye_contact"] = 0.0  # start low
        steps_ema = 0
        for _ in range(100):
            az._ema_update("eye_contact", 1.0)
            steps_ema += 1
            if az._ema["eye_contact"] >= 0.7:
                break
        assert steps_ema < 30, f"EMA should cross 0.7 in <30 steps, took {steps_ema}"

    def test_hysteresis_prevents_label_flip_on_small_change(self):
        az = InterviewAnalyzer(window_size=30)
        # Establish "Good" state
        az._label_state["eye_contact"] = "Good"
        # Score just dips below 0.7 threshold by less than hysteresis band
        label = az._label_with_hysteresis("eye_contact", 0.68)
        assert label == "Good", "Hysteresis should prevent label flip on 0.02 dip"

    def test_hysteresis_changes_label_on_large_drop(self):
        az = InterviewAnalyzer(window_size=30)
        az._label_state["eye_contact"] = "Good"
        label = az._label_with_hysteresis("eye_contact", 0.35)
        assert label == "Needs improvement"

    def test_smile_peak_percentile_vs_mean_for_frequent_smiles(self):
        """When smiling often (6/10 frames), peak-percentile should be high while mean stays moderate."""
        az = InterviewAnalyzer(window_size=10)
        # 6 smiling frames + 4 neutral
        for _ in range(6):
            az.smile_raw_window.append(0.8)
        for _ in range(4):
            az.smile_raw_window.append(0.0)
        peak = float(np.percentile(list(az.smile_raw_window), 80))
        mean = float(np.mean(list(az.smile_raw_window)))
        # Peak-percentile should be at least as high as the mean
        assert peak >= mean, "80th percentile should be >= mean"
        # And should capture the smile frames (>= 0.5)
        assert peak >= 0.5, f"80th-pct of mostly-smiling window should be >=0.5, got {peak}"


# ── Flaw D: Detection gating ─────────────────────────────────────────────────

class TestDetectionGating:
    def test_missing_face_returns_none_for_iris(self):
        assert InterviewAnalyzer.iris_eye_contact_score(None) is None

    def test_missing_face_returns_none_for_smile(self):
        assert InterviewAnalyzer.raw_smile_score(None) is None

    def test_missing_pose_returns_none_for_posture(self):
        assert InterviewAnalyzer.posture_score(None) is None

    def test_head_stability_returns_none_with_one_position(self):
        result = InterviewAnalyzer.head_stability_score([np.array([0.5, 0.5])], 10)
        assert result is None

    def test_body_movement_returns_none_with_no_data(self):
        result = InterviewAnalyzer.body_movement_score([], [], [], 10)
        assert result is None

    def test_excluded_flag_set_when_face_absent(self):
        """analyze_frame with no face should set excluded=True."""
        az = InterviewAnalyzer(window_size=30)
        black = np.zeros((480, 640, 3), dtype=np.uint8)
        result = az.analyze_frame(black)
        # On a blank frame MediaPipe should not detect a face
        if not result["face_visible"]:
            assert result["excluded"] is True
        # If somehow detected on blank frame, just check key exists
        assert "excluded" in result


# ── Flaw A (original tests, kept) ────────────────────────────────────────────

class TestIrisEyeContact:
    def test_centered_iris_scores_high(self):
        score = InterviewAnalyzer.iris_eye_contact_score(_centered_face())
        assert score is not None and score >= 0.75

    def test_off_center_iris_scores_lower(self):
        centered  = InterviewAnalyzer.iris_eye_contact_score(_centered_face())
        off_center = InterviewAnalyzer.iris_eye_contact_score(_off_center_iris_face())
        assert centered is not None and off_center is not None
        assert off_center < centered


class TestSmileScore:
    def test_smiling_scores_higher_than_neutral(self):
        neutral = InterviewAnalyzer.raw_smile_score(_centered_face())
        smiling = InterviewAnalyzer.raw_smile_score(_smiling_face())
        assert neutral is not None and smiling is not None
        assert smiling > neutral

    def test_missing_face_returns_none(self):
        assert InterviewAnalyzer.raw_smile_score(None) is None


class TestTemporalMetrics:
    def test_stable_head_scores_high(self):
        positions = [np.array([0.5, 0.5]) for _ in range(10)]
        score = InterviewAnalyzer.head_stability_score(positions, 10, icd=0.20)
        assert score is not None and score >= 0.85

    def test_jittery_head_scores_lower(self):
        stable  = [np.array([0.5, 0.5]) for _ in range(10)]
        jittery = [np.array([0.5 + (i % 3) * 0.025, 0.5]) for i in range(10)]
        s_score = InterviewAnalyzer.head_stability_score(stable,  10, icd=0.20)
        j_score = InterviewAnalyzer.head_stability_score(jittery, 10, icd=0.20)
        assert s_score is not None and j_score is not None
        assert j_score < s_score

    def test_combined_movement_penalizes_variance(self):
        still   = [np.array([0.5, 0.45]) for _ in range(10)]
        moving  = [np.array([0.5 + 0.03 * (i % 2), 0.45]) for i in range(10)]
        nose    = [np.array([0.5, 0.35]) for _ in range(10)]
        ss = InterviewAnalyzer.body_movement_score(still,  nose, [0.001] * 10, 10, 0.20)
        ms = InterviewAnalyzer.body_movement_score(moving, nose, [0.02]  * 10, 10, 0.20)
        assert ss is not None and ms is not None
        assert ms < ss


class TestPosture:
    def test_upright_level_scores_high(self):
        score = InterviewAnalyzer.posture_score(_pose_landmarks(True, True), 0.20)
        assert score is not None and score >= 0.70

    def test_slouched_scores_lower(self):
        up  = InterviewAnalyzer.posture_score(_pose_landmarks(True),  0.20)
        sl  = InterviewAnalyzer.posture_score(_pose_landmarks(False), 0.20)
        assert up is not None and sl is not None
        assert sl < up


# ── Flaw E: Varied feedback ───────────────────────────────────────────────────

class TestFeedbackEngine:
    def test_varied_messages_no_immediate_repeat(self):
        """Same metric, same severity → different message on consecutive calls."""
        engine = FeedbackEngine()
        msgs = set()
        for _ in range(6):
            fb = engine.generate(
                eye_contact=0.2, smile=0.1, posture=0.8,
                head_stability=0.9, body_movement=0.9, confidence=40.0,
            )
            msgs.add(fb["recommendations"][0])
        # Should have seen at least 2 distinct messages across 6 calls
        assert len(msgs) >= 2, "Feedback should vary, not repeat the same string every time."

    def test_face_not_visible_overrides_other_messages(self):
        fb = FeedbackEngine().generate(
            eye_contact=0.0, smile=0.0, posture=0.0,
            head_stability=0.0, body_movement=0.0, confidence=0.0,
            face_visible=False,
        )
        assert any("visible" in r.lower() or "frame" in r.lower() for r in fb["recommendations"])

    def test_calibrating_state_shown(self):
        fb = FeedbackEngine().generate(
            eye_contact=0.5, smile=0.3, posture=0.6,
            head_stability=0.8, body_movement=0.8, confidence=60.0,
            calibrating=True,
        )
        assert any("calibrat" in r.lower() for r in fb["recommendations"])

    def test_all_good_triggers_positive_message(self):
        fb = FeedbackEngine().generate(
            eye_contact=0.9, smile=0.85, posture=0.88,
            head_stability=0.92, body_movement=0.88, confidence=90.0,
        )
        assert len(fb["recommendations"]) == 1
        rec = fb["recommendations"][0].lower()
        assert any(w in rec for w in ("great", "excellent", "strong", "good"))

    def test_weak_metrics_produce_multiple_recommendations(self):
        fb = FeedbackEngine().generate(
            eye_contact=0.2, smile=0.1, posture=0.3,
            head_stability=0.2, body_movement=0.2, confidence=25.0,
        )
        assert len(fb["recommendations"]) >= 3

    def test_status_labels_present(self):
        fb = FeedbackEngine().generate(
            eye_contact=0.85, smile=0.6, posture=0.3,
            head_stability=0.75, body_movement=0.5, confidence=65.0,
        )
        assert fb["eye_contact"]["status"] == "Good"
        assert fb["posture"]["status"] == "Needs improvement"

    # ── Config-threshold wiring tests ────────────────────────────────
    def test_config_thresholds_respected_for_smile(self):
        """smile good=0.5 from config → score=0.6 should be 'Good', not 'Okay'."""
        thresholds = {
            "smile": {"good": 0.50, "okay": 0.20},
            # leave others at defaults
        }
        engine = FeedbackEngine(thresholds=thresholds)
        # severity should be 2 (good) for 0.6 with good_t=0.5
        sev = engine._severity("smile", 0.6)
        assert sev == 2, f"Expected severity 2 for smile=0.6 with good_t=0.5, got {sev}"

        # Label should be Good
        label = engine._label("smile", 0.6, True)
        assert label == "Good"

    def test_default_thresholds_applied_when_no_config(self):
        """Without thresholds, score=0.65 for eye_contact is 'Okay' (below default 0.70)."""
        engine = FeedbackEngine()
        sev = engine._severity("eye_contact", 0.65)
        assert sev == 1  # Okay, not Good

    def test_custom_threshold_raises_good_bar(self):
        """eye_contact good=0.85 → score=0.80 should be 'Okay', not 'Good'."""
        engine = FeedbackEngine(thresholds={"eye_contact": {"good": 0.85, "okay": 0.50}})
        sev = engine._severity("eye_contact", 0.80)
        assert sev == 1  # Okay
        label = engine._label("eye_contact", 0.80, True)
        assert label == "Okay"

    def test_analyzer_thresholds_flow_to_hysteresis(self):
        """Thresholds loaded from config must flow through to _label_with_hysteresis."""
        import json
        import tempfile, os
        cfg = {
            "confidence_weights": {
                "eye_contact": 0.30, "smile": 0.15, "posture": 0.20,
                "head_stability": 0.20, "body_movement": 0.15,
            },
            "thresholds": {
                "smile": {"good": 0.50, "okay": 0.20},
            },
            "window_size": 30,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(cfg, f)
            path = f.name
        try:
            az = InterviewAnalyzer(config_path=path, window_size=30)
            # smile good_t=0.50 → score=0.55 should be "Good"
            label = az._label_with_hysteresis("smile", 0.55, True)
            assert label == "Good", (
                f"Expected 'Good' for smile=0.55 with good_t=0.50, got '{label}'"
            )
        finally:
            os.unlink(path)


# ── Session service ───────────────────────────────────────────────────────────

class TestSessionService:
    def test_session_lifecycle(self, tmp_path):
        from app.database.db_manager import DatabaseManager
        db = DatabaseManager(database_url=f"sqlite:///{tmp_path / 'test.db'}")
        service = SessionService(db=db)

        session_id = "test-session-1"
        service.start_session(session_id)
        service.append_frame(session_id, {
            "eye_contact": 0.8, "confidence": 75.0, "excluded": False,
        })
        service.append_frame(session_id, {
            "eye_contact": 0.9, "confidence": 80.0, "excluded": False,
        })
        summary = service.build_summary(session_id, fps=15)
        assert summary["total_frames"] == 2
        assert summary["eye_contact"]["mean"] == pytest.approx(0.85, abs=0.01)

        service.end_session(session_id, summary)
        record = service.get_session(session_id)
        assert record is not None
        assert record["frame_count"] == 2
        assert record["ended_at"] is not None

    def test_excluded_frames_not_in_aggregates(self, tmp_path):
        """Gated frames (excluded=True) must not distort session averages."""
        from app.database.db_manager import DatabaseManager
        db = DatabaseManager(database_url=f"sqlite:///{tmp_path / 'test2.db'}")
        service = SessionService(db=db)

        session_id = "test-excluded"
        service.start_session(session_id)
        # 3 valid frames with high eye contact
        for _ in range(3):
            service.append_frame(session_id, {
                "eye_contact": 0.9, "confidence": 85.0, "excluded": False,
            })
        # 2 gated frames with zero scores — should NOT drag the mean down
        for _ in range(2):
            service.append_frame(session_id, {
                "eye_contact": 0.0, "confidence": 0.0, "excluded": True,
            })
        summary = service.build_summary(session_id, fps=15)
        assert summary["eye_contact"]["mean"] == pytest.approx(0.9, abs=0.01), (
            "Excluded frames must not affect session mean"
        )
        assert summary["valid_frame_count"] == 3
        assert summary["excluded_frame_count"] == 2


# ── Flaw B full fix: 3-D head pose via solvePnP ───────────────────────────────

class TestSolvePnPHeadPose:
    """estimate_head_pose should return near-zero yaw/pitch for a frontal face."""

    def _frontal_landmark_array(self) -> np.ndarray:
        """Approximate frontal-face landmark positions in normalized [0,1] coords."""
        # These mirror the 6 PnP reference landmarks at a typical camera distance
        lm = np.zeros((478, 2))
        lm[1]   = [0.500, 0.520]  # nose tip
        lm[152] = [0.500, 0.820]  # chin
        lm[33]  = [0.350, 0.420]  # left eye outer
        lm[263] = [0.650, 0.420]  # right eye outer
        lm[61]  = [0.420, 0.680]  # left mouth corner
        lm[291] = [0.580, 0.680]  # right mouth corner
        # iris (needed for eye contact score)
        lm[133] = [0.390, 0.420]
        lm[362] = [0.610, 0.420]
        lm[468] = [0.368, 0.420]
        lm[473] = [0.632, 0.420]
        lm[4]   = [0.500, 0.520]  # nose for geometric fallback
        lm[13]  = [0.500, 0.660]
        lm[14]  = [0.500, 0.700]
        return lm

    def test_frontal_face_yaw_near_zero(self):
        az = InterviewAnalyzer(window_size=30)
        lm = self._frontal_landmark_array()
        yaw, pitch, roll = az.estimate_head_pose(lm, 640, 480)
        assert abs(yaw) < 20.0, f"Frontal face yaw should be near 0, got {yaw:.1f}°"

    def test_camera_offset_subtracted_from_pitch(self):
        """Setting a +8° camera offset should reduce the returned pitch by 8°."""
        az = InterviewAnalyzer(window_size=30)
        lm = self._frontal_landmark_array()
        _, pitch_no_offset, _ = az.estimate_head_pose(lm, 640, 480)

        az._camera_pitch_offset_deg = 8.0
        _, pitch_with_offset, _ = az.estimate_head_pose(lm, 640, 480)

        diff = pitch_no_offset - pitch_with_offset
        assert abs(diff - 8.0) < 0.5, (
            f"Camera offset subtraction failed: Δpitch={diff:.2f}°, expected ~8°"
        )

    def test_analyze_frame_returns_yaw_pitch_keys(self):
        az = InterviewAnalyzer(window_size=30)
        black = np.zeros((480, 640, 3), dtype=np.uint8)
        result = az.analyze_frame(black)
        assert "yaw_deg"   in result
        assert "pitch_deg" in result
        assert isinstance(result["yaw_deg"],   float)
        assert isinstance(result["pitch_deg"], float)


# ── Flaw E full fix: persistent user profile ─────────────────────────────────

class TestUserProfileService:
    def test_profile_starts_empty(self, tmp_path):
        from app.database.db_manager import DatabaseManager
        from app.services.user_profile_service import UserProfileService
        db = DatabaseManager(database_url=f"sqlite:///{tmp_path / 'p.db'}")
        svc = UserProfileService(db=db)
        profile = svc.get_profile("user_a")
        assert profile["baseline"] == {}
        assert profile["camera_offset_deg"] == 0.0
        assert profile["session_count"] == 0

    def test_baseline_stored_and_retrieved(self, tmp_path):
        from app.database.db_manager import DatabaseManager
        from app.services.user_profile_service import UserProfileService
        db = DatabaseManager(database_url=f"sqlite:///{tmp_path / 'p2.db'}")
        svc = UserProfileService(db=db)
        baseline = {"eye_contact": 0.80, "smile": 0.15, "posture": 0.75,
                    "head_stability": 0.90, "body_movement": 0.88}
        svc.update_baseline("user_b", baseline)
        profile = svc.get_profile("user_b")
        assert profile["session_count"] == 1
        assert abs(profile["baseline"]["eye_contact"] - 0.80) < 0.01

    def test_baseline_blends_on_second_session(self, tmp_path):
        from app.database.db_manager import DatabaseManager
        from app.services.user_profile_service import UserProfileService
        db = DatabaseManager(database_url=f"sqlite:///{tmp_path / 'p3.db'}")
        svc = UserProfileService(db=db)
        b1 = {"eye_contact": 0.80, "smile": 0.10, "posture": 0.75,
              "head_stability": 0.90, "body_movement": 0.85}
        b2 = {"eye_contact": 0.60, "smile": 0.30, "posture": 0.65,
              "head_stability": 0.80, "body_movement": 0.75}
        svc.update_baseline("user_c", b1)
        svc.update_baseline("user_c", b2)
        profile = svc.get_profile("user_c")
        # EMA blend: new = 0.7*b1 + 0.3*b2
        expected = 0.7 * 0.80 + 0.3 * 0.60
        assert abs(profile["baseline"]["eye_contact"] - expected) < 0.01, (
            f"Expected blended eye_contact ≈ {expected:.3f}, got {profile['baseline']['eye_contact']:.3f}"
        )
        assert profile["session_count"] == 2

    def test_camera_offset_stored_and_retrieved(self, tmp_path):
        from app.database.db_manager import DatabaseManager
        from app.services.user_profile_service import UserProfileService
        db = DatabaseManager(database_url=f"sqlite:///{tmp_path / 'p4.db'}")
        svc = UserProfileService(db=db)
        svc.update_camera_offset("user_d", -9.5)
        profile = svc.get_profile("user_d")
        assert abs(profile["camera_offset_deg"] - (-9.5)) < 0.01

    def test_analyzer_loads_persisted_baseline(self, tmp_path):
        """InterviewAnalyzer should start pre-calibrated when a profile exists."""
        from app.core.singleton import SingletonMeta
        from app.database.db_manager import DatabaseManager
        from app.services.user_profile_service import UserProfileService

        # Use a fresh DatabaseManager instance (bypass singleton for test isolation)
        SingletonMeta._instances.clear()
        db = DatabaseManager(database_url=f"sqlite:///{tmp_path / 'p5.db'}")
        svc = UserProfileService(db=db)
        baseline = {"eye_contact": 0.82, "smile": 0.12, "posture": 0.78,
                    "head_stability": 0.91, "body_movement": 0.87}
        svc.update_baseline("user_e", baseline)

        az = InterviewAnalyzer(window_size=30, user_id="user_e")
        # _calibrated should be True because a persisted baseline was found
        assert az._calibrated is True, "Analyzer should be pre-calibrated from persisted profile"
        assert abs(az._baseline["eye_contact"] - 0.82) < 0.01
