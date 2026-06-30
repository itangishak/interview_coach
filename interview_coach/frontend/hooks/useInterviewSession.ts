"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AnalysisPayload, SessionSummary, WSMessage } from "@/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/interview";
const FRAME_INTERVAL_MS = 67; // ~15 fps

export interface InterviewSessionState {
  connected: boolean;
  active: boolean;
  analysis: AnalysisPayload | null;
  summary: SessionSummary | null;
  sessionId: string | null;
  startSession: () => void;
  stopSession: () => void;
}

export function useInterviewSession(): InterviewSessionState {
  const [connected, setConnected] = useState(false);
  const [active, setActive] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null);
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // Connect WebSocket once on mount
  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => { setConnected(false); setActive(false); };
    ws.onerror = () => setConnected(false);

    ws.onmessage = (event: MessageEvent) => {
      const msg = JSON.parse(event.data) as WSMessage;
      if (msg.type === "status") {
        setSessionId(msg.payload.session_id);
      } else if (msg.type === "analysis") {
        setAnalysis(msg.payload);
      } else if (msg.type === "summary") {
        setSummary(msg.payload);
        setActive(false);
      }
    };

    return () => { ws.close(); };
  }, []);

  const captureAndSend = useCallback(() => {
    const ws = wsRef.current;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !video || !canvas) return;
    if (video.readyState < 2) return; // not enough data yet

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    ws.send(JSON.stringify({ type: "frame", image: dataUrl }));
  }, []);

  const startSession = useCallback(async () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    // Get webcam
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      streamRef.current = stream;

      // Attach stream to a hidden video element
      let video = videoRef.current;
      if (!video) {
        video = document.createElement("video");
        video.style.display = "none";
        video.playsInline = true;
        video.muted = true;
        document.body.appendChild(video);
        videoRef.current = video;
      }
      video.srcObject = stream;
      await video.play();

      // Hidden canvas for frame capture
      if (!canvasRef.current) {
        const canvas = document.createElement("canvas");
        canvas.style.display = "none";
        document.body.appendChild(canvas);
        canvasRef.current = canvas;
      }
    } catch {
      console.error("Camera access denied");
      return;
    }

    setSummary(null);
    setAnalysis(null);
    const sid = crypto.randomUUID();
    ws.send(JSON.stringify({ type: "start", session_id: sid }));
    setActive(true);

    frameTimerRef.current = setInterval(captureAndSend, FRAME_INTERVAL_MS);
  }, [captureAndSend]);

  const stopSession = useCallback(() => {
    const ws = wsRef.current;
    if (frameTimerRef.current) {
      clearInterval(frameTimerRef.current);
      frameTimerRef.current = null;
    }
    // Stop camera stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
    }
    setActive(false);
  }, []);

  return { connected, active, analysis, summary, sessionId, startSession, stopSession };
}
