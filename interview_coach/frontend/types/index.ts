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

export interface AnalysisPayload {
  eye_contact: number;        // 0–1
  smile: number;              // 0–1
  posture: number;            // 0–1
  head_stability: number;     // 0–1
  body_movement: number;      // 0–1 (higher = less movement = better)
  confidence: number;         // 0–100
  feedback: FeedbackPayload;
  face_visible: boolean;      // preferred name
  pose_visible: boolean;
  excluded: boolean;          // frame was gated (not in session aggregates)
  yaw_deg: number;            // corrected head yaw  (camera offset subtracted)
  pitch_deg: number;          // corrected head pitch
  // Legacy aliases kept for backward compat
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
