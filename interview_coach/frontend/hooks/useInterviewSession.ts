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
  startSession: (opts?: { diagnosticMode?: boolean }) => void;
  stopSession: () => void;
}

export function useInterviewSession(userId?: string): InterviewSessionState {
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

  // Reconnect bookkeeping
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const intentionalCloseRef = useRef(false);
  const pendingStartRef = useRef<string | null>(null);

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    clearReconnect();
    if (intentionalCloseRef.current) return;

    const delay = Math.min(1000 * 2 ** reconnectAttemptRef.current, 30000);
    reconnectAttemptRef.current += 1;

    reconnectTimerRef.current = setTimeout(() => {
      connect(); // eslint-disable-line @typescript-eslint/no-use-before-define
    }, delay);
  }, [clearReconnect]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (intentionalCloseRef.current) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      reconnectAttemptRef.current = 0;
      // If we have a pending session start (e.g. after reconnect), resend it
      if (pendingStartRef.current) {
        ws.send(JSON.stringify({ type: "start", session_id: pendingStartRef.current }));
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Only reconnect if the user did NOT intentionally stop
      if (!intentionalCloseRef.current) {
        scheduleReconnect();
      }
    };

    ws.onerror = () => {
      setConnected(false);
    };

    ws.onmessage = (event: MessageEvent) => {
      const msg = JSON.parse(event.data) as WSMessage;
      if (msg.type === "status") {
        setSessionId(msg.payload.session_id);
      } else if (msg.type === "analysis") {
        setAnalysis(msg.payload);
      } else if (msg.type === "summary") {
        setSummary(msg.payload);
        setActive(false);
        pendingStartRef.current = null;
      }
    };
  }, [scheduleReconnect]);

  // Connect on mount, cleanup on unmount
  useEffect(() => {
    intentionalCloseRef.current = false;
    connect();
    return () => {
      intentionalCloseRef.current = true;
      clearReconnect();
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect, clearReconnect]);

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
    const dataUrl = canvas.toDataURL("image/jpeg", 0.85); // raised from 0.7 — better landmark accuracy
    ws.send(JSON.stringify({ type: "frame", image: dataUrl }));
  }, []);

  const startSession = useCallback(async (opts?: { diagnosticMode?: boolean }) => {
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
    pendingStartRef.current = sid;
    ws.send(JSON.stringify({
      type: "start",
      session_id: sid,
      diagnostic: opts?.diagnosticMode ?? false,
      ...(userId ? { user_id: userId } : {}),
    }));
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
    pendingStartRef.current = null;
  }, []);

  return { connected, active, analysis, summary, sessionId, startSession, stopSession };
}