"use client";

import type { AnalysisPayload } from "@/types";

const ICONS = ["👁", "😊", "🎯", "🏃", "🪑", "⭐"];

interface Props {
  analysis: AnalysisPayload | null;
}

export function FeedbackPanel({ analysis }: Props) {
  const recommendations = analysis?.feedback?.recommendations ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
      {recommendations.length === 0 ? (
        <div
          style={{
            background: "#181d2e",
            border: "1px solid #252b3d",
            borderRadius: 10,
            padding: "10px 12px",
            fontSize: 12,
            lineHeight: 1.5,
            display: "flex",
            gap: 8,
            alignItems: "flex-start",
          }}
        >
          <span>💡</span>
          <span>{analysis ? "Detecting…" : "Start your session to receive real-time coaching feedback."}</span>
        </div>
      ) : (
        recommendations.map((tip, i) => (
          <div
            key={i}
            style={{
              background: "#181d2e",
              border: "1px solid #252b3d",
              borderRadius: 10,
              padding: "10px 12px",
              fontSize: 12,
              lineHeight: 1.5,
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
            }}
          >
            <span style={{ flexShrink: 0, marginTop: 1 }}>{ICONS[i] ?? "💡"}</span>
            <span>{tip}</span>
          </div>
        ))
      )}
    </div>
  );
}
