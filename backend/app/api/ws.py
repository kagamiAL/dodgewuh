"""Authenticated lobby transport. Gameplay is unavailable until worker integration."""
import asyncio
import os
from time import monotonic
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.protocol import decode_client
from app.services.rooms import RoomError

router = APIRouter()


@router.websocket('/ws/rooms/{room_code}')
async def websocket(socket: WebSocket, room_code: str):
    origins = {os.getenv('PUBLIC_ORIGIN', 'http://localhost:5173')}
    origins.update(filter(None, os.getenv('DEV_ORIGINS', '').split(',')))
    if socket.headers.get('origin') not in origins or socket.query_params:
        await socket.close(code=4400)
        return
    # The static lobby is an explicit local integration aid, never production authority.
    if os.getenv('LOBBY_BASELINE_ENABLED') != 'true':
        await socket.close(code=4400)
        return
    await socket.accept()
    hub = socket.app.state.lobby_hub
    key = None
    facts = None
    try:
        raw = await asyncio.wait_for(socket.receive_text(), 5)
        if len(raw.encode()) > 8192:
            await socket.close(code=4400)
            return
        try:
            hello = decode_client(raw)
            if hello.type != 'session.hello':
                raise ValueError('Hello required')
            facts = await asyncio.to_thread(socket.app.state.rooms.authenticate, room_code, hello.payload.token)
        except RoomError as exc:
            await socket.close(code=4404 if exc.status == 404 else 4401)
            return
        except (ValueError, TypeError, AttributeError):
            await socket.close(code=4401)
            return
        code = facts['room_code']
        key = (code, facts['member_id'])
        lock = hub.locks.setdefault(code, asyncio.Lock())
        async with lock:
            facts = await asyncio.to_thread(socket.app.state.rooms.authenticate, code, hello.payload.token)
            prior = hub.sockets.get(key)
            hub.sockets[key] = socket
            if prior:
                await prior.close(code=4409)
            hub.revisions[code] = hub.revisions.get(code, 0) + 1
            room, state = hub.baseline(facts)
            await hub.send(socket, 'session.welcome', dict(member_id=facts['member_id'], room=room, state=state))
            await hub.broadcast(code, room)
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
                await hub.send(socket, 'error', dict(code='BAD_MESSAGE', message='Malformed message', ref_seq=None))
                await socket.close(code=4400)
                break
            if message.type == 'session.hello':
                await socket.close(code=4400)
                break
            # Recheck persisted expiry/revocation on each heartbeat or command.
            facts = await asyncio.to_thread(socket.app.state.rooms.authenticate, code, hello.payload.token)
            if message.type == 'session.ping':
                await hub.send(socket, 'session.pong', message.payload.model_dump())
            else:
                await hub.send(socket, 'error', dict(code='SERVER_BUSY',
                    message='Simulation worker integration is not available yet',
                    ref_seq=getattr(message.payload, 'seq', None)))
    except TimeoutError:
        await socket.close(code=4401 if key is None else 4400)
    except RoomError as exc:
        await socket.close(code=4404 if exc.status == 404 else 4401)
    except WebSocketDisconnect:
        pass
    finally:
        if key and hub.sockets.get(key) is socket:
            async with hub.locks[key[0]]:
                if hub.sockets.get(key) is socket:
                    del hub.sockets[key]
                    hub.revisions[key[0]] += 1
                    room, _ = hub.baseline(facts)
                    await hub.broadcast(key[0], room)
