"use client";

import { useEffect, useRef, useState } from "react";
import { ConfidenceRing } from "@/components/ConfidenceRing";
import { FeedbackPanel } from "@/components/FeedbackPanel";
import { MetricsPanel } from "@/components/MetricsPanel";
import { SessionReport } from "@/components/SessionReport";
import { SparklineChart } from "@/components/SparklineChart";
import { StatusCards } from "@/components/StatusCards";
import { useInterviewSession } from "@/hooks/useInterviewSession";

const MAX_HIST = 120; // 2 min at 1 sample/s

export default function HomePage() {
  const { connected, active, analysis, summary, startSession, stopSession } =
    useInterviewSession();

  const [showReport, setShowReport] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [confHistory, setConfHistory] = useState<number[]>([]);

  // Live webcam preview
  const videoPreviewRef = useRef<HTMLVideoElement>(null);

  // Timer
  useEffect(() => {
    if (!active) return;
    setElapsed(0);
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, [active]);

  // Build sparkline history
  useEffect(() => {
    if (!analysis) return;
    setConfHistory((prev) => {
      const next = [...prev, analysis.confidence];
      return next.length > MAX_HIST ? next.slice(-MAX_HIST) : next;
    });
  }, [analysis]);

  // Show report automatically when session ends with a summary
  useEffect(() => {
    if (summary) setShowReport(true);
  }, [summary]);

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

  return (
    <div style={{ display: "grid", gridTemplateRows: "56px 1fr", height: "100vh", overflow: "hidden" }}>

      {/* ── Header ── */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 28px",
          borderBottom: "1px solid #252b3d",
          background: "#111420",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 600, fontSize: 15 }}>
          <div
            className="animate-pulse-dot"
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: connected ? "#4f8ef7" : "#6b7491",
              boxShadow: connected ? "0 0 8px #4f8ef7" : "none",
            }}
          />
          Interview Coach
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: "#6b7491" }}>
            {mm}:{ss}
          </span>
          <button
            onClick={() => setShowReport(true)}
            style={{
              padding: "7px 18px",
              borderRadius: 8,
              border: "1px solid #252b3d",
              background: "#181d2e",
              color: "#e8ecf4",
              fontSize: 13,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            📋 Session Report
          </button>
          <button
            onClick={active ? stopSession : startSession}
            disabled={!connected}
            style={{
              padding: "7px 18px",
              borderRadius: 8,
              border: "none",
              background: active ? "#ef4444" : "#4f8ef7",
              color: "#fff",
              fontSize: 13,
              fontWeight: 500,
              cursor: connected ? "pointer" : "not-allowed",
              opacity: connected ? 1 : 0.5,
              transition: "background .2s",
            }}
          >
            {active ? "Stop Session" : "Start Session"}
          </button>
        </div>
      </header>

      {/* ── Main ── */}
      <main style={{ display: "grid", gridTemplateColumns: "1fr 340px", height: "calc(100vh - 56px)", overflow: "hidden" }}>

        {/* Video panel */}
        <div style={{ position: "relative", background: "#000", display: "flex", alignItems: "center", justifyContent: "center" }}>
          {!active ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, color: "#6b7491", fontSize: 14 }}>
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: .3 }}>
                <path d="M15 10l4.553-2.276A1 1 0 0121 8.723v6.554a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" />
              </svg>
              Press <strong style={{ color: "#e8ecf4" }}>Start Session</strong> to begin
            </div>
          ) : (
            <video
              ref={videoPreviewRef}
              autoPlay
              playsInline
              muted
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          )}

          {/* Confidence badge */}
          {active && analysis && (
            <ConfidenceRing value={analysis.confidence} />
          )}

          {/* Status pills */}
          {active && analysis && (
            <div style={{ position: "absolute", bottom: 20, left: 20, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[
                { ok: analysis.face_detected, good: "Face detected", bad: "No face" },
                { ok: analysis.eye_contact >= 0.6, good: "Good eye contact", bad: "Look at camera" },
                { ok: analysis.body_movement >= 0.6, good: "Calm", bad: "Too much movement" },
              ].map(({ ok, good, bad }, i) => (
                <div
                  key={i}
                  style={{
                    padding: "5px 12px",
                    borderRadius: 20,
                    fontSize: 11,
                    fontWeight: 500,
                    background: "rgba(10,12,16,.75)",
                    backdropFilter: "blur(8px)",
                    border: `1px solid ${ok ? "#22c55e55" : "#ef444455"}`,
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                  }}
                >
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: ok ? "#22c55e" : "#ef4444" }} />
                  {ok ? good : bad}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Side panel */}
        <div
          style={{
            background: "#111420",
            borderLeft: "1px solid #252b3d",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
          }}
        >
          {/* Live metrics */}
          <div style={{ padding: "20px 20px 0" }}>
            <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".1em", color: "#6b7491", marginBottom: 14 }}>
              Live metrics
            </div>
            <MetricsPanel analysis={analysis} />
          </div>

          <div style={{ height: 1, background: "#252b3d", margin: "0 20px" }} />

          {/* Status */}
          <div style={{ padding: "16px 20px 0" }}>
            <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".1em", color: "#6b7491", marginBottom: 14 }}>
              Status
            </div>
            <StatusCards analysis={analysis} />
          </div>

          <div style={{ height: 1, background: "#252b3d", margin: "0 20px" }} />

          {/* Sparkline */}
          <div style={{ padding: "16px 20px 0" }}>
            <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".1em", color: "#6b7491", marginBottom: 14 }}>
              Confidence history
            </div>
            <SparklineChart history={confHistory} />
          </div>

          <div style={{ height: 1, background: "#252b3d", margin: "0 20px" }} />

          {/* Feedback */}
          <div style={{ padding: "16px 20px 20px" }}>
            <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".1em", color: "#6b7491", marginBottom: 14 }}>
              AI feedback
            </div>
            <FeedbackPanel analysis={analysis} />
          </div>
        </div>
      </main>

      {/* Report modal */}
      {showReport && (
        <SessionReport summary={summary} onClose={() => setShowReport(false)} />
      )}
    </div>
  );
}
