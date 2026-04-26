import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.state import garden, ws_manager

router = APIRouter()


@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket, token: str = Query(...)):
    user_id = decode_token(token)
    if user_id is None:
        await websocket.close(code=1008)  # Policy Violation
        return

    await ws_manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps(garden.to_dict()))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
