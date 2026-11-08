"""Authenticated room socket: hello, heartbeat and routing into the room's live simulation."""
import asyncio
import os
from time import monotonic
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.protocol import decode_client
from app.services.game import encode
from app.services.rooms import RoomError

router = APIRouter()


@router.websocket('/ws/rooms/{room_code}')
async def websocket(socket: WebSocket, room_code: str):
    origins = {os.getenv('PUBLIC_ORIGIN', 'http://localhost:5173')}
    origins.update(filter(None, os.getenv('DEV_ORIGINS', '').split(',')))
    # DEV_ORIGINS='*' accepts any origin, so a fresh tunnel URL needs no coordinator restart.
    origin_ok = '*' in origins or socket.headers.get('origin') in origins
    if not origin_ok or socket.query_params:
        await socket.close(code=4400)
        return
    await socket.accept()
    hub = socket.app.state.game_hub
    rooms = socket.app.state.rooms
    room = peer = None
    try:
        raw = await asyncio.wait_for(socket.receive_text(), 5)
        if len(raw.encode()) > 8192:
            await socket.close(code=4400)
            return
        try:
            hello = decode_client(raw)
            if hello.type != 'session.hello':
                raise ValueError('Hello required')
            async with hub.lock:
                await hub.refresh(room_code.strip().upper())
                facts = await asyncio.to_thread(rooms.authenticate, room_code, hello.payload.token)
                room, peer = await hub.attach(socket, facts)
        except RoomError as exc:
            await socket.close(code=4404 if exc.status == 404 else 4401)
            return
        except (ValueError, TypeError, AttributeError):
            await socket.close(code=4401)
            return
        code = facts['room_code']
        allowance = 60.0
        last_message = monotonic()
        while True:
            raw = await asyncio.wait_for(socket.receive_text(), 15)
            if len(raw.encode()) > 8192:
                await socket.close(code=4400)
                break
            now = monotonic()
            allowance = min(60.0, allowance + (now - last_message) * 40)
            last_message = now
            allowance -= 1
            if allowance < 0:
                await socket.close(code=4429)
                break
            try:
                message = decode_client(raw)
            except (ValueError, TypeError, AttributeError):
                peer.send(encode('error', dict(code='BAD_MESSAGE', message='Malformed message', ref_seq=None)))
                await socket.close(code=4400)
                break
            if message.type == 'session.hello':
                await socket.close(code=4400)
                break
            if message.type == 'session.ping':
                # Recheck persisted expiry/revocation at heartbeat cadence, not per 20 Hz input.
                await asyncio.to_thread(rooms.authenticate, code, hello.payload.token)
                peer.send(encode('session.pong', message.payload.model_dump()))
            else:
                async with hub.lock:
                    room.handle(peer, message)
    except TimeoutError:
        await socket.close(code=4401 if peer is None else 4400)
    except RoomError as exc:
        await socket.close(code=4404 if exc.status == 404 else 4401)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if peer:
            async with hub.lock:
                hub.detach(room, peer)
