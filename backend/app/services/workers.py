"""One private, authenticated worker channel per live room (single coordinator)."""
import asyncio
import json
import os
import logging
from uuid import uuid4
from time import monotonic

from websockets.asyncio.client import connect
from app.services.game import Peer, encode
from app.services.rooms import RoomError


class WorkerRoom:
    def __init__(self, hub, code, url):
        self.hub, self.code, self.url = hub, code, url
        self.peers = {}
        self.queue = asyncio.Queue(maxsize=128)
        self.failed = False
        self.pending = {}
        self.ended = False
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
                        if item['op'] == 'inspected':
                            future = self.pending.pop(item['request'], None)
                            if future and not future.done():
                                future.set_result(item['phase'])
                            continue
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
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RoomError(503, 'SERVER_BUSY', 'Room worker unavailable'))
            self.pending.clear()
            # Keep the failed allocation as a tombstone even if SQL is unavailable.
            # Never restart an interrupted match under the same room identity.
            for peer in list(self.peers.values()):
                peer.close()
                try:
                    await asyncio.wait_for(peer.socket.send_text(encode('room.closed', dict(reason='server_shutdown'))), 1)
                except Exception:
                    pass
                peer.close(1012)
            self.peers.clear()
            if not self.hub.stopping and not self.ended:
                try:
                    await asyncio.to_thread(self.hub.rooms_service.close_worker_room, self.code)
                except Exception:
                    logging.getLogger(__name__).exception('Failed to persist worker loss room=%s', self.code)


class WorkerHub:
    def __init__(self, rooms_service):
        self.rooms_service = rooms_service
        self.rooms = {}
        self.stopping = False
        self.lock = asyncio.Lock()
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
        peer = room.attach(socket, facts)
        self.rooms_service.reservations.pop(peer.member_id, None)
        self.rooms_service.empty_since.pop(code, None)
        return room, peer

    def detach(self, room, peer):
        room.peers.pop(peer.connection_id, None)
        peer.close()
        connected = {p.member_id for p in room.peers.values() if not p.task.done()}
        if peer.member_id not in connected:
            self.rooms_service.reservations.setdefault(peer.member_id, monotonic())
        if not connected:
            self.rooms_service.empty_since.setdefault(room.code, monotonic())
        if not room.failed:
            try:
                room.enqueue(dict(op='detach', id=peer.connection_id))
            except RoomError:
                pass

    async def refresh(self, code, token=None):
        """Called under lock: barrier all prior inputs before a SQL policy decision."""
        room = self.rooms.get(code)
        phase = 'lobby'
        connected = frozenset()
        if room and not room.failed:
            request = uuid4().hex
            future = asyncio.get_running_loop().create_future()
            room.pending[request] = future
            room.enqueue(dict(op='inspect', request=request))
            try:
                phase = await asyncio.wait_for(future, 5)
            except TimeoutError:
                room.task.cancel()
                raise RoomError(503, 'SERVER_BUSY', 'Worker unavailable')
            finally:
                room.pending.pop(request, None)
            connected = frozenset(p.member_id for p in room.peers.values() if not p.task.done())
        facts = await asyncio.to_thread(self.rooms_service.lifecycle, code,
                                         phase=phase, connected=connected, token=token)
        if room and not room.failed:
            if facts is None or 'closed' in facts:
                room.ended = True
                reason = facts['closed'] if facts else 'expired'
                for peer in list(room.peers.values()):
                    peer.close()
                    try:
                        await asyncio.wait_for(peer.socket.send_text(encode('room.closed', dict(reason=reason))), 1)
                    except Exception:
                        pass
                    peer.close(4404)
                room.task.cancel()
                await asyncio.gather(room.task, return_exceptions=True)
                if self.rooms.get(code) is room:
                    del self.rooms[code]
            else:
                room.enqueue(dict(op='membership', facts=facts))
        return facts

    async def cleanup(self):
        async with self.lock:
            for code in await asyncio.to_thread(self.rooms_service.open_codes):
                await self.refresh(code)

    async def close(self):
        self.stopping = True
        tasks = [room.task for room in self.rooms.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.rooms.clear()
