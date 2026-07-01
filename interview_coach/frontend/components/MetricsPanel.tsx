"use client";

import type { AnalysisPayload } from "@/types";

function scoreColor(v: number) {
  if (v >= 70) return "var(--green)";
  if (v >= 45) return "var(--amber)";
  return "var(--red)";
}

function cardBorder(v: number) {
  if (v >= 70) return "rgba(34,197,94,.27)";
  if (v >= 45) return "rgba(245,158,11,.27)";
  return "rgba(239,68,68,.27)";
}

interface MetricCardProps {
  name: string;
  icon: string;
  value: number | null;      // null = no signal
  barColor?: string;
  subText: string;
  dimmed?: boolean;          // true during calibration
}

function MetricCard({ name, icon, value, barColor, subText, dimmed }: MetricCardProps) {
  const noSignal = value === null;
  const pct = noSignal ? 0 : Math.round(value * 100);
  const borderColor = noSignal || dimmed ? "var(--border)" : cardBorder(pct);

  return (
    <div
      style={{
        background: "var(--card)",
        border: `1px solid ${borderColor}`,
        borderRadius: 12,
        padding: 14,
        transition: "border-color .3s, opacity .3s",
        opacity: dimmed ? 0.55 : 1,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".07em" }}>
          {name}
        </span>
        <span style={{ fontSize: 14 }}>{icon}</span>
      </div>

      {/* Value — "—" when no signal, "…" when calibrating */}
      <div
        style={{
          fontSize: 24,
          fontWeight: 700,
          fontFamily: "'JetBrains Mono', monospace",
          lineHeight: 1,
          color: noSignal || dimmed ? "var(--muted)" : "var(--text)",
        }}
      >
        {noSignal ? "—" : dimmed ? "…" : `${pct}%`}
      </div>

      {/* Progress bar */}
      <div style={{ height: 3, background: "var(--border)", borderRadius: 2, marginTop: 8, overflow: "hidden" }}>
        {!noSignal && !dimmed && (
          <div
            style={{
              height: "100%",
              borderRadius: 2,
              width: `${pct}%`,
              background: barColor ?? scoreColor(pct),
              transition: "width .5s ease",
            }}
          />
        )}
      </div>

      <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 4 }}>{subText}</div>
    </div>
  );
}

interface Props {
  analysis: AnalysisPayload | null;
}

export function MetricsPanel({ analysis }: Props) {
  // face_valid: false means face is absent → show "—"
  // calibrating: true means baseline collection → dim cards
  const faceValid = analysis?.face_valid ?? false;
  const poseValid = analysis?.pose_valid ?? false;
  const calibrating = analysis?.calibrating ?? false;

  // Only show numeric value when signal is present
  const ec = faceValid ? (analysis?.eye_contact ?? null) : null;
  const sm = faceValid ? (analysis?.smile ?? null) : null;
  const ps = poseValid ? (analysis?.posture ?? null) : null;
  const mv = poseValid ? (analysis?.body_movement ?? null) : null;

  const ecPct = ec !== null ? Math.round(ec * 100) : 0;
  const smPct = sm !== null ? Math.round(sm * 100) : 0;
  const psPct = ps !== null ? Math.round(ps * 100) : 0;
  const mvPct = mv !== null ? Math.round(mv * 100) : 0;

  const ecSub = !analysis
    ? "Waiting…"
    : !faceValid
    ? "No face detected"
    : calibrating
    ? "Calibrating…"
    : ecPct >= 70 ? "Focused" : ecPct >= 45 ? "Drifting" : "Look at camera";

  const smSub = !analysis
    ? "Waiting…"
    : !faceValid
    ? "No face detected"
    : calibrating
    ? "Calibrating…"
    : smPct >= 50 ? "Warm & approachable" : smPct >= 25 ? "Slight" : "Try to smile more";

  const psSub = !analysis
    ? "Waiting…"
    : !poseValid
    ? "No pose detected"
    : calibrating
    ? "Calibrating…"
    : psPct >= 70 ? "Upright" : psPct >= 40 ? "Slightly slouched" : "Sit up straight";

  const mvSub = !analysis
    ? "Waiting…"
    : !poseValid
    ? "No pose detected"
    : calibrating
    ? "Calibrating…"
    : mvPct >= 70 ? "Calm & composed" : mvPct >= 45 ? "Slightly restless" : "Too much movement";

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
      <MetricCard name="Eye contact" icon="👁"  value={ec} barColor="var(--accent)"  subText={ecSub} dimmed={calibrating && faceValid} />
      <MetricCard name="Smile"       icon="😊"  value={sm} barColor="var(--green)"   subText={smSub} dimmed={calibrating && faceValid} />
      <MetricCard name="Posture"     icon="🪑"  value={ps} barColor="var(--accent2)" subText={psSub} dimmed={calibrating && poseValid} />
      <MetricCard name="Movement"    icon="🏃"  value={mv}
        barColor={mv === null ? "var(--muted)" : mvPct >= 70 ? "var(--green)" : mvPct >= 45 ? "var(--amber)" : "var(--red)"}
        subText={mvSub}
        dimmed={calibrating && poseValid}
      />
    </div>
  );
}
