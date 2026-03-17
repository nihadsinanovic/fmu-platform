import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# Active WebSocket connections per job_id
_connections: dict[str, list[WebSocket]] = {}


async def broadcast_job_update(job_id: str, message: dict) -> None:
    connections = _connections.get(job_id, [])
    for ws in connections:
        try:
            await ws.send_json(message)
        except Exception:
            pass


@router.websocket("/ws/jobs/{job_id}")
async def job_progress_websocket(websocket: WebSocket, job_id: uuid.UUID):
    await websocket.accept()
    key = str(job_id)
    if key not in _connections:
        _connections[key] = []
    _connections[key].append(websocket)

    try:
        while True:
            # Keep connection alive; client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        _connections[key].remove(websocket)
        if not _connections[key]:
            del _connections[key]
