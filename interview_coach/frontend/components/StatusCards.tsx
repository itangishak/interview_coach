"use client";

import type { AnalysisPayload } from "@/types";

interface Props {
  analysis: AnalysisPayload | null;
}

export function StatusCards({ analysis }: Props) {
  const headOk = analysis ? analysis.head_stability >= 0.5 : null;
  const faceOk = analysis?.face_detected ?? null;

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

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
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
    </div>
  );
}
