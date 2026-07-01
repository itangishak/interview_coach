"use client";

import { useEffect, useRef, useState } from "react";
import { ConfidenceRing } from "@/components/ConfidenceRing";
import { DiagnosticOverlay } from "@/components/DiagnosticOverlay";
import { DiagnosticPanel } from "@/components/DiagnosticPanel";
import { FeedbackPanel } from "@/components/FeedbackPanel";
import { MetricsPanel } from "@/components/MetricsPanel";
import { SparklineChart } from "@/components/SparklineChart";
import { StatusCards } from "@/components/StatusCards";
import { useInterviewSession } from "@/hooks/useInterviewSession";

const MAX_HIST = 120; // 2 min at 1 sample/s

type OverlayKey = "facialMidline" | "eyeLine" | "poseMidline" | "pnpPoints" | "irisPoints" | "poseAxes";
const DEFAULT_OVERLAYS: Record<OverlayKey, boolean> = {
  facialMidline: true,
  eyeLine:       true,
  poseMidline:   true,
  pnpPoints:     true,
  irisPoints:    true,
  poseAxes:      true,
};

// ── Theme helpers ─────────────────────────────────────────────────────────────
function readStoredTheme(): "dark" | "light" {
  try {
    return (localStorage.getItem("theme") as "dark" | "light") ?? "dark";
  } catch {
    return "dark";
  }
}

