"use client";

import type { SessionSummary } from "@/types";

function scoreColor(v: number) {
  if (v >= 70) return "var(--green)";
  if (v >= 45) return "var(--amber)";
  return "var(--red)";
}

interface Props {
  summary: SessionSummary | null;
  onClose: () => void;
}

const METRIC_LABELS: Record<string, string> = {
  confidence:     "Confidence score",
  eye_contact:    "Eye contact",
  smile:          "Smile frequency",
  posture:        "Posture",
  head_stability: "Head stability",
  body_movement:  "Body movement",
};

export function SessionReport({ summary, onClose }: Props) {
  const dur = summary?.duration_seconds ?? 0;
  const m = Math.floor(dur / 60);
  const s = dur % 60;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--overlay)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 18,
          padding: 32,
          maxWidth: 480,
          width: "90%",
          maxHeight: "80vh",
          overflowY: "auto",
          color: "var(--text)",
        }}
      >
        <h2 style={{ fontSize: 20, marginBottom: 6 }}>Session Report</h2>
        <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 24 }}>
          {summary
            ? `Duration: ${m}m ${s}s · ${summary.total_frames} frames analysed`
            : "No session data yet. Start and complete a session first."}
        </p>

        {summary && (
          <>
            {Object.entries(summary.metrics).map(([key, stat]) => {
              const pct = Math.round(stat.mean * (key === "confidence" ? 1 : 100));
              const label = METRIC_LABELS[key] ?? key;
              return (
                <div
                  key={key}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 0",
                    borderBottom: "1px solid var(--border)",
                    fontSize: 14,
                  }}
                >
                  <span style={{ color: "var(--muted)" }}>{label}</span>
                  <span
                    style={{
                      fontWeight: 600,
                      fontFamily: "'JetBrains Mono', monospace",
                      color: scoreColor(pct),
                    }}
                  >
                    {pct}%
                  </span>
                </div>
              );
            })}

            {summary.recommendations.length > 0 && (
              <div style={{ marginTop: 20 }}>
                <h3 style={{ fontSize: 13, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 10 }}>
                  Recommendations
                </h3>
                {summary.recommendations.map((tip, i) => (
                  <div
                    key={i}
                    style={{
                      fontSize: 13,
                      padding: "8px 12px",
                      borderRadius: 8,
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      marginBottom: 6,
                      lineHeight: 1.5,
                      color: "var(--text)",
                    }}
                  >
                    • {tip}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        <button
          onClick={onClose}
          style={{
            marginTop: 20,
            width: "100%",
            padding: 10,
            background: "var(--accent)",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          Close
        </button>
      </div>
    </div>
  );
}
