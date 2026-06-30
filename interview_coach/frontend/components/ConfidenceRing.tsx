"use client";

const RADIUS = 26;
const CIRC = 2 * Math.PI * RADIUS; // ≈163

function scoreColor(v: number) {
  if (v >= 70) return "#22c55e";
  if (v >= 45) return "#f59e0b";
  return "#ef4444";
}

function gradeLabel(v: number) {
  if (v >= 85) return "Excellent";
  if (v >= 70) return "Good";
  if (v >= 50) return "Fair";
  return "Needs work";
}

interface Props {
  value: number; // 0–100
}

export function ConfidenceRing({ value }: Props) {
  const pct = Math.min(100, Math.max(0, value));
  const offset = CIRC * (1 - pct / 100);
  const color = scoreColor(pct);

  return (
    <div
      style={{
        position: "absolute",
        top: 20,
        left: 20,
        background: "rgba(10,12,16,.75)",
        backdropFilter: "blur(8px)",
        border: "1px solid #252b3d",
        borderRadius: 14,
        padding: "14px 18px",
        display: "flex",
        alignItems: "center",
        gap: 14,
      }}
    >
      {/* SVG ring */}
      <div style={{ position: "relative", width: 64, height: 64 }}>
        <svg width="64" height="64" viewBox="0 0 64 64" style={{ transform: "rotate(-90deg)" }}>
          <circle
            cx="32" cy="32" r={RADIUS}
            fill="none" stroke="#252b3d" strokeWidth="5"
          />
          <circle
            cx="32" cy="32" r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={CIRC}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset .6s ease, stroke .4s" }}
          />
        </svg>
        {/* Centre label */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 17, fontWeight: 700, lineHeight: 1 }}>
            {Math.round(pct)}
          </span>
          <span style={{ fontSize: 9, color: "#6b7491", marginTop: 1 }}>%</span>
        </div>
      </div>

      {/* Text */}
      <div>
        <div style={{ fontSize: 11, color: "#6b7491", textTransform: "uppercase", letterSpacing: ".08em" }}>
          Confidence
        </div>
        <div style={{ fontSize: 22, fontWeight: 700, marginTop: 2, color, transition: "color .4s" }}>
          {gradeLabel(pct)}
        </div>
      </div>
    </div>
  );
}
