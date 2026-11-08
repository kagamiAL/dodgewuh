"""Private game runtime. Only the coordinator may supply authenticated membership facts."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
import secrets

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from app.protocol import Health, decode_client
from app.services.game import GameHub


@asynccontextmanager
async def lifespan(app):
    if not os.getenv('GAME_WORKER_SECRET'):
        raise ValueError('GAME_WORKER_SECRET must be nonempty')
    app.state.hub = GameHub()
    yield
    app.state.hub.close()


app = FastAPI(title='dodgewuh game worker', version='0.1.0', lifespan=lifespan)


@app.get('/api/health', response_model=Health)
def health() -> Health:
    return Health(build=os.getenv('BUILD_SHA', 'dev'), rooms=len(app.state.hub.rooms))


class RelaySocket:
    def __init__(self, queue, connection_id):
        self.queue, self.id = queue, connection_id

    async def send_text(self, text):
        await self.queue.put(dict(op='message', id=self.id, text=text))

    async def close(self, code=4400):
        await self.queue.put(dict(op='close', id=self.id, code=code))


@app.websocket('/internal/room')
async def room_channel(socket: WebSocket):
    expected = 'Bearer ' + os.environ['GAME_WORKER_SECRET']
    if not secrets.compare_digest(socket.headers.get('authorization', ''), expected):
        await socket.close(code=4401)
        return
    await socket.accept()
    hub = socket.app.state.hub
    queue = asyncio.Queue(maxsize=128)
    peers = {}
    room = None

    async def send():
        while True:
            await socket.send_json(await queue.get())

    sender = asyncio.create_task(send())
    # A failed sender must also terminate the receiver and release room ownership.
    sender.add_done_callback(lambda task: asyncio.create_task(socket.close()) if not task.cancelled() else None)
    try:
        while True:
            item = json.loads(await socket.receive_text())
            connection_id = item['id']
            if item['op'] == 'attach':
                facts = item['facts']
                if room is None:
                    # A second coordinator/channel must never share a simulation.
                    if facts['room_code'] in hub.rooms:
                        await socket.close(code=4409)
                        break
                elif facts['room_code'] != room.code:
                    raise ValueError('One room per channel')
                if connection_id in peers:
                    raise ValueError('Duplicate connection')
                room, peer = hub.attach(RelaySocket(queue, connection_id), facts)
                peers[connection_id] = peer
            elif item['op'] == 'detach':
                peer = peers.pop(connection_id, None)
                if peer:
                    room.detach(peer)
            elif item['op'] == 'input':
                message = decode_client(json.dumps(item['message']))
                if message.type in ('session.hello', 'session.ping'):
                    raise ValueError('Coordinator-only session message')
                room.handle(peers[connection_id], message)
            else:
                raise ValueError('Unknown worker operation')
    except (WebSocketDisconnect, ValueError, KeyError, RuntimeError):
        pass
    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        if room:
            room.close()
            if hub.rooms.get(room.code) is room:
                del hub.rooms[room.code]
