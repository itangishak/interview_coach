"""Interview coaching WebSocket and REST endpoints."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.interview_analyzer import InterviewAnalyzer
from app.services.session_service import SessionService
from app.services.user_profile_service import UserProfileService

router = APIRouter(tags=["interview"])

# ── Lazy singleton accessors ──────────────────────────────────────────────────
# SingletonMeta is now lock-free, so calling these inside async handlers
# is safe: the worst case is a harmless double-creation race that
# immediately discards the extra instance.  The FastAPI lifespan in
# main.py pre-warms them in a thread pool before serving traffic.
def _sessions() -> SessionService:
    return SessionService()

def _profiles() -> UserProfileService:
    return UserProfileService()


@router.websocket("/ws/interview")
async def interview_stream(websocket: WebSocket):
    """Receive base64 webcam frames and stream per-frame analysis."""
    await websocket.accept()
    settings = get_settings()
    analyzer: InterviewAnalyzer | None = None
    session_id: str | None = None
    fps = settings.interview.target_fps
    loop = asyncio.get_event_loop()

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            msg_type = data.get("type", "frame")

            if msg_type == "start":
                session_id = data.get("session_id") or str(uuid.uuid4())
                user_id    = data.get("user_id") or None
                diagnostic = bool(data.get("diagnostic", False))
                analyzer   = InterviewAnalyzer(user_id=user_id, diagnostic_mode=diagnostic)
                analyzer.reset()
                # Run blocking DB write in thread pool — keeps event loop free
                started = await loop.run_in_executor(
                    None, _sessions().start_session, session_id
                )
                await websocket.send_json({"type": "status", "payload": started})
                continue

            if msg_type == "frame":
                if analyzer is None:
                    analyzer = InterviewAnalyzer()
                image_b64 = data.get("image", "")
                if not image_b64:
                    continue
                try:
                    _, encoded = image_b64.split(",", 1)
                except ValueError:
                    encoded = image_b64

                img_bytes = base64.b64decode(encoded)
                nparr     = np.frombuffer(img_bytes, np.uint8)
                frame     = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                # analyze_frame is CPU-bound — run in executor to avoid blocking
                result = await loop.run_in_executor(None, analyzer.analyze_frame, frame)
                if session_id:
                    await loop.run_in_executor(
                        None, _sessions().append_frame, session_id, result
                    )

                await websocket.send_json({"type": "analysis", "payload": result})
                continue

            if msg_type == "stop":
                if not session_id:
                    await websocket.send_json(
                        {"type": "summary", "payload": {"error": "No active session"}}
                    )
                    continue
                summary = await loop.run_in_executor(
                    None, lambda: _sessions().build_summary(session_id, fps=fps)
                )
                await loop.run_in_executor(
                    None, _sessions().end_session, session_id, summary
                )
                if analyzer is not None:
                    await loop.run_in_executor(None, analyzer.save_session_baseline)

                await websocket.send_json({"type": "summary", "payload": summary})
                continue

    except WebSocketDisconnect:
        if analyzer is not None:
            try:
                await loop.run_in_executor(None, analyzer.save_session_baseline)
            except Exception:
                pass
        return


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.get("/interview/sessions")
async def list_sessions(limit: int = 20) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    return {"sessions": await loop.run_in_executor(None, lambda: _sessions().list_sessions(limit=limit))}


@router.get("/interview/sessions/{session_id}")
async def get_session_summary(session_id: str) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    record = await loop.run_in_executor(None, _sessions().get_session, session_id)
    if record is None:
        return {"error": "Session not found"}
    return record


@router.get("/interview/sessions/{session_id}/report")
async def get_session_report(session_id: str) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    record = await loop.run_in_executor(None, _sessions().get_session, session_id)
    if record is None:
        return {"error": "Session not found"}

    summary = record.get("summary") or await loop.run_in_executor(
        None, _sessions().build_summary, session_id
    )
    return {
        "session_id":      session_id,
        "started_at":      record["started_at"],
        "ended_at":        record.get("ended_at"),
        "total_frames":    record.get("frame_count", 0),
        "metrics": {
            key: summary[key]
            for key in SessionService.METRICS
            if key in summary
        },
        "recommendations": summary.get("recommendations", []),
        "duration_seconds": summary.get("duration_seconds", 0),
    }


# ── User profile endpoints ────────────────────────────────────────────────────

@router.get("/interview/profiles/{user_id}")
async def get_profile(user_id: str) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _profiles().get_profile, user_id)


class CameraOffsetPayload(BaseModel):
    pitch_deg: float


@router.post("/interview/profiles/{user_id}/camera-offset")
async def set_camera_offset(user_id: str, payload: CameraOffsetPayload) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: _profiles().update_camera_offset(user_id, pitch_deg=payload.pitch_deg)
    )
    return {"user_id": user_id, "camera_pitch_offset_deg": payload.pitch_deg, "saved": True}


@router.get("/interview/profiles")
async def list_profiles() -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    return {"profiles": await loop.run_in_executor(None, _profiles().list_profiles)}
