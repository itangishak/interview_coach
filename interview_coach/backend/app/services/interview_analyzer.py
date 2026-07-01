"""Real-time interview coaching analyzer using MediaPipe Face Mesh + Pose.

Fixes applied (v2)
------------------
Item 1  — Emitted payload uses null/0 for face-gated metrics instead of frozen EMA.
           Internal EMA state is still frozen (for warm-up continuity), but the
           wire value is 0 so the frontend never shows stale numbers as live readings.
Item 2  — Frontend gating handled here by adding face_valid / pose_valid booleans
           alongside each metric so the UI can unambiguously decide to show "—".
Item 3  — Calibrating flag propagated in every payload so frontend can grey out cards.
Item 4  — Movement/stability normalization anchors tightened (moved to config):
           body_movement floor 0.003→0.0003, ceiling 0.047→0.018;
           head_stability divisor coefficient 0.15→0.06.
Item 5  — Posture: spine lean penalty added using nose-to-shoulder-midpoint ratio;
           shoulder visibility threshold raised from 0.5 to 0.65.
Item 6  — Smile: cheek-squint proxy added (eye-outer to cheekbone contraction);
           ratio score suppressed when mouth is open (jaw_open > threshold).
Item 7  — Diagnostic mode: when diagnostic=True, payload includes landmark coords
           and raw internal values for the overlay canvas and debug panel.

Previous fixes retained
-----------------------
Flaw A  — All distances ICD/shoulder-normalized.
Flaw B  — solvePnP yaw+pitch; camera offset correction.
Flaw C  — EMA α=0.3; hysteresis labels; 80th-pct smile window.
Flaw D  — None returns; excluded flag; session aggregate filtering.
Flaw E  — 2-sec calibration + persistent UserProfile baseline.
Config thresholds wired end-to-end.
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
_EMA_ALPHA_SMILE      = 0.45   # faster EMA for smile — short genuine smiles register
_YAW_THRESHOLD_DEG    = 25.0   # gate frames with |corrected yaw| beyond this
_CALIB_SECONDS        = 2      # seconds of neutral recording at session start
_SMILE_PEAK_PERCENTILE = 80    # percentile of smile window (captures events)

# Body-movement normalization anchors — module-level defaults.
# Actual runtime values are loaded from interview_config.json["normalization"]
# inside _load_config() so they can be tuned without touching source code.
_MOVEMENT_FLOOR = 0.0003   # floor: combined variance of a desk-still person
_MOVEMENT_CEIL  = 0.018    # ceil:  combined variance of noticeable fidgeting

# Head-stability normalization coefficient — module-level default.
_STABILITY_COEFF = 0.06    # std_norm = std / (icd * coeff)

# Smile cheek-squint proxy (Item 6)
_SMILE_JAW_OPEN_THRESHOLD = 0.20   # mouth_height/icd ratio above which mouth is open
_SMILE_SQUINT_WEIGHT      = 0.30   # blend: 30% squint, 70% mouth geometry

# Posture lean penalty (Item 5)
_POSTURE_LEAN_RATIO_MIN   = 0.8    # nose must be at least 0.8× sw above midpoint
_POSTURE_SHOULDER_VIS_MIN = 0.65   # raised from 0.5 (Item 5)

# Gaze calibration (Item 6)
# Number of frames captured during the "look at camera" phase at session start.
# During this window the mean iris offset is recorded and used as the zero
# reference for the eye contact metric, removing the camera-above-screen bias.
_GAZE_CALIB_SECONDS_DEFAULT = 3

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
        diagnostic_mode: bool = False,
    ) -> None:
        self.window_size = window_size
        self.fps = fps
        self.user_id = user_id
        self.diagnostic_mode = diagnostic_mode
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

        # Normalization anchors — overridable from config (Item 4)
        self._movement_floor: float = _MOVEMENT_FLOOR
        self._movement_ceil:  float = _MOVEMENT_CEIL
        self._stability_coeff: float = _STABILITY_COEFF

        # Gaze calibration (Item 6)
        self._gaze_calib_seconds: int = _GAZE_CALIB_SECONDS_DEFAULT
        self._gaze_calib_frames:  int = fps * _GAZE_CALIB_SECONDS_DEFAULT
        self._gaze_calib_buffer:  list[float] = []   # raw iris offsets
        self._gaze_calib_done:    bool = False
        self._gaze_reference_offset: float = 0.0    # mean offset when looking at camera

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

        # Item 4: load normalization anchors from config so they are tunable
        # without touching source code.
        norm = self.config.get("normalization", {})
        self._movement_floor  = float(norm.get("movement_floor",  _MOVEMENT_FLOOR))
        self._movement_ceil   = float(norm.get("movement_ceil",   _MOVEMENT_CEIL))
        self._stability_coeff = float(norm.get("stability_coeff", _STABILITY_COEFF))

        # Item 6: gaze calibration duration
        gaze_secs = int(self.config.get("gaze_calibration_seconds", _GAZE_CALIB_SECONDS_DEFAULT))
        self._gaze_calib_seconds = gaze_secs
        self._gaze_calib_frames  = self.fps * gaze_secs

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
            # Item 6: restore persisted gaze reference offset if present
            gaze_ref = float(profile.get("gaze_reference_offset", 0.0))
            if gaze_ref != 0.0:
                self._gaze_reference_offset = gaze_ref
                self._gaze_calib_done = True
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
            UserProfileService().update_camera_offset(self.user_id, pitch_deg=pitch_deg)
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

    @classmethod
    def _raw_iris_offset_from_lm(cls, lm: np.ndarray) -> float:
        """Return raw mean iris offset (before gaze-reference correction).

        This is the un-corrected value used for gaze calibration (Item 6).
        The same geometry as _iris_score_from_lm, but returns the offset
        directly so the calibration phase can record a reference baseline.
        """
        left_outer,  left_inner  = lm[33],  lm[133]
        right_outer, right_inner = lm[362], lm[263]
        left_iris,  right_iris   = lm[468], lm[473]
        left_off  = cls._iris_gaze_offset(left_outer,  left_inner,  left_iris)
        right_off = cls._iris_gaze_offset(right_outer, right_inner, right_iris)
        return (left_off + right_off) / 2.0

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
        """Returns None when face absent.

        Combines three signals (Item 6):
        - ratio_score:    mouth_width/height ratio (suppressed when jaw is open)
        - elevation_score: lip-corner elevation normalized by ICD
        - squint_score:   cheek-squint proxy (eye-outer to cheekbone contraction)

        Using cheek squint makes the metric robust to speaking, where the mouth
        opens and the ratio score collapses, producing false negatives.
        """
        if face_landmarks is None:
            return None
        lm = np.array([[p.x, p.y] for p in face_landmarks.landmark])
        icd = cls._interocular_distance(lm)

        mouth_width  = float(np.linalg.norm(lm[61] - lm[291]))
        mouth_height = float(np.linalg.norm(lm[13] - lm[14]))
        if mouth_height < 1e-6:
            return 0.0

        # Jaw open? Suppress ratio when mouth is open to avoid speech artifact.
        jaw_open = mouth_height / (icd + 1e-6)
        mouth_is_open = jaw_open > _SMILE_JAW_OPEN_THRESHOLD

        ratio = mouth_width / mouth_height
        ratio_score = 0.0 if mouth_is_open else float(np.clip((ratio - 2.0) / 3.0, 0.0, 1.0))

        lip_center_y = (lm[13][1] + lm[14][1]) / 2.0
        corner_y     = (lm[61][1] + lm[291][1]) / 2.0
        elevation_score = float(np.clip((lip_center_y - corner_y) / (icd * 0.25), 0.0, 1.0))

        # Cheek squint: y-distance between eye outer corner (33/263) and
        # infraorbital region (landmarks 116 left / 345 right in 478-mesh).
        # Contraction during genuine smiling reduces this y-gap.
        # We measure the gap relative to the resting gap (≈ icd * 0.35) and
        # score how much it has contracted.
        try:
            left_gap  = abs(lm[116][1] - lm[33][1])
            right_gap = abs(lm[345][1] - lm[263][1])
            avg_gap   = (left_gap + right_gap) / 2.0
            rest_gap  = icd * 0.35 + 1e-6
            # Squint score: low gap = more squint = real smile
            squint_score = float(np.clip(1.0 - avg_gap / rest_gap, 0.0, 1.0))
        except (IndexError, Exception):
            squint_score = 0.0

        # Blend: ratio + elevation carry 70%, cheek squint 30%
        mouth_score = 0.55 * ratio_score + 0.45 * elevation_score
        return float(np.clip(
            (1.0 - _SMILE_SQUINT_WEIGHT) * mouth_score + _SMILE_SQUINT_WEIGHT * squint_score,
            0.0, 1.0,
        ))

    @classmethod
    def head_stability_score(
        cls,
        positions: list[np.ndarray],
        window_size: int,
        icd: float = 0.12,
        stability_coeff: float | None = None,
    ) -> float | None:
        """Nose-position std normalized by ICD. Returns None when < 2 pts (Flaw D).

        Item 4: coefficient loaded from config (default _STABILITY_COEFF=0.06).
        Pass stability_coeff explicitly to use instance-level value from config.
        """
        if len(positions) < 2:
            return None
        arr = np.array(positions[-window_size:])
        std = float(np.std(arr, axis=0).mean())
        coeff = stability_coeff if stability_coeff is not None else _STABILITY_COEFF
        std_norm = std / (icd * coeff + 1e-6)
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
        movement_floor: float | None = None,
        movement_ceil: float | None = None,
    ) -> float | None:
        """Variance normalized by shoulder width (Flaw A). None when no data (Flaw D).

        Item 4: floor/ceiling anchors loaded from config when called from
        analyze_frame; fall back to module-level defaults for standalone use.
        """
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
        floor = movement_floor if movement_floor is not None else _MOVEMENT_FLOOR
        ceil  = movement_ceil  if movement_ceil  is not None else _MOVEMENT_CEIL
        denom = max(ceil - floor, 1e-8)
        return float(np.clip(1.0 - (combined - floor) / denom, 0.0, 1.0))

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
        """Shoulder tilt + lean penalty, normalized by shoulder width.

        Item 5 improvements:
        - Shoulder visibility threshold raised to _POSTURE_SHOULDER_VIS_MIN (0.65)
        - Lean penalty: measures nose-to-shoulder-midpoint y-distance vs shoulder
          width. If the ratio is below _POSTURE_LEAN_RATIO_MIN the person is
          leaning too far back or the nose is too close to the shoulders → penalty.
        - Hip-midpoint uprightness check if landmarks 23/24 are visible (spine angle).
        """
        if pose_landmarks is None:
            return None
        lm = np.array([[p.x, p.y, p.visibility] for p in pose_landmarks.landmark])
        ls, rs, nose = lm[11], lm[12], lm[0]

        # Item 5: raised visibility threshold
        if ls[2] < _POSTURE_SHOULDER_VIS_MIN or rs[2] < _POSTURE_SHOULDER_VIS_MIN:
            return None

        sw = shoulder_width or float(np.linalg.norm(ls[:2] - rs[:2])) + 1e-6
        tilt_norm = abs(ls[1] - rs[1]) / (sw * 0.4 + 1e-6)
        score     = 1.0 - tilt_norm

        # Item 5: lean penalty using nose-to-shoulder-midpoint y-distance
        shoulder_mid_y = (ls[1] + rs[1]) / 2.0
        nose_to_shoulder_y = shoulder_mid_y - nose[1]  # positive when nose above shoulders
        lean_ratio = nose_to_shoulder_y / (sw + 1e-6)
        if lean_ratio < _POSTURE_LEAN_RATIO_MIN:
            # Penalty proportional to deficit below minimum ratio
            deficit = _POSTURE_LEAN_RATIO_MIN - lean_ratio
            score *= max(0.0, 1.0 - deficit * 0.8)

        # Hip uprightness check (spine angle) if hips are visible
        if len(lm) > 24 and lm[23][2] > 0.5 and lm[24][2] > 0.5:
            hip_mid_y = (lm[23][1] + lm[24][1]) / 2.0
            # Shoulder midpoint should be above hip midpoint
            if shoulder_mid_y >= hip_mid_y:  # shoulders at or below hips → very slouched
                score *= 0.60

        return float(np.clip(score, 0.0, 1.0))


    # ──────────────────────────────────────────────────────────────────
    # EMA + Hysteresis — use config thresholds (was the discrepancy)
    # ──────────────────────────────────────────────────────────────────
    def _ema_update(self, key: str, new_val: float, alpha: float | None = None) -> float:
        a = alpha if alpha is not None else _EMA_ALPHA
        prev = self._ema.get(key, new_val)
        updated = a * new_val + (1.0 - a) * prev
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

        # ── Raw iris offset (used for gaze calibration and score) ─────
        raw_iris_offset: float | None = None
        if face_lm_arr is not None and not head_turned:
            raw_iris_offset = self._raw_iris_offset_from_lm(face_lm_arr)

        # ── Item 6: Gaze calibration ───────────────────────────────────
        # During the first _gaze_calib_frames valid face frames, record the
        # mean iris offset while the person is assumed to be looking at the
        # camera. After the window is full, set the reference offset so that
        # "looking at camera" → corrected offset ≈ 0 → score ≈ 1.0.
        if raw_iris_offset is not None and not self._gaze_calib_done:
            self._gaze_calib_buffer.append(raw_iris_offset)
            if len(self._gaze_calib_buffer) >= self._gaze_calib_frames:
                self._gaze_reference_offset = float(np.mean(self._gaze_calib_buffer))
                self._gaze_calib_done = True

        # Apply gaze reference correction to get the eye contact score
        raw_eye: float | None = None
        if raw_iris_offset is not None:
            corrected_offset = max(0.0, raw_iris_offset - self._gaze_reference_offset)
            raw_eye = float(np.clip(1.0 - corrected_offset, 0.0, 1.0))

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

        # Pass instance-level anchors from config (Item 4)
        raw_head = self.head_stability_score(
            list(self.nose_positions), self.window_size, icd,
            stability_coeff=self._stability_coeff,
        )
        raw_move = self.body_movement_score(
            list(self.shoulder_centers),
            list(self.nose_positions),
            list(self.movement_displacements),
            self.window_size,
            shoulder_w,
            movement_floor=self._movement_floor,
            movement_ceil=self._movement_ceil,
        )

        # ── Gate: face absent OR head turned beyond threshold ─────────
        excluded = not face_visible or raw_eye is None

        # ── EMA update ────────────────────────────────────────────────
        # Item 1: separate internal EMA state (frozen when excluded, for
        # warm-up continuity) from emitted wire values (0 when excluded so
        # the frontend never shows stale numbers as live readings).
        if not excluded:
            eye_contact    = self._ema_update("eye_contact", raw_eye)   # type: ignore[arg-type]
            self.smile_raw_window.append(raw_smile or 0.0)
            smile_peak     = float(np.percentile(list(self.smile_raw_window), _SMILE_PEAK_PERCENTILE))
            smile          = self._ema_update("smile", smile_peak)
            posture        = self._ema_update("posture",        raw_pos)  if raw_pos  is not None else self._ema["posture"]
            head_stability = self._ema_update("head_stability", raw_head) if raw_head is not None else self._ema["head_stability"]
            body_movement  = self._ema_update("body_movement",  raw_move) if raw_move is not None else self._ema["body_movement"]
            # Emit real values
            emit_eye_contact    = eye_contact
            emit_smile          = smile
            emit_posture        = posture
            emit_head_stability = head_stability
            emit_body_movement  = body_movement
            face_valid = True
            pose_valid = pose_visible
        else:
            # Keep frozen EMA for internal warm-up continuity
            eye_contact    = self._ema["eye_contact"]
            smile          = self._ema["smile"]
            posture        = self._ema["posture"]
            head_stability = self._ema["head_stability"]
            body_movement  = self._ema["body_movement"]
            # Emit 0 so the frontend shows inactive state, not stale readings
            emit_eye_contact    = 0.0
            emit_smile          = 0.0
            emit_posture        = 0.0 if not pose_visible else posture
            emit_head_stability = 0.0
            emit_body_movement  = 0.0 if not pose_visible else body_movement
            face_valid = False
            pose_valid = pose_visible

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
        confidence = self._compute_confidence(features) if not excluded else 0.0

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

        payload: dict[str, Any] = {
            # Item 1: emit wire values (0 when excluded), not frozen EMA
            "eye_contact":    round(emit_eye_contact,    3),
            "smile":          round(emit_smile,          3),
            "posture":        round(emit_posture,        3),
            "head_stability": round(emit_head_stability, 3),
            "body_movement":  round(emit_body_movement,  3),
            "confidence":     round(confidence,          1),
            "feedback":       feedback,
            "face_visible":   face_visible,
            "pose_visible":   pose_visible,
            # Item 1: explicit per-metric validity flags for the frontend
            "face_valid":     face_valid,
            "pose_valid":     pose_valid,
            # Item 3: calibrating flag so frontend can grey out metric cards
            "calibrating":    not self._calibrated,
            # Item 6: gaze calibration phase indicator
            "gaze_calibrating": not self._gaze_calib_done,
            "excluded":       excluded,
            "yaw_deg":        round(yaw_deg,   1),
            "pitch_deg":      round(pitch_deg, 1),
            # Legacy aliases
            "face_detected":  face_visible,
            "pose_detected":  pose_visible,
        }

        # ── Item 8: Diagnostic payload ────────────────────────────────
        # Only appended when diagnostic_mode=True to keep normal payloads lean.
        if self.diagnostic_mode:
            landmarks: dict[str, list[float]] = {}
            if face_lm_arr is not None:
                for lm_name, idx in {
                    "nose_tip": 1, "nose_bridge": 168, "chin": 152,
                    "left_eye_outer": 33, "left_eye_inner": 133,
                    "right_eye_inner": 362, "right_eye_outer": 263,
                    "left_iris": 468, "right_iris": 473,
                    "left_mouth": 61, "right_mouth": 291,
                }.items():
                    if idx < len(face_lm_arr):
                        landmarks[lm_name] = [
                            round(float(face_lm_arr[idx][0]), 4),
                            round(float(face_lm_arr[idx][1]), 4),
                        ]
            if pose_lm_arr is not None:
                for lm_name, idx in {
                    "left_shoulder": 11, "right_shoulder": 12,
                    "left_hip": 23, "right_hip": 24,
                }.items():
                    if idx < len(pose_lm_arr):
                        landmarks[lm_name] = [
                            round(float(pose_lm_arr[idx][0]), 4),
                            round(float(pose_lm_arr[idx][1]), 4),
                        ]
            payload["diagnostic"] = {
                "face_visible": face_visible, "pose_visible": pose_visible, "excluded": excluded,
                "yaw_deg": round(yaw_deg, 2), "pitch_deg": round(pitch_deg, 2), "roll_deg": round(roll_deg, 2),
                "icd": round(icd, 4), "shoulder_width": round(shoulder_w, 4),
                "raw_eye_contact":    round(raw_eye,   3) if raw_eye   is not None else None,
                "raw_iris_offset":    round(raw_iris_offset, 4) if raw_iris_offset is not None else None,
                "raw_smile":          round(raw_smile, 3) if raw_smile is not None else None,
                "raw_posture":        round(raw_pos,   3) if raw_pos   is not None else None,
                "raw_head_stability": round(raw_head,  3) if raw_head  is not None else None,
                "raw_body_movement":  round(raw_move,  3) if raw_move  is not None else None,
                "ema_eye_contact":    round(self._ema["eye_contact"],    3),
                "ema_smile":          round(self._ema["smile"],          3),
                "ema_posture":        round(self._ema["posture"],        3),
                "ema_head_stability": round(self._ema["head_stability"], 3),
                "ema_body_movement":  round(self._ema["body_movement"],  3),
                "gaze_reference_offset": round(self._gaze_reference_offset, 4),
                "gaze_calibrating":   not self._gaze_calib_done,
                "gaze_calib_frames":  len(self._gaze_calib_buffer),
                "calibrated":         self._calibrated,
                "baseline":           {k: round(v, 3) for k, v in self._baseline.items()},
                "frame_count":        len(self.nose_positions),
                "movement_floor":     self._movement_floor,
                "movement_ceil":      self._movement_ceil,
                "stability_coeff":    self._stability_coeff,
                "landmarks":          landmarks,
            }

        return payload

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
        # Reset gaze calibration (Item 6) — re-calibrate each session
        self._gaze_calib_buffer.clear()
        self._gaze_calib_done = bool(self._gaze_reference_offset != 0.0)  # keep persisted ref
        # Reload persisted baseline so new session starts pre-calibrated
        self._load_persistent_profile()
        self._baseline = dict(self._persisted_baseline)
        self._calibrated = bool(self._persisted_baseline)
