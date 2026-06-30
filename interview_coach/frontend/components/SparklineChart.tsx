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

    ctx.beginPath();
    history.forEach((v, i) => {
      const x = (i / (history.length - 1)) * w;
      const y = h - (v / 100) * h;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#4f8ef7";
    ctx.lineWidth = 2;
    ctx.stroke();

    // fill area under line
    const lastX = w;
    const lastY = h - (history[history.length - 1] / 100) * h;
    ctx.lineTo(lastX, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = "rgba(79,142,247,.12)";
    ctx.fill();
  }, [history]);

  const avg = history.length
    ? Math.round(history.reduce((a, b) => a + b, 0) / history.length)
    : null;

  return (
    <div
      style={{
        background: "#181d2e",
        border: "1px solid #252b3d",
        borderRadius: 12,
        padding: 12,
        marginBottom: 20,
      }}
    >
      <div style={{ fontSize: 10, color: "#6b7491", marginBottom: 6, display: "flex", justifyContent: "space-between" }}>
        <span>Last 60 s</span>
        <span>{avg !== null ? `Avg ${avg}%` : "—"}</span>
      </div>
      <canvas ref={canvasRef} style={{ width: "100%", height: 48, display: "block" }} />
    </div>
  );
}
