"use client";

import type { AnalysisPayload } from "@/types";

interface Props {
  analysis: AnalysisPayload | null;
}

export function StatusCards({ analysis }: Props) {
  const headOk = analysis ? analysis.head_stability >= 0.5 : null;
  // Prefer face_visible; fall back to legacy face_detected
  const faceOk = analysis ? (analysis.face_visible ?? analysis.face_detected ?? null) : null;
  const yaw    = analysis?.yaw_deg   ?? null;
  const pitch  = analysis?.pitch_deg ?? null;

  const cardStyle = {
    background: "#181d2e",
    border: "1px solid #252b3d",
    borderRadius: 12,
    padding: "12px 14px",
    display: "flex",
    alignItems: "center",
    gap: 10,
  } as const;

  const iconBox = (ok: boolean | null, trueIcon: string, falseIcon: string) => ({
    width: 32,
    height: 32,
    borderRadius: 8,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 16,
    flexShrink: 0,
    background: ok === null ? "#1a2535" : ok ? "#0f2a1e" : "#2a1a0f",
  } as const);

  // Yaw color: green within ±10°, amber ±10–20°, red >20°
  const yawColor =
    yaw === null ? "#6b7491"
    : Math.abs(yaw) <= 10 ? "#22c55e"
    : Math.abs(yaw) <= 20 ? "#f59e0b"
    : "#ef4444";

  const pitchColor =
    pitch === null ? "#6b7491"
    : Math.abs(pitch) <= 10 ? "#22c55e"
    : Math.abs(pitch) <= 20 ? "#f59e0b"
    : "#ef4444";

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
      {/* Head stability */}
      <div style={cardStyle}>
        <div style={iconBox(headOk, "✅", "⚠️")}>
          {headOk === null ? "🎯" : headOk ? "✅" : "⚠️"}
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#6b7491" }}>Head</div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {headOk === null ? "—" : headOk ? "Stable" : "Moving"}
          </div>
        </div>
      </div>

      {/* Face detection */}
      <div style={cardStyle}>
        <div style={iconBox(faceOk, "✅", "❌")}>
          {faceOk === null ? "📷" : faceOk ? "✅" : "❌"}
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#6b7491" }}>Detection</div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {faceOk === null ? "—" : faceOk ? "Face found" : "No face"}
          </div>
        </div>
      </div>

      {/* Head yaw (3-D, camera-offset corrected) */}
      <div style={cardStyle}>
        <div style={{
          width: 32, height: 32, borderRadius: 8, display: "flex",
          alignItems: "center", justifyContent: "center", fontSize: 16,
          flexShrink: 0, background: "#1a2535",
        }}>
          ↔️
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#6b7491" }}>Yaw</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: yawColor }}>
            {yaw === null ? "—" : `${yaw > 0 ? "+" : ""}${yaw.toFixed(1)}°`}
          </div>
        </div>
      </div>

      {/* Head pitch (camera-offset corrected) */}
      <div style={cardStyle}>
        <div style={{
          width: 32, height: 32, borderRadius: 8, display: "flex",
          alignItems: "center", justifyContent: "center", fontSize: 16,
          flexShrink: 0, background: "#1a2535",
        }}>
          ↕️
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#6b7491" }}>Pitch</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: pitchColor }}>
            {pitch === null ? "—" : `${pitch > 0 ? "+" : ""}${pitch.toFixed(1)}°`}
          </div>
        </div>
      </div>
    </div>
  );
}
