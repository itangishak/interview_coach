import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.prediction_service import PredictionService

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/sign")
async def sign_stream(websocket: WebSocket):
    await websocket.accept()
    service = PredictionService.from_settings()
    await websocket.send_json({"type": "status", "payload": service.status()})

    try:
        while True:
            payload = service.predict_and_assemble(
                None,
                sign_type="dynamic",
                append_to_sentence=True,
                source="websocket",
            )
            await websocket.send_json({"type": "prediction", "payload": payload})
            await asyncio.sleep(2.5)
    except WebSocketDisconnect:
        return