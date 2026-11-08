"""Public registration routes and bounded, process-local rate windows."""
import asyncio
from collections import OrderedDict, deque
from threading import Lock
from time import monotonic
from fastapi import APIRouter, Request, Response
from app.protocol import CreateRoom, JoinRoom, Registration
from app.services.rooms import RoomError

router = APIRouter()
# Each key is (client IP, action); each deque stores recent monotonic request times.
# FastAPI runs these sync handlers in threads, so updates need a shared lock.
_windows = OrderedDict()
_lock = Lock()


def limit(request, action, maximum):
    """Enforce a rolling 60-second limit without unbounded per-client memory."""
    # Trust the direct peer only. Proxy headers require explicit trusted proxy configuration.
    key = (request.client.host if request.client else "unknown", action)
    now = monotonic()
    with _lock:
        # Remove inactive clients, then trim individual timestamps for the current client.
        for old_key in list(_windows):
            if not _windows[old_key] or _windows[old_key][-1] <= now - 60:
                del _windows[old_key]
        # Reject new keys at the memory cap instead of evicting active rate limits.
        if key not in _windows and len(_windows) >= 10000:
            raise RoomError(429, "RATE_LIMIT", "Too many requests")
        window = _windows.setdefault(key, deque())
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= maximum:
            raise RoomError(429, "RATE_LIMIT", "Too many requests")
        window.append(now)


@router.post("/api/rooms", status_code=201, response_model=Registration)
async def create(body: CreateRoom, request: Request, response: Response):
    """Create a room and register its immutable host screen in one transaction."""
    limit(request, "create", 5)
    # Registration includes a bearer secret and must not be cached.
    response.headers["Cache-Control"] = "no-store"
    async with request.app.state.game_hub.lock:
        return await asyncio.to_thread(request.app.state.rooms.register, body.name)


@router.post("/api/rooms/{room_code}/members", status_code=201, response_model=Registration)
async def join(room_code: str, body: JoinRoom, request: Request, response: Response):
    """Register a screen or phone; the service enforces phase and seat capacity."""
    limit(request, "join", 30)
    response.headers["Cache-Control"] = "no-store"
    hub = request.app.state.game_hub
    async with hub.lock:
        await hub.refresh(room_code.strip().upper())
        return await asyncio.to_thread(request.app.state.rooms.register, body.name, body.device, room_code)


@router.delete('/api/rooms/{room_code}/members/me', status_code=204)
async def leave(room_code: str, request: Request):
    authorization = request.headers.get('authorization', '')
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token or ' ' in token:
        raise RoomError(401, 'UNAUTHORIZED', 'Bearer membership required')
    hub = request.app.state.game_hub
    async with hub.lock:
        await hub.refresh(room_code.strip().upper(), token=token)
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})
