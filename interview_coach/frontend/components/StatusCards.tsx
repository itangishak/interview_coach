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

  const cardStyle: React.CSSProperties = {
    background: "var(--card)",
    border: "1px solid var(--border)",
    borderRadius: 12,
    padding: "12px 14px",
    display: "flex",
    alignItems: "center",
    gap: 10,
  };

  const iconBoxStyle = (ok: boolean | null, okBg: string, badBg: string): React.CSSProperties => ({
    width: 32,
    height: 32,
    borderRadius: 8,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 16,
    flexShrink: 0,
    background: ok === null ? "var(--bg-card, #1a2535)" : ok ? okBg : badBg,
  });

  // Yaw color: green within ±10°, amber ±10–20°, red >20°
  const yawColor =
    yaw === null ? "var(--muted)"
    : Math.abs(yaw) <= 10 ? "var(--green)"
    : Math.abs(yaw) <= 20 ? "var(--amber)"
    : "var(--red)";

  const pitchColor =
    pitch === null ? "var(--muted)"
    : Math.abs(pitch) <= 10 ? "var(--green)"
    : Math.abs(pitch) <= 20 ? "var(--amber)"
    : "var(--red)";

  const labelStyle: React.CSSProperties = { fontSize: 11, color: "var(--muted)" };
  const valueStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: "var(--text)" };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
      {/* Head stability */}
      <div style={cardStyle}>
        <div style={iconBoxStyle(headOk, "var(--green-bg)", "var(--amber-bg)")}>
          {headOk === null ? "🎯" : headOk ? "✅" : "⚠️"}
        </div>
        <div>
          <div style={labelStyle}>Head</div>
          <div style={valueStyle}>
            {headOk === null ? "—" : headOk ? "Stable" : "Moving"}
          </div>
        </div>
      </div>

      {/* Face detection */}
      <div style={cardStyle}>
        <div style={iconBoxStyle(faceOk, "var(--green-bg)", "var(--red-bg)")}>
          {faceOk === null ? "📷" : faceOk ? "✅" : "❌"}
        </div>
        <div>
          <div style={labelStyle}>Detection</div>
          <div style={valueStyle}>
            {faceOk === null ? "—" : faceOk ? "Face found" : "No face"}
          </div>
        </div>
      </div>

      {/* Head yaw */}
      <div style={cardStyle}>
        <div style={{ width: 32, height: 32, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0, background: "var(--bg-card, #1a2535)" }}>
          ↔️
        </div>
        <div>
          <div style={labelStyle}>Yaw</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: yawColor }}>
            {yaw === null ? "—" : `${yaw > 0 ? "+" : ""}${yaw.toFixed(1)}°`}
          </div>
        </div>
      </div>

      {/* Head pitch */}
      <div style={cardStyle}>
        <div style={{ width: 32, height: 32, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0, background: "var(--bg-card, #1a2535)" }}>
          ↕️
        </div>
        <div>
          <div style={labelStyle}>Pitch</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: pitchColor }}>
            {pitch === null ? "—" : `${pitch > 0 ? "+" : ""}${pitch.toFixed(1)}°`}
          </div>
        </div>
      </div>
    </div>
  );
}
