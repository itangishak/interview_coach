"""Real-time interview coaching analyzer using MediaPipe Face Mesh + Pose."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np

from app.services.feedback_engine import FeedbackEngine


class InterviewAnalyzer:
    """
    Analyzes webcam frames during a mock interview.

    Outputs per-frame metrics:
        - eye_contact (0..1) — iris landmarks 468–477 relative to eye corners
        - smile (0..1) — width/height ratio + corner elevation, temporally smoothed
        - posture (0..1)
        - head_stability (0..1) — nose variance over rolling window
        - body_movement (0..1) — shoulder + head variance over rolling window
        - confidence (0..100)
    """

    _feature_names = ["eye_contact", "smile", "posture", "head_stability", "body_movement"]

    def __init__(
        self,
        config_path: str | Path | None = None,
        window_size: int = 30,
    ) -> None:
        self.window_size = window_size
        self.config: dict[str, Any] = {}
        self.weights = {
            "eye_contact": 0.30,
            "smile": 0.15,
            "posture": 0.20,
            "head_stability": 0.20,
            "body_movement": 0.15,
        }
        self.thresholds: dict[str, dict[str, float]] = {}

        self._load_config(config_path)

        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self.nose_positions: deque[np.ndarray] = deque(maxlen=window_size * 2)
        self.shoulder_centers: deque[np.ndarray] = deque(maxlen=window_size * 2)
        self.movement_displacements: deque[float] = deque(maxlen=window_size * 2)

        self.eye_contact_scores: deque[float] = deque(maxlen=window_size)
        self.smile_scores: deque[float] = deque(maxlen=window_size)

        self.feedback_engine = FeedbackEngine(self.thresholds)

    def _load_config(self, config_path: str | Path | None) -> None:
        if config_path is None:
            root = Path(__file__).resolve().parents[2]
            config_path = root / "checkpoints" / "interview" / "interview_config.json"
        config_path = Path(config_path)

        if not config_path.exists():
            self.config = {
                "feature_names": self._feature_names,
                "confidence_weights": self.weights,
                "thresholds": {},
                "window_size": self.window_size,
            }
            return

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.weights = self.config.get("confidence_weights", self.weights)
        self.thresholds = self.config.get("thresholds", {})
        self.window_size = self.config.get("window_size", self.window_size)

    # ------------------------------------------------------------------
    # Feature helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _iris_gaze_offset(outer: np.ndarray, inner: np.ndarray, iris: np.ndarray) -> float:
        """Horizontal + vertical iris offset within the eye socket (0 = centered)."""
        eye_vec = inner - outer
        eye_len = float(np.linalg.norm(eye_vec)) + 1e-6
        iris_proj = float(np.dot(iris - outer, eye_vec) / (eye_len**2))
        h_offset = abs(iris_proj - 0.5) * 2.0

        eye_mid_y = (outer[1] + inner[1]) / 2.0
        v_offset = abs(iris[1] - eye_mid_y) / (eye_len * 0.35 + 1e-6)
        return (h_offset + v_offset) / 2.0

    @classmethod
    def iris_eye_contact_score(cls, face_landmarks) -> float:
        """Iris landmarks 468–477 relative to eye corners 33/133 and 362/263."""
        if face_landmarks is None:
            return 0.0

        lm = np.array([[p.x, p.y] for p in face_landmarks.landmark])

        left_outer, left_inner = lm[33], lm[133]
        right_outer, right_inner = lm[362], lm[263]
        left_iris, right_iris = lm[468], lm[473]

        left_offset = cls._iris_gaze_offset(left_outer, left_inner, left_iris)
        right_offset = cls._iris_gaze_offset(right_outer, right_inner, right_iris)
        avg_offset = (left_offset + right_offset) / 2.0
        return float(np.clip(1.0 - avg_offset, 0.0, 1.0))

    @classmethod
    def raw_smile_score(cls, face_landmarks) -> float:
        """Width/height mouth ratio plus corner elevation."""
        if face_landmarks is None:
            return 0.0

        lm = np.array([[p.x, p.y] for p in face_landmarks.landmark])
        mouth_width = float(np.linalg.norm(lm[61] - lm[291]))
        mouth_height = float(np.linalg.norm(lm[13] - lm[14]))
        if mouth_height < 1e-6:
            return 0.0

        ratio = mouth_width / mouth_height
        ratio_score = float(np.clip((ratio - 2.0) / 3.0, 0.0, 1.0))

        lip_center_y = (lm[13][1] + lm[14][1]) / 2.0
        corner_y = (lm[61][1] + lm[291][1]) / 2.0
        elevation = lip_center_y - corner_y
        elevation_score = float(np.clip(elevation / 0.015, 0.0, 1.0))

        return 0.55 * ratio_score + 0.45 * elevation_score

    def _smooth(self, buffer: deque[float], raw: float) -> float:
        buffer.append(raw)
        if not buffer:
            return raw
        return float(np.mean(buffer))

    @classmethod
    def head_stability_from_positions(cls, positions: list[np.ndarray], window_size: int) -> float:
        if len(positions) < 2:
            return 1.0
        arr = np.array(positions[-window_size:])
        std = float(np.std(arr, axis=0).mean())
        score = 1.0 - (std - 0.008) / 0.035
        return float(np.clip(score, 0.0, 1.0))

    @classmethod
    def body_movement_from_buffers(
        cls,
        shoulder_centers: list[np.ndarray],
        nose_positions: list[np.ndarray],
        displacements: list[float],
        window_size: int,
    ) -> float:
        if not displacements and len(shoulder_centers) < 2:
            return 1.0

        shoulder_var = 0.0
        if len(shoulder_centers) >= 2:
            shoulder_arr = np.array(shoulder_centers[-window_size:])
            shoulder_var = float(np.var(shoulder_arr, axis=0).mean())

        head_var = 0.0
        if len(nose_positions) >= 2:
            head_arr = np.array(nose_positions[-window_size:])
            head_var = float(np.var(head_arr, axis=0).mean())

        disp_mean = float(np.mean(displacements[-window_size:])) if displacements else 0.0
        combined = 0.45 * shoulder_var + 0.35 * head_var + 0.20 * disp_mean
        score = 1.0 - (combined - 0.003) / 0.022
        return float(np.clip(score, 0.0, 1.0))

    @staticmethod
    def posture_score(pose_landmarks) -> float:
        if pose_landmarks is None:
            return 0.5
        lm = np.array([[p.x, p.y, p.visibility] for p in pose_landmarks.landmark])
        left_shoulder = lm[11]
        right_shoulder = lm[12]
        nose = lm[0]
        if left_shoulder[2] < 0.5 or right_shoulder[2] < 0.5:
            return 0.5
        shoulder_diff = abs(left_shoulder[1] - right_shoulder[1])
        upright = nose[1] < min(left_shoulder[1], right_shoulder[1])
        score = 1.0 - shoulder_diff * 5.0
        if not upright:
            score *= 0.7
        return float(np.clip(score, 0.0, 1.0))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze_frame(self, frame: np.ndarray) -> dict[str, Any]:
        """Analyze a single BGR frame and return metrics + feedback."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_result = self.face_mesh.process(rgb)
        pose_result = self.pose.process(rgb)

        face_lm = face_result.multi_face_landmarks[0] if face_result.multi_face_landmarks else None
        pose_lm = pose_result.pose_landmarks

        raw_eye = self.iris_eye_contact_score(face_lm)
        raw_smile = self.raw_smile_score(face_lm)
        eye_contact = self._smooth(self.eye_contact_scores, raw_eye)
        smile = self._smooth(self.smile_scores, raw_smile)
        posture = self.posture_score(pose_lm)

        if face_lm:
            nose = np.array([face_lm.landmark[4].x, face_lm.landmark[4].y], dtype=np.float32)
            self.nose_positions.append(nose)

        if pose_lm:
            lm = np.array([[p.x, p.y] for p in pose_lm.landmark], dtype=np.float32)
            center = (lm[11] + lm[12]) / 2.0
            if self.shoulder_centers:
                prev = self.shoulder_centers[-1]
                disp = float(np.linalg.norm(center - prev))
                self.movement_displacements.append(disp)
            self.shoulder_centers.append(center)

        head_stability = self.head_stability_from_positions(
            list(self.nose_positions), self.window_size
        )
        body_movement = self.body_movement_from_buffers(
            list(self.shoulder_centers),
            list(self.nose_positions),
            list(self.movement_displacements),
            self.window_size,
        )

        features = np.array(
            [eye_contact, smile, posture, head_stability, body_movement],
            dtype=np.float32,
        )
        confidence = self._compute_confidence(features)
        feedback = self.feedback_engine.generate(
            eye_contact=eye_contact,
            smile=smile,
            posture=posture,
            head_stability=head_stability,
            body_movement=body_movement,
            confidence=confidence,
        )

        return {
            "eye_contact": round(eye_contact, 3),
            "smile": round(smile, 3),
            "posture": round(posture, 3),
            "head_stability": round(head_stability, 3),
            "body_movement": round(body_movement, 3),
            "confidence": round(confidence, 1),
            "feedback": feedback,
            "face_detected": face_lm is not None,
            "pose_detected": pose_lm is not None,
        }

    def _compute_confidence(self, features: np.ndarray) -> float:
        """Weighted sum of normalised metric scores, scaled to 0–100."""
        weights = np.array(
            [
                self.weights["eye_contact"],
                self.weights["smile"],
                self.weights["posture"],
                self.weights["head_stability"],
                self.weights["body_movement"],
            ],
            dtype=np.float32,
        )
        score = float(features @ weights) * 100.0
        return float(np.clip(score, 0.0, 100.0))

    def reset(self) -> None:
        """Clear rolling buffers for a new session."""
        self.nose_positions.clear()
        self.shoulder_centers.clear()
        self.movement_displacements.clear()
        self.eye_contact_scores.clear()
        self.smile_scores.clear()