"use client";

import { useEffect, useRef } from "react";
import type { DiagnosticPayload } from "@/types";

interface OverlayToggles {
  facialMidline: boolean;
  eyeLine: boolean;
  poseMidline: boolean;
  pnpPoints: boolean;
  irisPoints: boolean;
  poseAxes: boolean;
}

interface Props {
  data: DiagnosticPayload | null;
  overlays: OverlayToggles;
  /** Width and height of the video element being overlaid */
  videoWidth: number;
  videoHeight: number;
}

function lm(
  landmarks: DiagnosticPayload["landmarks"],
  name: string,
  w: number,
  h: number
): [number, number] | null {
  const pt = landmarks[name as keyof typeof landmarks];
  if (!pt) return null;
  return [pt[0] * w, pt[1] * h];
}

export function DiagnosticOverlay({ data, overlays, videoWidth, videoHeight }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const w = videoWidth || canvas.offsetWidth;
    const h = videoHeight || canvas.offsetHeight;
    canvas.width = w;
    canvas.height = h;
    ctx.clearRect(0, 0, w, h);

    if (!data || !data.landmarks) return;
    const L = data.landmarks;

    ctx.lineWidth = 1.5;
    ctx.font = "10px monospace";

    // ── Facial midline ───────────────────────────────────────────────
    if (overlays.facialMidline) {
      const nose   = lm(L, "nose_bridge", w, h);
      const chin   = lm(L, "chin", w, h);
      const noseTip = lm(L, "nose_tip", w, h);
      if (nose && chin) {
        ctx.beginPath();
        ctx.moveTo(nose[0], nose[1]);
        ctx.lineTo(chin[0], chin[1]);
        ctx.strokeStyle = "rgba(79,142,247,.75)";
        ctx.stroke();
      }
      if (noseTip) {
        ctx.beginPath();
        ctx.arc(noseTip[0], noseTip[1], 3, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(79,142,247,.9)";
        ctx.fill();
      }
    }

    // ── Eye line ─────────────────────────────────────────────────────
    if (overlays.eyeLine) {
      const lo = lm(L, "left_eye_outer", w, h);
      const ro = lm(L, "right_eye_outer", w, h);
      if (lo && ro) {
        ctx.beginPath();
        ctx.moveTo(lo[0], lo[1]);
        ctx.lineTo(ro[0], ro[1]);
        ctx.strokeStyle = "rgba(34,197,94,.75)";
        ctx.stroke();
      }
    }

    // ── Pose midline (shoulder → hip) ────────────────────────────────
    if (overlays.poseMidline) {
      const ls = lm(L, "left_shoulder", w, h);
      const rs = lm(L, "right_shoulder", w, h);
      const lh = lm(L, "left_hip", w, h);
      const rh = lm(L, "right_hip", w, h);
      if (ls && rs && lh && rh) {
        const sMid: [number, number] = [(ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2];
        const hMid: [number, number] = [(lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2];
        ctx.beginPath();
        ctx.moveTo(sMid[0], sMid[1]);
        ctx.lineTo(hMid[0], hMid[1]);
        ctx.strokeStyle = "rgba(245,158,11,.75)";
        ctx.setLineDash([4, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
        // shoulder bar
        ctx.beginPath();
        ctx.moveTo(ls[0], ls[1]);
        ctx.lineTo(rs[0], rs[1]);
        ctx.strokeStyle = "rgba(245,158,11,.5)";
        ctx.stroke();
      }
    }

    // ── PnP reference points ─────────────────────────────────────────
    if (overlays.pnpPoints) {
      const PNP_NAMES = ["nose_tip", "chin", "left_eye_outer", "right_eye_outer", "left_mouth", "right_mouth"];
      const COLORS = ["#4f8ef7", "#ef4444", "#22c55e", "#22c55e", "#f59e0b", "#f59e0b"];
      PNP_NAMES.forEach((name, i) => {
        const pt = lm(L, name, w, h);
        if (!pt) return;
        ctx.beginPath();
        ctx.arc(pt[0], pt[1], 4, 0, Math.PI * 2);
        ctx.strokeStyle = COLORS[i];
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });
    }

    // ── Iris landmarks ───────────────────────────────────────────────
    if (overlays.irisPoints) {
      const li = lm(L, "left_iris", w, h);
      const ri = lm(L, "right_iris", w, h);
      [li, ri].forEach((pt) => {
        if (!pt) return;
        ctx.beginPath();
        ctx.arc(pt[0], pt[1], 5, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(124,92,252,.9)";
        ctx.lineWidth = 2;
        ctx.stroke();
      });
    }

    // ── Pose orientation axes (yaw/pitch text overlay) ───────────────
    if (overlays.poseAxes) {
      ctx.fillStyle = "rgba(232,236,244,.85)";
      ctx.font = "bold 11px 'JetBrains Mono', monospace";
      ctx.fillText(
        `Y:${data.yaw_deg.toFixed(1)}° P:${data.pitch_deg.toFixed(1)}° R:${data.roll_deg.toFixed(1)}°`,
        8,
        h - 8
      );
    }
  }, [data, overlays, videoWidth, videoHeight]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
      }}
    />
  );
}
