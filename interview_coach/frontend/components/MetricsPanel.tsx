"use client";

import type { AnalysisPayload } from "@/types";

function scoreColor(v: number) {
  if (v >= 70) return "#22c55e";
  if (v >= 45) return "#f59e0b";
  return "#ef4444";
}

function cardBorder(v: number) {
  if (v >= 70) return "rgba(34,197,94,.27)";
  if (v >= 45) return "rgba(245,158,11,.27)";
  return "rgba(239,68,68,.27)";
}

interface MetricCardProps {
  name: string;
  icon: string;
  value: number;      // 0–1
  barColor?: string;
  subText: string;
}

function MetricCard({ name, icon, value, barColor, subText }: MetricCardProps) {
  const pct = Math.round(value * 100);
  return (
    <div
      style={{
        background: "#181d2e",
        border: `1px solid ${cardBorder(pct)}`,
        borderRadius: 12,
        padding: 14,
        transition: "border-color .3s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontSize: 10, color: "#6b7491", textTransform: "uppercase", letterSpacing: ".07em" }}>
          {name}
        </span>
        <span style={{ fontSize: 14 }}>{icon}</span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>
        {pct}%
      </div>
      <div style={{ height: 3, background: "#252b3d", borderRadius: 2, marginTop: 8, overflow: "hidden" }}>
        <div
          style={{
            height: "100%",
            borderRadius: 2,
            width: `${pct}%`,
            background: barColor ?? scoreColor(pct),
            transition: "width .5s ease",
          }}
        />
      </div>
      <div style={{ fontSize: 10, color: "#6b7491", marginTop: 4 }}>{subText}</div>
    </div>
  );
}

interface Props {
  analysis: AnalysisPayload | null;
}

export function MetricsPanel({ analysis }: Props) {
  const ec    = analysis?.eye_contact ?? 0;
  const sm    = analysis?.smile ?? 0;
  const ps    = analysis?.posture ?? 0;
  const mv    = analysis?.body_movement ?? 0;

  const ecSub = ec >= 0.7 ? "Focused" : ec >= 0.45 ? "Drifting" : "Look at camera";
  const smSub = sm >= 0.5 ? "Warm & approachable" : sm >= 0.25 ? "Slight" : "Try to smile more";
  const psSub = ps >= 0.7 ? "Upright" : ps >= 0.4 ? "Slightly slouched" : "Sit up straight";
  const mvSub = mv >= 0.7 ? "Calm & composed" : mv >= 0.45 ? "Slightly restless" : "Too much movement";

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
      <MetricCard name="Eye contact" icon="👁"  value={ec} barColor="#4f8ef7" subText={analysis ? ecSub : "Waiting…"} />
      <MetricCard name="Smile"       icon="😊"  value={sm} barColor="#22c55e" subText={analysis ? smSub : "Waiting…"} />
      <MetricCard name="Posture"     icon="🪑"  value={ps} barColor="#7c5cfc" subText={analysis ? psSub : "Waiting…"} />
      <MetricCard name="Movement"    icon="🏃"  value={mv} barColor={mv >= 0.7 ? "#22c55e" : mv >= 0.45 ? "#f59e0b" : "#ef4444"} subText={analysis ? mvSub : "Waiting…"} />
    </div>
  );
}