function applyTheme(theme: "dark" | "light") {
  if (theme === "light") {
    document.documentElement.setAttribute("data-theme", "light");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  try { localStorage.setItem("theme", theme); } catch { /* ssr */ }
}

export default function HomePage() {
  const [diagnosticMode, setDiagnosticMode] = useState(false);
  const [overlays, setOverlays] = useState<Record<OverlayKey, boolean>>(DEFAULT_OVERLAYS);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  const { connected, active, analysis, startSession, stopSession } =
    useInterviewSession();

  const [elapsed, setElapsed] = useState(0);
  const [confHistory, setConfHistory] = useState<number[]>([]);

  // Live webcam preview
  const videoPreviewRef = useRef<HTMLVideoElement>(null);
  const [videoDims, setVideoDims] = useState({ w: 640, h: 480 });

  // ── Theme init (reads localStorage on mount; respects prefers-color-scheme) ──
  useEffect(() => {
    let stored: "dark" | "light" | null = null;
    try { stored = localStorage.getItem("theme") as "dark" | "light" | null; } catch { /* ssr */ }
    const preferred = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    const initial = stored ?? preferred;
    setTheme(initial);
    applyTheme(initial);
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      applyTheme(next);
      return next;
    });
  };

  // Timer
  useEffect(() => {
    if (!active) return;
    setElapsed(0);
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, [active]);

  // Build sparkline history (only when face is valid — not frozen EMA)
  useEffect(() => {
    if (!analysis) return;
    if (!analysis.face_valid) return; // skip excluded frames in sparkline
    setConfHistory((prev) => {
      const next = [...prev, analysis.confidence];
      return next.length > MAX_HIST ? next.slice(-MAX_HIST) : next;
    });
  }, [analysis]);

  // Mirror webcam into the preview <video>
  useEffect(() => {
    if (!active) return;
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: false })
      .then((stream) => {
        if (videoPreviewRef.current) {
          videoPreviewRef.current.srcObject = stream;
        }
      })
      .catch(() => {});
  }, [active]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  const toggleOverlay = (key: OverlayKey) => {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleStart = () => {
    startSession({ diagnosticMode });
  };

  const btnBase: React.CSSProperties = {
    padding: "7px 18px",
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "var(--card)",
    color: "var(--text)",
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
  };

  return (
    <div style={{ display: "grid", gridTemplateRows: "56px 1fr", height: "100vh", overflow: "hidden", background: "var(--bg)", color: "var(--text)" }}>

      {/* ── Header ── */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 28px",
          borderBottom: "1px solid var(--border)",
          background: "var(--surface)",
        }}
      >
        {/* Left: logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 600, fontSize: 15 }}>
          <div
            className="animate-pulse-dot"
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: connected ? "var(--accent)" : "var(--muted)",
              boxShadow: connected ? "0 0 8px var(--accent)" : "none",
            }}
          />
          Interview Coach
        </div>

        {/* Right: controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: "var(--muted)" }}>
            {mm}:{ss}
          </span>

          {/* Theme toggle */}
          <button onClick={toggleTheme} title="Toggle theme" style={btnBase}>
            {theme === "dark" ? "☀️" : "🌙"}
          </button>

          {/* Diagnostic mode toggle */}
          <button
            onClick={() => setDiagnosticMode((v) => !v)}
            title="Toggle diagnostic mode"
            style={{
              ...btnBase,
              background: diagnosticMode ? "var(--accent)" : "var(--card)",
              color: diagnosticMode ? "#fff" : "var(--text)",
              border: diagnosticMode ? "1px solid var(--accent)" : "1px solid var(--border)",
            }}
          >
            🔬 Diagnostic
          </button>

          {/* Start / Stop */}
          <button
            onClick={active ? stopSession : handleStart}
            disabled={!connected}
            style={{
              padding: "7px 18px",
              borderRadius: 8,
              border: "none",
              background: active ? "var(--red)" : "var(--accent)",
              color: "#fff",
              fontSize: 13,
              fontWeight: 500,
              cursor: connected ? "pointer" : "not-allowed",
              opacity: connected ? 1 : 0.5,
              transition: "background .2s",
            }}
          >
            {active ? "Stop" : "Start Session"}
          </button>
        </div>
      </header>

      {/* ── Main ── */}
      <main style={{ display: "grid", gridTemplateColumns: diagnosticMode ? "1fr 340px 280px" : "1fr 340px", height: "calc(100vh - 56px)", overflow: "hidden" }}>

        {/* Video panel */}
        <div style={{ position: "relative", background: "#000", display: "flex", alignItems: "center", justifyContent: "center" }}>
          {!active ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, color: "var(--muted)", fontSize: 14 }}>
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: .3 }}>
                <path d="M15 10l4.553-2.276A1 1 0 0121 8.723v6.554a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              </svg>
              Press <strong style={{ color: "var(--text)" }}>Start Session</strong> to begin
            </div>
          ) : (
            <video
              ref={videoPreviewRef}
              autoPlay
              playsInline
              muted
              onLoadedMetadata={(e) => {
                const v = e.currentTarget;
                setVideoDims({ w: v.videoWidth, h: v.videoHeight });
              }}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          )}

          {/* Diagnostic overlay canvas */}
          {active && diagnosticMode && (
            <DiagnosticOverlay
              data={analysis?.diagnostic ?? null}
              overlays={overlays}
              videoWidth={videoDims.w}
              videoHeight={videoDims.h}
            />
          )}

          {/* Confidence badge */}
          {active && analysis && (
            <ConfidenceRing
              value={analysis.confidence}
              faceValid={analysis.face_valid}
              calibrating={analysis.calibrating}
            />
          )}

          {/* Status pills */}
          {active && analysis && (
            <div style={{ position: "absolute", bottom: 20, left: 20, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[
                { ok: analysis.face_detected, good: "Face detected", bad: "No face" },
                { ok: analysis.face_valid && analysis.eye_contact >= 0.6, good: "Good eye contact", bad: "Look at camera" },
                { ok: analysis.pose_valid && analysis.body_movement >= 0.6, good: "Calm", bad: "Too much movement" },
              ].map(({ ok, good, bad }, i) => (
                <div
                  key={i}
                  style={{
                    padding: "5px 12px",
                    borderRadius: 20,
                    fontSize: 11,
                    fontWeight: 500,
                    background: "var(--blur-bg)",
                    backdropFilter: "blur(8px)",
                    border: `1px solid ${ok ? "rgba(34,197,94,.35)" : "rgba(239,68,68,.35)"}`,
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                    color: "var(--text)",
                  }}
                >
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: ok ? "var(--green)" : "var(--red)" }} />
                  {ok ? good : bad}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Side panel */}
        <div
          style={{
            background: "var(--surface)",
            borderLeft: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
          }}
        >
          {/* Live metrics */}
          <div style={{ padding: "20px 20px 0" }}>
            <SectionLabel>Live metrics</SectionLabel>
            <MetricsPanel analysis={analysis} />
          </div>

          <Divider />

          {/* Status */}
          <div style={{ padding: "16px 20px 0" }}>
            <SectionLabel>Status</SectionLabel>
            <StatusCards analysis={analysis} />
          </div>

          <Divider />

          {/* Sparkline */}
          <div style={{ padding: "16px 20px 0" }}>
            <SectionLabel>Confidence history</SectionLabel>
            <SparklineChart history={confHistory} />
          </div>

          <Divider />

          {/* Feedback */}
          <div style={{ padding: "16px 20px 20px" }}>
            <SectionLabel>AI feedback</SectionLabel>
            <FeedbackPanel analysis={analysis} />
          </div>
        </div>

        {/* Diagnostic side panel (only when diagnosticMode=true) */}
        {diagnosticMode && (
          <div
            style={{
              background: "var(--surface)",
              borderLeft: "1px solid var(--border)",
              overflowY: "auto",
              padding: "16px 14px",
            }}
          >
            <SectionLabel>Diagnostic</SectionLabel>
            <DiagnosticPanel
              data={analysis?.diagnostic ?? null}
              overlays={overlays}
              onToggleOverlay={(key) => toggleOverlay(key as OverlayKey)}
            />
          </div>
        )}
      </main>

    </div>
  );
}

// ── Small layout helpers ──────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".1em", color: "var(--muted)", marginBottom: 14 }}>
      {children}
    </div>
  );
}

function Divider() {
  return <div style={{ height: 1, background: "var(--border)", margin: "0 20px" }} />;
}
