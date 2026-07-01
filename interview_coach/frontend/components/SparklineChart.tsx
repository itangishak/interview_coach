"use client";

import { useEffect, useRef } from "react";

interface Props {
  history: number[]; // confidence values 0–100
}

export function SparklineChart({ history }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const w = canvas.offsetWidth || 280;
    const h = 48;
    canvas.width = w;
    canvas.height = h;
    ctx.clearRect(0, 0, w, h);

    if (history.length < 2) return;

    // Read CSS variable for accent colour so it respects theme
    const accent = getComputedStyle(document.documentElement)
      .getPropertyValue("--accent").trim() || "#4f8ef7";

    ctx.beginPath();
    history.forEach((v, i) => {
      const x = (i / (history.length - 1)) * w;
      const y = h - (v / 100) * h;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = accent;
    ctx.lineWidth = 2;
    ctx.stroke();

    // Fill area under line
    const lastX = w;
    const lastY = h - (history[history.length - 1] / 100) * h;
    ctx.lineTo(lastX, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = `${accent}1f`; // ~12% opacity
    ctx.fill();
  }, [history]);

  const avg = history.length
    ? Math.round(history.reduce((a, b) => a + b, 0) / history.length)
    : null;

  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 12,
        padding: 12,
        marginBottom: 20,
      }}
    >
      <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
        <span>Last 60 s</span>
        <span>{avg !== null ? `Avg ${avg}%` : "—"}</span>
      </div>
      <canvas ref={canvasRef} style={{ width: "100%", height: 48, display: "block" }} />
    </div>
  );
}
