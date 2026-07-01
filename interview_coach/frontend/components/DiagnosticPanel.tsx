"use client";

import type { DiagnosticPayload } from "@/types";

interface OverlayToggles {
  facialMidline: boolean;
  eyeLine: boolean;
  poseMidline: boolean;
  pnpPoints: boolean;
  irisPoints: boolean;
  poseAxes: boolean;
}

interface Props {
  data: DiagnosticPayload | null;
  overlays: OverlayToggles;
  onToggleOverlay: (key: keyof OverlayToggles) => void;
}

const OVERLAY_LABELS: Record<keyof OverlayToggles, string> = {
  facialMidline: "Facial midline",
  eyeLine:       "Eye line",
  poseMidline:   "Pose midline",
  pnpPoints:     "PnP points",
  irisPoints:    "Iris points",
  poseAxes:      "Pose axes",
};

function Row({ label, value }: { label: string; value: string | number | boolean | null }) {
  let display: string;
  if (value === null || value === undefined) display = "—";
  else if (typeof value === "boolean") display = value ? "true" : "false";
  else if (typeof value === "number") display = isFinite(value) ? value.toString() : "—";
  else display = String(value);

  const color =
    typeof value === "boolean"
      ? value ? "var(--green)" : "var(--red)"
      : "var(--text)";

  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid var(--border)", fontSize: 11 }}>
      <span style={{ color: "var(--muted)" }}>{label}</span>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", color }}>{display}</span>
    </div>
  );
}

export function DiagnosticPanel({ data, overlays, onToggleOverlay }: Props) {
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 12,
        padding: "12px 14px",
        marginBottom: 16,
        fontSize: 11,
      }}
    >
      {/* Overlay toggles */}
      <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".08em", color: "var(--muted)", marginBottom: 8 }}>
        Overlays
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 8px", marginBottom: 12 }}>
        {(Object.keys(OVERLAY_LABELS) as (keyof OverlayToggles)[]).map((key) => (
          <label
            key={key}
            style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer", color: "var(--text)", fontSize: 11 }}
          >
            <input
              type="checkbox"
              checked={overlays[key]}
              onChange={() => onToggleOverlay(key)}
              style={{ accentColor: "var(--accent)", cursor: "pointer" }}
            />
            {OVERLAY_LABELS[key]}
          </label>
        ))}
      </div>

      {/* Raw readouts */}
      <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".08em", color: "var(--muted)", marginBottom: 6 }}>
        Raw values
      </div>

      {!data ? (
        <div style={{ color: "var(--muted)", fontSize: 11, padding: "4px 0" }}>No diagnostic data — start session with Diagnostic mode enabled.</div>
      ) : (
        <>
          <Row label="face_visible"      value={data.face_visible} />
          <Row label="pose_visible"      value={data.pose_visible} />
          <Row label="excluded"          value={data.excluded} />
          <Row label="calibrated"        value={data.calibrated} />
          <Row label="gaze_calibrating"  value={data.gaze_calibrating} />
          <Row label="yaw_deg"           value={`${data.yaw_deg.toFixed(2)}°`} />
          <Row label="pitch_deg"         value={`${data.pitch_deg.toFixed(2)}°`} />
          <Row label="roll_deg"          value={`${data.roll_deg.toFixed(2)}°`} />
          <Row label="ICD (norm)"        value={data.icd.toFixed(4)} />
          <Row label="shoulder_w (norm)" value={data.shoulder_width.toFixed(4)} />

          <div style={{ height: 6 }} />
          <Row label="raw_eye_contact"   value={data.raw_eye_contact?.toFixed(3) ?? "—"} />
          <Row label="ema_eye_contact"   value={data.ema_eye_contact.toFixed(3)} />
          <Row label="gaze_ref_offset"   value={data.gaze_reference_offset.toFixed(4)} />

          <div style={{ height: 6 }} />
          <Row label="raw_smile"         value={data.raw_smile?.toFixed(3) ?? "—"} />
          <Row label="ema_smile"         value={data.ema_smile.toFixed(3)} />

          <div style={{ height: 6 }} />
          <Row label="raw_posture"       value={data.raw_posture?.toFixed(3) ?? "—"} />
          <Row label="ema_posture"       value={data.ema_posture.toFixed(3)} />

          <div style={{ height: 6 }} />
          <Row label="raw_head_stab"     value={data.raw_head_stability?.toFixed(3) ?? "—"} />
          <Row label="ema_head_stab"     value={data.ema_head_stability.toFixed(3)} />
          <Row label="stability_coeff"   value={data.stability_coeff.toFixed(4)} />

          <div style={{ height: 6 }} />
          <Row label="raw_body_move"     value={data.raw_body_movement?.toFixed(3) ?? "—"} />
          <Row label="ema_body_move"     value={data.ema_body_movement.toFixed(3)} />
          <Row label="movement_floor"    value={data.movement_floor.toFixed(5)} />
          <Row label="movement_ceil"     value={data.movement_ceil.toFixed(4)} />

          <div style={{ height: 6 }} />
          <Row label="frame_count"       value={data.frame_count} />

          {Object.keys(data.baseline).length > 0 && (
            <>
              <div style={{ height: 6 }} />
              <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".08em", color: "var(--muted)", padding: "3px 0" }}>
                Baseline
              </div>
              {Object.entries(data.baseline).map(([k, v]) => (
                <Row key={k} label={k} value={v.toFixed(3)} />
              ))}
            </>
          )}
        </>
      )}
    </div>
  );
}
