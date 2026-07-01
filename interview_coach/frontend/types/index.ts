export interface MetricDetail {
  score: number;
  status: "Good" | "Okay" | "Needs improvement";
}

export interface FeedbackPayload {
  eye_contact: MetricDetail;
  smile: MetricDetail;
  posture: MetricDetail;
  head_stability: MetricDetail;
  body_movement: MetricDetail;
  confidence: MetricDetail;
  recommendations: string[];
}

export interface DiagnosticLandmarks {
  nose_tip?: [number, number];
  nose_bridge?: [number, number];
  chin?: [number, number];
  left_eye_outer?: [number, number];
  left_eye_inner?: [number, number];
  right_eye_inner?: [number, number];
  right_eye_outer?: [number, number];
  left_iris?: [number, number];
  right_iris?: [number, number];
  left_mouth?: [number, number];
  right_mouth?: [number, number];
  left_shoulder?: [number, number];
  right_shoulder?: [number, number];
  left_hip?: [number, number];
  right_hip?: [number, number];
}

export interface DiagnosticPayload {
  face_visible: boolean;
  pose_visible: boolean;
  excluded: boolean;
  latency_ms?: {
    prep: number;
    face: number;
    pose: number;
    total: number;
  };
  yaw_deg: number;
  pitch_deg: number;
  roll_deg: number;
  icd: number;
  shoulder_width: number;
  raw_eye_contact: number | null;
  raw_iris_offset: number | null;
  raw_smile: number | null;
  raw_posture: number | null;
  raw_head_stability: number | null;
  raw_body_movement: number | null;
  ema_eye_contact: number;
  ema_smile: number;
  ema_posture: number;
  ema_head_stability: number;
  ema_body_movement: number;
  gaze_reference_offset: number;
  gaze_calibrating: boolean;
  gaze_calib_frames: number;
  calibrated: boolean;
  baseline: Record<string, number>;
  frame_count: number;
  movement_floor: number;
  movement_ceil: number;
  stability_coeff: number;
  landmarks: DiagnosticLandmarks;
}

export interface AnalysisPayload {
  eye_contact: number;        // 0–1  (0 when face absent — Item 1)
  smile: number;              // 0–1
  posture: number;            // 0–1
  head_stability: number;     // 0–1
  body_movement: number;      // 0–1 (higher = less movement = better)
  confidence: number;         // 0–100 (0 when face absent)
  feedback: FeedbackPayload;
  face_visible: boolean;
  pose_visible: boolean;
  // Item 1: per-metric validity flags — false when detection is absent
  face_valid: boolean;
  pose_valid: boolean;
  // Item 3: calibration flags
  calibrating: boolean;
  gaze_calibrating: boolean;
  excluded: boolean;
  yaw_deg: number;
  pitch_deg: number;
  // Item 8: present only when diagnostic_mode=true on the backend
  diagnostic?: DiagnosticPayload;
  // Legacy aliases
  face_detected: boolean;
  pose_detected: boolean;
}

export interface SessionSummary {
  session_id: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  total_frames: number;
  valid_frame_count: number;
  excluded_frame_count: number;
  metrics: Record<string, { mean: number; min: number; max: number }>;
  recommendations: string[];
}

export interface UserProfile {
  baseline: Record<string, number>;
  camera_offset_deg: number;
  session_count: number;
}

export type WSMessage =
  | { type: "status";   payload: { session_id: string; started_at: string; state: string } }
  | { type: "analysis"; payload: AnalysisPayload }
  | { type: "summary";  payload: SessionSummary };
