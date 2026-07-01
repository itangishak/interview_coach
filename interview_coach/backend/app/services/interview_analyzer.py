"""Real-time interview coaching analyzer using MediaPipe Face Mesh + Pose.

Fixes applied
-------------
Flaw A  — All facial distances normalized by interocular distance (ICD);
           body distances normalized by shoulder width.
Flaw B  — Full 3D yaw AND pitch estimated from 6-point PnP solve using the
           face transformation matrix landmarks; camera-above-screen pitch
           offset loaded from per-user profile and subtracted before scoring.
           Frames with |corrected_yaw| > 25° are gated (frozen, not fabricated).
Flaw C  — EMA (α=0.3) replaces brick-wall mean; hysteresis on status labels;
           smile reports 80th-percentile of rolling window.
Flaw D  — Missing face/pose → scores frozen at last known value; frame excluded
           from session aggregates; explicit face_visible/pose_visible flags.
Flaw E  — 2-second in-session neutral calibration; persistent per-user baseline
           loaded at session start and saved on session end via UserProfileService.

Config thresholds wired
-----------------------
All "good"/"okay" thresholds now come from interview_config.json (or config.yaml
defaults). FeedbackEngine._severity() and _label_with_hysteresis() both read from
self.thresholds so changing the JSON file changes the labels without code edits.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np

from app.services.feedback_engine import FeedbackEngine

# ── Module-level tuning constants ─────────────────────────────────────────────
_EMA_ALPHA            = 0.30   # EMA recent-frame weight (0.1 slow … 0.5 fast)
_YAW_THRESHOLD_DEG    = 25.0   # gate frames with |corrected yaw| beyond this
_CALIB_SECONDS        = 2      # seconds of neutral recording at session start
_SMILE_PEAK_PERCENTILE = 80    # percentile of smile window (captures events)

# 3-D reference points (MediaPipe canonical model, in mm, OpenCV coords)
# Used for solvePnP to obtain real yaw / pitch / roll from 2-D landmarks.
_MODEL_POINTS = np.array([
    [0.0,    0.0,    0.0  ],   # 1  nose tip
    [0.0,   -330.0, -65.0 ],   # 152 chin
    [-225.0,  170.0, -135.0],  # 33  left eye outer corner
    [ 225.0,  170.0, -135.0],  # 263 right eye outer corner
    [-150.0, -150.0, -125.0],  # 61  left mouth corner
    [ 150.0, -150.0, -125.0],  # 291 right mouth corner
], dtype=np.float64)

_PNP_LANDMARK_IDX = [1, 152, 33, 263, 61, 291]


class InterviewAnalyzer:
    """Analyzes webcam frames during a mock interview.

    Per-frame output keys
    ---------------------
    eye_contact     float 0–1   EMA iris-gaze score (normalized, pose-corrected)
    smile           float 0–1   80th-pct smile in rolling window → EMA
    posture         float 0–1   Shoulder symmetry + uprightness (normalized)
    head_stability  float 0–1   Nose-position variance (ICD-normalized)
    body_movement   float 0–1   Shoulder/head variance (shoulder-width-normalized)
    confidence      float 0–100 Weighted sum of above (config-weights)
    face_visible    bool        False when MediaPipe detects no face this frame
    pose_visible    bool        False when MediaPipe detects no pose this frame
    excluded        bool        True when frame is gated (not in session aggregates)
    yaw_deg         float       Corrected head yaw (camera-offset subtracted)
    pitch_deg       float       Corrected head pitch
    """

    _feature_names = ["eye_contact", "smile", "posture", "head_stability", "body_movement"]
    _HYSTERESIS = 0.05   # half-band for label hysteresis

    # Default thresholds used when config doesn't specify them
    _DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
        "eye_contact":    {"good": 0.70, "okay": 0.40},
        "smile":          {"good": 0.50, "okay": 0.20},
        "posture":        {"good": 0.70, "okay": 0.50},
        "head_stability": {"good": 0.70, "okay": 0.40},
        "body_movement":  {"good": 0.70, "okay": 0.40},
        "confidence":     {"good": 0.70, "okay": 0.40},
    }

    def __init__(
        self,
        config_path: str | Path | None = None,
        window_size: int = 30,
        fps: int = 15,
        user_id: str | None = None,
    ) -> None:
        self.window_size = window_size
        self.fps = fps
        self.user_id = user_id
        self.config: dict[str, Any] = {}
        self.weights = {
            "eye_contact":    0.30,
            "smile":          0.15,
            "posture":        0.20,
            "head_stability": 0.20,
            "body_movement":  0.15,
        }
        # Start with defaults; _load_config merges from JSON
        self.thresholds: dict[str, dict[str, float]] = {
            k: dict(v) for k, v in self._DEFAULT_THRESHOLDS.items()
        }
        self._load_config(config_path)

        # Camera pitch offset (degrees) — how far the webcam sits above the
        # centre of the monitor.  Subtracted from every pitch estimate so that
        # genuine "look at interviewer on screen" is neutral, not penalized.
        self._camera_pitch_offset_deg: float = 0.0

        # Persistent baseline (loaded from UserProfileService when user_id given)
        self._persisted_baseline: dict[str, float] = {}
        self._load_persistent_profile()

        # ── MediaPipe ─────────────────────────────────────────────────
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        )

        # ── Rolling windows ───────────────────────────────────────────
        win = window_size * 2
        self.nose_positions: deque[np.ndarray] = deque(maxlen=win)
        self.shoulder_centers: deque[np.ndarray] = deque(maxlen=win)
        self.movement_displacements: deque[float] = deque(maxlen=win)
        self.smile_raw_window: deque[float] = deque(maxlen=window_size)

        # ── EMA state ─────────────────────────────────────────────────
        self._ema: dict[str, float] = {
            "eye_contact":    0.5,
            "smile":          0.0,
            "posture":        0.8,
            "head_stability": 1.0,
            "body_movement":  1.0,
        }

        # ── Hysteresis label state ─────────────────────────────────────
        self._label_state: dict[str, str] = {}

        # ── In-session calibration ─────────────────────────────────────
        self._calib_frames = fps * _CALIB_SECONDS
        self._calib_buffer: list[dict[str, float]] = []
        self._baseline: dict[str, float] = dict(self._persisted_baseline)
        self._calibrated = bool(self._persisted_baseline)  # pre-calibrated if profile exists

        self.feedback_engine = FeedbackEngine(self.thresholds)

        # ── Frame dimensions (set on first frame for PnP) ─────────────
        self._frame_w: int = 640
        self._frame_h: int = 480


    # ──────────────────────────────────────────────────────────────────
    # Config loading — thresholds fully wired (was the discrepancy)
    # ──────────────────────────────────────────────────────────────────
    def _load_config(self, config_path: str | Path | None) -> None:
        if config_path is None:
            root = Path(__file__).resolve().parents[2]
            config_path = root / "checkpoints" / "interview" / "interview_config.json"
        config_path = Path(config_path)

        if not config_path.exists():
            self.config = {
                "feature_names": self._feature_names,
                "confidence_weights": self.weights,
                "thresholds": self.thresholds,
                "window_size": self.window_size,
            }
            return

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.weights = self.config.get("confidence_weights", self.weights)
        self.window_size = self.config.get("window_size", self.window_size)

        # Merge config thresholds over defaults — only overwrite keys present in JSON
        for metric, values in self.config.get("thresholds", {}).items():
            self.thresholds.setdefault(metric, {}).update(values)

    # ──────────────────────────────────────────────────────────────────
    # Persistent profile I/O (Flaw E — cross-session)
    # ──────────────────────────────────────────────────────────────────
    def _load_persistent_profile(self) -> None:
        if not self.user_id:
            return
        try:
            from app.services.user_profile_service import UserProfileService
            svc = UserProfileService()
            profile = svc.get_profile(self.user_id)
            self._persisted_baseline = profile.get("baseline", {})
            self._camera_pitch_offset_deg = float(
                profile.get("camera_offset_deg", 0.0)
            )
        except Exception:
            pass  # DB unavailable — degrade gracefully

    def save_session_baseline(self) -> None:
        """Call at session end to persist this session's baseline for the user."""
        if not self.user_id or not self._calibrated or not self._baseline:
            return
        try:
            from app.services.user_profile_service import UserProfileService
            UserProfileService().update_baseline(self.user_id, self._baseline)
        except Exception:
            pass

    def set_camera_offset(self, pitch_deg: float) -> None:
        """Set and persist camera pitch offset for this user."""
        self._camera_pitch_offset_deg = pitch_deg
        if not self.user_id:
            return
        try:
            from app.services.user_profile_service import UserProfileService
            UserProfileService().update_camera_offset(self.user_id, pitch_deg)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    # Scale reference helpers
    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _interocular_distance(lm: np.ndarray) -> float:
        """Distance between outer eye corners 33 and 263 (frame-normalized)."""
        return float(np.linalg.norm(lm[33] - lm[263])) + 1e-6

    @staticmethod
    def _shoulder_width(lm: np.ndarray) -> float:
        """Distance between left (11) and right (12) shoulder keypoints."""
        return float(np.linalg.norm(lm[11] - lm[12])) + 1e-6

    # ──────────────────────────────────────────────────────────────────
    # 3-D head-pose estimation via solvePnP (Flaw B — full fix)
    # ──────────────────────────────────────────────────────────────────
    def estimate_head_pose(
        self, lm: np.ndarray, frame_w: int, frame_h: int
    ) -> tuple[float, float, float]:
        """Return (yaw_deg, pitch_deg, roll_deg) via solvePnP.

        2-D image points come from 6 stable landmarks (nose tip, chin, eye
        corners, mouth corners).  Camera matrix is estimated from frame size
        (focal ≈ frame_width, principal point = frame centre).

        Camera-above-screen pitch offset is subtracted from pitch so that
        genuine eye contact with the on-screen interviewer reads as ~0°.

        Returns (yaw_deg, corrected_pitch_deg, roll_deg).
        On failure falls back to the fast geometric yaw estimate.
        """
        image_points = np.array(
            [lm[idx, :2] * np.array([frame_w, frame_h]) for idx in _PNP_LANDMARK_IDX],
            dtype=np.float64,
        )
        focal = float(frame_w)
        cx, cy = frame_w / 2.0, frame_h / 2.0
        camera_matrix = np.array(
            [[focal, 0, cx], [0, focal, cy], [0, 0, 1]], dtype=np.float64
        )
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        ok, rvec, _ = cv2.solvePnP(
            _MODEL_POINTS, image_points, camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            # Fallback: geometric yaw only
            yaw = self._geometric_yaw(lm)
            return yaw, 0.0, 0.0

        rmat, _ = cv2.Rodrigues(rvec)
        # Decompose rotation matrix into Euler angles (XYZ convention)
        sy = float(np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2))
        singular = sy < 1e-6
        if not singular:
            pitch = float(np.degrees(np.arctan2(-rmat[2, 0], sy)))
            yaw   = float(np.degrees(np.arctan2( rmat[1, 0], rmat[0, 0])))
            roll  = float(np.degrees(np.arctan2( rmat[2, 1], rmat[2, 2])))
        else:
            pitch = float(np.degrees(np.arctan2(-rmat[2, 0], sy)))
            yaw   = float(np.degrees(np.arctan2(-rmat[1, 2], rmat[1, 1])))
            roll  = 0.0

        # Subtract camera-above-screen offset so "looking at interviewer" → pitch ≈ 0
        corrected_pitch = pitch - self._camera_pitch_offset_deg
        return yaw, corrected_pitch, roll

    @staticmethod
    def _geometric_yaw(lm: np.ndarray) -> float:
        """Fast fallback: nose-tip x-offset relative to ICD → approximate yaw°."""
        nose_x    = lm[4, 0]
        eye_mid_x = (lm[33, 0] + lm[263, 0]) / 2.0
        icd       = float(np.linalg.norm(lm[33] - lm[263])) + 1e-6
        offset    = (nose_x - eye_mid_x) / icd
        return float(np.degrees(np.arctan(offset * 2.5)))

    # Keep old name as alias
    @staticmethod
    def estimate_yaw_deg(lm: np.ndarray) -> float:
        return InterviewAnalyzer._geometric_yaw(lm)


    # ──────────────────────────────────────────────────────────────────
    # Metric helpers (all ICD/shoulder-normalized — Flaw A)
    # ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _iris_gaze_offset(
        outer: np.ndarray, inner: np.ndarray, iris: np.ndarray
    ) -> float:
        """Iris offset relative to eye width (scale-independent)."""
        eye_vec = inner - outer
        eye_len = float(np.linalg.norm(eye_vec)) + 1e-6
        iris_proj = float(np.dot(iris - outer, eye_vec) / (eye_len ** 2))
        h_offset = abs(iris_proj - 0.5) * 2.0
        eye_mid_y = (outer[1] + inner[1]) / 2.0
        v_offset = abs(iris[1] - eye_mid_y) / (eye_len * 0.35 + 1e-6)
        return (h_offset + v_offset) / 2.0

    @classmethod
    def iris_eye_contact_score(cls, face_landmarks) -> float | None:
        """Returns None when face absent or yaw gated.
        Normalized by eye width → distance-independent.
        Note: full yaw+pitch correction happens in analyze_frame via solvePnP;
        this classmethod only does the geometric yaw fallback for standalone use.
        """
        if face_landmarks is None:
            return None
        lm = np.array([[p.x, p.y] for p in face_landmarks.landmark])
        yaw = cls._geometric_yaw(lm)
        if abs(yaw) > _YAW_THRESHOLD_DEG:
            return None
        return cls._iris_score_from_lm(lm)

    @classmethod
    def _iris_score_from_lm(cls, lm: np.ndarray) -> float:
        """Compute iris score from pre-extracted landmark array."""
        left_outer,  left_inner  = lm[33],  lm[133]
        right_outer, right_inner = lm[362], lm[263]
        left_iris,  right_iris   = lm[468], lm[473]
        left_off  = cls._iris_gaze_offset(left_outer,  left_inner,  left_iris)
        right_off = cls._iris_gaze_offset(right_outer, right_inner, right_iris)
        avg_offset = (left_off + right_off) / 2.0
        return float(np.clip(1.0 - avg_offset, 0.0, 1.0))

    @classmethod
    def raw_smile_score(cls, face_landmarks) -> float | None:
        """Returns None when face absent. Elevation normalized by ICD (Flaw A)."""
        if face_landmarks is None:
            return None
        lm = np.array([[p.x, p.y] for p in face_landmarks.landmark])
        icd = cls._interocular_distance(lm)
        mouth_width  = float(np.linalg.norm(lm[61] - lm[291]))
        mouth_height = float(np.linalg.norm(lm[13] - lm[14]))
        if mouth_height < 1e-6:
            return 0.0
        ratio       = mouth_width / mouth_height
        ratio_score = float(np.clip((ratio - 2.0) / 3.0, 0.0, 1.0))
        lip_center_y = (lm[13][1] + lm[14][1]) / 2.0
        corner_y     = (lm[61][1] + lm[291][1]) / 2.0
        elevation_score = float(np.clip(
            (lip_center_y - corner_y) / (icd * 0.25), 0.0, 1.0
        ))
        return 0.55 * ratio_score + 0.45 * elevation_score

    @classmethod
    def head_stability_score(
        cls,
        positions: list[np.ndarray],
        window_size: int,
        icd: float = 0.12,
    ) -> float | None:
        """Nose-position std normalized by ICD. Returns None when < 2 pts (Flaw D)."""
        if len(positions) < 2:
            return None
        arr = np.array(positions[-window_size:])
        std = float(np.std(arr, axis=0).mean())
        std_norm = std / (icd * 0.15 + 1e-6)
        return float(np.clip(1.0 - std_norm, 0.0, 1.0))

    @classmethod
    def head_stability_from_positions(
        cls, positions: list[np.ndarray], window_size: int
    ) -> float:
        result = cls.head_stability_score(positions, window_size)
        return result if result is not None else 1.0

    @classmethod
    def body_movement_score(
        cls,
        shoulder_centers: list[np.ndarray],
        nose_positions: list[np.ndarray],
        displacements: list[float],
        window_size: int,
        shoulder_width: float = 0.20,
    ) -> float | None:
        """Variance normalized by shoulder width (Flaw A). None when no data (Flaw D)."""
        if len(shoulder_centers) < 2 and not displacements:
            return None
        shoulder_var = 0.0
        if len(shoulder_centers) >= 2:
            arr = np.array(shoulder_centers[-window_size:])
            shoulder_var = float(np.var(arr, axis=0).mean()) / (shoulder_width ** 2 + 1e-8)
        head_var = 0.0
        if len(nose_positions) >= 2:
            arr = np.array(nose_positions[-window_size:])
            head_var = float(np.var(arr, axis=0).mean()) / (shoulder_width ** 2 + 1e-8)
        disp_mean = (
            float(np.mean(displacements[-window_size:])) / (shoulder_width + 1e-6)
            if displacements else 0.0
        )
        combined = 0.45 * shoulder_var + 0.35 * head_var + 0.20 * disp_mean
        return float(np.clip(1.0 - (combined - 0.003) / 0.047, 0.0, 1.0))

    @classmethod
    def body_movement_from_buffers(
        cls,
        shoulder_centers: list[np.ndarray],
        nose_positions: list[np.ndarray],
        displacements: list[float],
        window_size: int,
    ) -> float:
        result = cls.body_movement_score(shoulder_centers, nose_positions, displacements, window_size)
        return result if result is not None else 1.0

    @classmethod
    def posture_score(cls, pose_landmarks, shoulder_width: float | None = None) -> float | None:
        """Shoulder tilt normalized by shoulder width. None when absent (Flaw D)."""
        if pose_landmarks is None:
            return None
        lm = np.array([[p.x, p.y, p.visibility] for p in pose_landmarks.landmark])
        ls, rs, nose = lm[11], lm[12], lm[0]
        if ls[2] < 0.5 or rs[2] < 0.5:
            return None
        sw = shoulder_width or float(np.linalg.norm(ls[:2] - rs[:2])) + 1e-6
        tilt_norm = abs(ls[1] - rs[1]) / (sw * 0.4 + 1e-6)
        upright   = nose[1] < min(ls[1], rs[1])
        score     = 1.0 - tilt_norm
        if not upright:
            score *= 0.7
        return float(np.clip(score, 0.0, 1.0))


    # ──────────────────────────────────────────────────────────────────
    # EMA + Hysteresis — use config thresholds (was the discrepancy)
    # ──────────────────────────────────────────────────────────────────
    def _ema_update(self, key: str, new_val: float) -> float:
        prev = self._ema.get(key, new_val)
        updated = _EMA_ALPHA * new_val + (1.0 - _EMA_ALPHA) * prev
        self._ema[key] = updated
        return updated

    def _threshold(self, metric: str, level: str) -> float:
        """Read good/okay threshold from config; fall back to defaults."""
        return float(
            self.thresholds.get(metric, self._DEFAULT_THRESHOLDS.get(metric, {})).get(
                level,
                0.70 if level == "good" else 0.40,
            )
        )

    def _label_with_hysteresis(
        self, key: str, value: float, higher_is_better: bool = True
    ) -> str:
        """Status label using per-metric config thresholds + hysteresis band."""
        current = self._label_state.get(key, "")
        h = self._HYSTERESIS

        # Use configured thresholds (fixes the discrepancy)
        good_t = self._threshold(key, "good")
        okay_t = self._threshold(key, "okay")

        if higher_is_better:
            if value >= good_t + h or (current == "Good" and value >= good_t - h):
                label = "Good"
            elif value >= okay_t + h or (current == "Okay" and value >= okay_t - h):
                label = "Okay"
            else:
                label = "Needs improvement"
        else:
            # Inverted scale (body_movement: higher score = less movement = better)
            # "Needs improvement" when score is low
            if value <= okay_t - good_t - h or (
                current == "Needs improvement" and value <= okay_t - good_t + h
            ):
                label = "Needs improvement"
            elif value <= okay_t + h or (current == "Okay" and value <= okay_t + h):
                label = "Okay"
            else:
                label = "Good"

        self._label_state[key] = label
        return label

    # ──────────────────────────────────────────────────────────────────
    # Calibration — in-session + persistent (Flaw E)
    # ──────────────────────────────────────────────────────────────────
    def _update_calibration(self, raw: dict[str, float]) -> None:
        if self._calibrated:
            return
        self._calib_buffer.append(raw)
        if len(self._calib_buffer) >= self._calib_frames:
            session_baseline = {
                k: float(np.median([f[k] for f in self._calib_buffer if k in f]))
                for k in self._feature_names
            }
            # Blend with persisted baseline if available
            if self._persisted_baseline:
                for k in self._feature_names:
                    old = self._persisted_baseline.get(k)
                    new = session_baseline.get(k)
                    if old is not None and new is not None:
                        session_baseline[k] = round(
                            0.7 * float(old) + 0.3 * float(new), 4
                        )
            self._baseline = session_baseline
            self._calibrated = True

    def _deviation_from_baseline(self, key: str, value: float) -> float:
        if not self._calibrated or key not in self._baseline:
            return value
        b = self._baseline[key]
        if b < 0.05:
            return value
        return float(np.clip(value / b, 0.0, 1.0))


    # ──────────────────────────────────────────────────────────────────
    # Main analysis loop
    # ──────────────────────────────────────────────────────────────────
    def analyze_frame(self, frame: np.ndarray) -> dict[str, Any]:
        """Process a single BGR frame and return metrics + feedback."""
        h, w = frame.shape[:2]
        self._frame_h, self._frame_w = h, w

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_result = self.face_mesh.process(rgb)
        pose_result = self.pose.process(rgb)

        face_lm_raw = (
            face_result.multi_face_landmarks[0] if face_result.multi_face_landmarks else None
        )
        pose_lm_raw = pose_result.pose_landmarks

        face_visible = face_lm_raw is not None
        pose_visible = pose_lm_raw is not None

        icd: float = 0.12
        shoulder_w: float = 0.20
        face_lm_arr: np.ndarray | None = None
        pose_lm_arr: np.ndarray | None = None

        if face_visible:
            face_lm_arr = np.array([[p.x, p.y] for p in face_lm_raw.landmark])
            icd = self._interocular_distance(face_lm_arr)

        if pose_visible:
            pose_lm_arr = np.array([[p.x, p.y] for p in pose_lm_raw.landmark])
            shoulder_w = self._shoulder_width(pose_lm_arr)

        # ── 3-D head pose (Flaw B full fix) ───────────────────────────
        yaw_deg: float = 0.0
        pitch_deg: float = 0.0
        roll_deg: float = 0.0
        head_turned = False

        if face_visible and face_lm_arr is not None:
            yaw_deg, pitch_deg, roll_deg = self.estimate_head_pose(
                face_lm_arr, w, h
            )
            head_turned = abs(yaw_deg) > _YAW_THRESHOLD_DEG

        # ── Raw metric scores ─────────────────────────────────────────
        # Eye contact: use solvePnP-corrected yaw gate instead of geometric
        if face_lm_arr is not None and not head_turned:
            raw_eye: float | None = self._iris_score_from_lm(face_lm_arr)
        else:
            raw_eye = None

        raw_smile = self.raw_smile_score(face_lm_raw)
        raw_pos   = self.posture_score(pose_lm_raw, shoulder_w)

        if face_visible and face_lm_arr is not None:
            self.nose_positions.append(face_lm_arr[4].copy())

        if pose_visible and pose_lm_arr is not None:
            center = (pose_lm_arr[11] + pose_lm_arr[12]) / 2.0
            if self.shoulder_centers:
                self.movement_displacements.append(
                    float(np.linalg.norm(center - self.shoulder_centers[-1]))
                )
            self.shoulder_centers.append(center)

        raw_head = self.head_stability_score(list(self.nose_positions), self.window_size, icd)
        raw_move = self.body_movement_score(
            list(self.shoulder_centers),
            list(self.nose_positions),
            list(self.movement_displacements),
            self.window_size,
            shoulder_w,
        )

        # ── Gate: face absent OR head turned beyond threshold ─────────
        excluded = not face_visible or raw_eye is None

        if not excluded:
            eye_contact = self._ema_update("eye_contact", raw_eye)   # type: ignore[arg-type]
            self.smile_raw_window.append(raw_smile or 0.0)
            smile_peak = float(np.percentile(list(self.smile_raw_window), _SMILE_PEAK_PERCENTILE))
            smile = self._ema_update("smile", smile_peak)
            posture       = self._ema_update("posture",        raw_pos)   if raw_pos   is not None else self._ema["posture"]
            head_stability = self._ema_update("head_stability", raw_head) if raw_head  is not None else self._ema["head_stability"]
            body_movement  = self._ema_update("body_movement",  raw_move) if raw_move  is not None else self._ema["body_movement"]
        else:
            eye_contact    = self._ema["eye_contact"]
            smile          = self._ema["smile"]
            posture        = self._ema["posture"]
            head_stability = self._ema["head_stability"]
            body_movement  = self._ema["body_movement"]

        if not excluded:
            self._update_calibration({
                "eye_contact":    eye_contact,
                "smile":          smile,
                "posture":        posture,
                "head_stability": head_stability,
                "body_movement":  body_movement,
            })

        adj_ec = self._deviation_from_baseline("eye_contact",    eye_contact)
        adj_sm = self._deviation_from_baseline("smile",          smile)
        adj_ps = self._deviation_from_baseline("posture",        posture)
        adj_hs = self._deviation_from_baseline("head_stability", head_stability)
        adj_mv = self._deviation_from_baseline("body_movement",  body_movement)

        features = np.array([adj_ec, adj_sm, adj_ps, adj_hs, adj_mv], dtype=np.float32)
        confidence = self._compute_confidence(features)

        feedback = self.feedback_engine.generate(
            eye_contact    = eye_contact,
            smile          = smile,
            posture        = posture,
            head_stability = head_stability,
            body_movement  = body_movement,
            confidence     = confidence,
            face_visible   = face_visible,
            calibrating    = not self._calibrated,
            label_fn       = self._label_with_hysteresis,
        )

        return {
            "eye_contact":     round(eye_contact,     3),
            "smile":           round(smile,           3),
            "posture":         round(posture,          3),
            "head_stability":  round(head_stability,   3),
            "body_movement":   round(body_movement,    3),
            "confidence":      round(confidence,       1),
            "feedback":        feedback,
            "face_visible":    face_visible,
            "pose_visible":    pose_visible,
            "excluded":        excluded,
            "yaw_deg":         round(yaw_deg,          1),
            "pitch_deg":       round(pitch_deg,        1),
            # Legacy aliases
            "face_detected":   face_visible,
            "pose_detected":   pose_visible,
        }

    def _compute_confidence(self, features: np.ndarray) -> float:
        weights = np.array(
            [self.weights[k] for k in self._feature_names], dtype=np.float32
        )
        return float(np.clip(float(features @ weights) * 100.0, 0.0, 100.0))

    def reset(self) -> None:
        """Clear per-session state for a new session."""
        self.nose_positions.clear()
        self.shoulder_centers.clear()
        self.movement_displacements.clear()
        self.smile_raw_window.clear()
        self._ema = {
            "eye_contact":    0.5,
            "smile":          0.0,
            "posture":        0.8,
            "head_stability": 1.0,
            "body_movement":  1.0,
        }
        self._label_state.clear()
        self._calib_buffer.clear()
        # Reload persisted baseline so new session starts pre-calibrated
        self._load_persistent_profile()
        self._baseline = dict(self._persisted_baseline)
        self._calibrated = bool(self._persisted_baseline)
