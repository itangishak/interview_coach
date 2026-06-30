"""Interview coaching WebSocket and REST endpoints."""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.services.interview_analyzer import InterviewAnalyzer
from app.services.session_service import SessionService

router = APIRouter(tags=["interview"])


@router.websocket("/ws/interview")
async def interview_stream(websocket: WebSocket):
    """Receive base64 webcam frames and stream per-frame analysis."""
    await websocket.accept()
    settings = get_settings()
    analyzer = InterviewAnalyzer()
    sessions = SessionService()
    session_id: str | None = None
    fps = settings.interview.target_fps

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            msg_type = data.get("type", "frame")

            if msg_type == "start":
                session_id = data.get("session_id") or str(uuid.uuid4())
                analyzer.reset()
                started = sessions.start_session(session_id)
                await websocket.send_json({"type": "status", "payload": started})
                continue

            if msg_type == "frame":
                image_b64 = data.get("image", "")
                if not image_b64:
                    continue
                try:
                    _, encoded = image_b64.split(",", 1)
                except ValueError:
                    encoded = image_b64

                img_bytes = base64.b64decode(encoded)
                nparr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                result = analyzer.analyze_frame(frame)
                if session_id:
                    sessions.append_frame(session_id, result)

                await websocket.send_json({"type": "analysis", "payload": result})
                continue

            if msg_type == "stop":
                if not session_id:
                    await websocket.send_json(
                        {"type": "summary", "payload": {"error": "No active session"}}
                    )
                    continue
                summary = sessions.build_summary(session_id, fps=fps)
                sessions.end_session(session_id, summary)
                await websocket.send_json({"type": "summary", "payload": summary})
                continue

    except WebSocketDisconnect:
        return


@router.get("/interview/sessions")
async def list_sessions(limit: int = 20) -> dict[str, Any]:
    sessions = SessionService()
    return {"sessions": sessions.list_sessions(limit=limit)}


@router.get("/interview/sessions/{session_id}")
async def get_session_summary(session_id: str) -> dict[str, Any]:
    sessions = SessionService()
    record = sessions.get_session(session_id)
    if record is None:
        return {"error": "Session not found"}
    return record


@router.get("/interview/sessions/{session_id}/report")
async def get_session_report(session_id: str) -> dict[str, Any]:
    """Aggregate metrics and recommendations for the session report modal."""
    sessions = SessionService()
    record = sessions.get_session(session_id)
    if record is None:
        return {"error": "Session not found"}

    summary = record.get("summary") or sessions.build_summary(session_id)
    return {
        "session_id": session_id,
        "started_at": record["started_at"],
        "ended_at": record.get("ended_at"),
        "total_frames": record.get("frame_count", 0),
        "metrics": {
            key: summary[key]
            for key in SessionService.METRICS
            if key in summary
        },
        "recommendations": summary.get("recommendations", []),
        "duration_seconds": summary.get("duration_seconds", 0),
    }