"""One private, authenticated worker channel per live room (single coordinator)."""
import asyncio
import json
import os
import logging
from uuid import uuid4

from websockets.asyncio.client import connect
from app.services.game import Peer, encode
from app.services.rooms import RoomError


class WorkerRoom:
    def __init__(self, hub, code, url):
        self.hub, self.code, self.url = hub, code, url
        self.peers = {}
        self.queue = asyncio.Queue(maxsize=128)
        self.failed = False
        self.task = asyncio.create_task(self.run())

    def enqueue(self, message):
        if self.failed:
            raise RoomError(503, 'SERVER_BUSY', 'Room worker unavailable')
        try:
            self.queue.put_nowait(json.dumps(message))
        except asyncio.QueueFull:
            self.task.cancel()
            raise RoomError(503, 'SERVER_BUSY', 'Room worker overloaded')

    def attach(self, socket, facts):
        peer = Peer(socket, facts['member_id'])
        peer.connection_id = uuid4().hex
        self.peers[peer.connection_id] = peer
        try:
            self.enqueue(dict(op='attach', id=peer.connection_id, facts=facts))
        except Exception:
            self.peers.pop(peer.connection_id)
            peer.close(1013)
            raise
        return peer

    def handle(self, peer, message):
        self.enqueue(dict(op='input', id=peer.connection_id, message=message.model_dump()))

    async def run(self):
        try:
            async with connect(self.url, additional_headers={'Authorization': f'Bearer {self.hub.secret}'},
                               open_timeout=5, ping_interval=5, ping_timeout=5,
                               max_size=262144, max_queue=32) as socket:
                async def send():
                    while True:
                        await socket.send(await self.queue.get())
                sender = asyncio.create_task(send())
                try:
                    async for raw in socket:
                        item = json.loads(raw)
                        peer = self.peers.get(item['id'])
                        if peer is None:
                            continue
                        if item['op'] == 'close':
                            peer.close(item['code'])
                        else:
                            text = item['text']
                            if json.loads(text)['type'] == 'state.snapshot':
                                peer.send_snapshot(text)
                            else:
                                peer.send(text)
                finally:
                    sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).warning("Worker channel lost room=%s", self.code)
        finally:
            self.failed = True
            # Keep the failed allocation as a tombstone even if SQL is unavailable.
            # Never restart an interrupted match under the same room identity.
            for peer in list(self.peers.values()):
                peer.close()
                try:
                    await asyncio.wait_for(peer.socket.send_text(encode('room.closed', dict(reason='server_shutdown'))), 1)
                except Exception:
                    pass
                peer.close(1012)
            if not self.hub.stopping:
                try:
                    await asyncio.to_thread(self.hub.rooms_service.close_worker_room, self.code)
                except Exception:
                    logging.getLogger(__name__).exception('Failed to persist worker loss room=%s', self.code)


class WorkerHub:
    def __init__(self, rooms_service):
        self.rooms_service = rooms_service
        self.rooms = {}
        self.stopping = False
        self.secret = os.environ['GAME_WORKER_SECRET']
        if not self.secret:
            raise ValueError('GAME_WORKER_SECRET must be nonempty')
        urls = os.getenv('GAME_WORKER_URLS', os.getenv('GAME_WORKER_URL', 'http://localhost:8001'))
        self.urls = [u.strip().rstrip('/').replace('https://', 'wss://').replace('http://', 'ws://')
                     + '/internal/room' for u in urls.split(',') if u.strip()]
        if not self.urls:
            raise ValueError('At least one worker URL is required')
        self.next_worker = 0

    def attach(self, socket, facts):
        code = facts['room_code']
        room = self.rooms.get(code)
        if room is None:
            room = self.rooms[code] = WorkerRoom(self, code, self.urls[self.next_worker % len(self.urls)])
            self.next_worker += 1
        return room, room.attach(socket, facts)

    def detach(self, room, peer):
        room.peers.pop(peer.connection_id, None)
        peer.close()
        if not room.failed:
            try:
                room.enqueue(dict(op='detach', id=peer.connection_id))
            except RoomError:
                pass

    async def close(self):
        self.stopping = True
        tasks = [room.task for room in self.rooms.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.rooms.clear()
