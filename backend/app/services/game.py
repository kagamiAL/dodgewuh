"""Live rooms: one authoritative Simulation and fixed-step runner per room.

Rules live entirely in Richard's simulation. This module routes validated commands,
mirrors readiness/connection facts into it and broadcasts what it decides (plan 03,
"Pure simulation integration seam"). Everything here runs on one event loop and no
GameRoom method awaits, so each room's mutations are serialized by construction.

This runs on the game worker; the coordinator relays authenticated commands.
"""
import asyncio
from collections import deque
from dataclasses import is_dataclass
import logging
from time import monotonic

from simulation import (ArmsCommand, Assignment, InputRejected, LegsCommand, PhaseChanged,
    RolesChanged, Simulation, SimulationError, Vec2)
from app.protocol import server_messages

BOOT = monotonic()
TICK_S = 1 / 60
MAX_CATCH_UP = 5
OVERLOAD_S = 0.25
SNAPSHOT_EVERY = 3  # 60 Hz steps -> 20 Hz snapshots
RELIABLE_LIMIT = 32
SLOTS = ((1, 'arms'), (1, 'legs'), (2, 'arms'), (2, 'legs'))
PLAYING = ('countdown', 'active')

log = logging.getLogger('dodgewuh.game')


def now_ms():
    return int((monotonic() - BOOT) * 1000)


def plain(value):
    """Frozen simulation DTOs -> wire dicts (tuples become lists for strict models)."""
    if is_dataclass(value):
        return {name: plain(getattr(value, name)) for name in value.__dataclass_fields__}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    return value


def encode(event, payload):
    message = server_messages.validate_python(dict(v=1, type=event, server_ms=now_ms(), payload=payload))
    return message.model_dump_json()


class Peer:
    """One authenticated socket with its own sender task, so the runner never awaits a send.

    Reliable messages are FIFO and bounded; overflow disconnects the slow client.
    Only the latest snapshot is kept, and a reliable message discards a pending older
    snapshot so it can never be delivered after a transition (plan 03 barrier rule).
    """

    def __init__(self, socket, member_id):
        self.socket = socket
        self.member_id = member_id
        self.welcomed = False
        self.last_seq = 0
        self.reliable = deque()
        self.snapshot = None
        self.wake = asyncio.Event()
        self.task = asyncio.create_task(self._run())

    def send(self, text):
        if len(self.reliable) >= RELIABLE_LIMIT:
            log.warning('slow client disconnected member=%s', self.member_id)
            self.close(4400)
            return
        self.reliable.append(text)
        self.snapshot = None
        self.wake.set()

    def send_snapshot(self, text):
        self.snapshot = text
        self.wake.set()

    async def _run(self):
        try:
            while True:
                await self.wake.wait()
                self.wake.clear()
                while self.reliable or self.snapshot:
                    if self.reliable:
                        text = self.reliable.popleft()
                    else:
                        text, self.snapshot = self.snapshot, None
                    await asyncio.wait_for(self.socket.send_text(text), 2)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Timed out or already gone: closing ends the receive loop, which detaches us.
            await self._close_socket(4400)

    async def _close_socket(self, code):
        try:
            await self.socket.close(code=code)
        except Exception:
            pass

    def close(self, code=None):
        self.task.cancel()
        if code is not None:
            asyncio.create_task(self._close_socket(code))


class GameRoom:
    def __init__(self, facts):
        self.code = facts['room_code']
        self.facts = facts
        self.sim = Simulation()
        self.peers = {}
        self.status = {}
        self.cameras = {}  # connected screen member_id -> team whose Legs its camera drives
        self.revision = 0
        self.ordinal = 0
        self.steps = 0
        self.task = asyncio.create_task(self._run())

    # --- facts derived from membership -------------------------------------
    def _member(self, member_id):
        return next((m for m in self.facts['members'] if m['member_id'] == member_id), None)

    def _device(self, member_id):
        member = self._member(member_id)
        return member and member['device']

    def _screens(self):
        return [mid for mid in self.peers if self._device(mid) == 'screen']

    def _assigned(self, member_id):
        return any(a.member_id == member_id for a in self.sim.snapshot().assignments)

    def _camera_drives(self, member_id):
        """True when this phone is a Legs player whose team's movement comes from a screen camera."""
        return any(a.member_id == member_id and a.role == 'legs' and a.team in self.cameras.values()
                   for a in self.sim.snapshot().assignments)

    def _required(self, member_id):
        """Losing an assigned phone or the original host aborts an underway match."""
        return member_id == self.facts['host_id'] or self._assigned(member_id)

    def _sync_assignments(self):
        """Seat newly registered phones in free slots, in registration slot order.

        Only in lobby: preserve live occupied roles after simulation swaps, remove
        released members and fill missing team/role pairs from registration order.
        """
        state = self.sim.snapshot()
        if state.phase != 'lobby':
            return
        active = {m['member_id'] for m in self.facts['members']}
        retained = tuple(a for a in state.assignments if a.member_id in active)
        taken = {(a.team, a.role) for a in retained}
        seated = {a.member_id for a in retained}
        free = [slot for slot in SLOTS if slot not in taken]
        phones = sorted((m for m in self.facts['members'] if m['device'] == 'phone'), key=lambda m: m['slot'])
        added = [Assignment(member_id=m['member_id'], team=team, role=role)
                 for m, (team, role) in zip((m for m in phones if m['member_id'] not in seated), free)]
        if added or retained != state.assignments:
            self.sim.set_assignments(retained + tuple(added))
            self._clear_readiness()

    def _push_facts(self):
        ready = frozenset(mid for mid, st in self.status.items() if st['ready'] and mid in self.peers)
        self.sim.set_readiness(
            ready_member_ids=ready,
            connected_member_ids=frozenset(self.peers),
            screen_count=len(self._screens()),
            host_connected=self.facts['host_id'] in self.peers,
        )

    def _clear_readiness(self):
        for st in self.status.values():
            st.update(ready=False, calibrated=False)
        self._push_facts()

    def _abort(self, reason):
        if self.sim.snapshot().phase != 'lobby':
            log.info('room=%s aborted to lobby: %s', self.code, reason)
            self.sim.control('abort', reason)

    # --- outbound ------------------------------------------------------------
    def _room(self):
        state = self.sim.snapshot()
        members = []
        for m in self.facts['members']:
            st = self.status.get(m['member_id'], {})
            members.append(dict(member_id=m['member_id'], name=m['name'], device=m['device'],
                connected=m['member_id'] in self.peers, ready=st.get('ready', False),
                permission=st.get('permission', 'unknown'), calibrated=st.get('calibrated', False),
                camera_team=self.cameras.get(m['member_id'])))
        return dict(room_id=self.facts['room_id'], room_code=self.code, host_id=self.facts['host_id'],
            revision=self.revision, members=members, assignments=plain(state.assignments),
            assignment_version=state.assignment_version, phase=state.phase)

    def _broadcast(self, text):
        for peer in self.peers.values():
            if peer.welcomed:
                peer.send(text)

    def _broadcast_room(self):
        self.revision += 1
        self._broadcast(encode('room.updated', dict(room=self._room())))

    def _broadcast_snapshot(self):
        text = encode('state.snapshot', dict(state=plain(self.sim.snapshot())))
        for peer in self.peers.values():
            if peer.welcomed:
                peer.send_snapshot(text)

    def _error(self, peer, code, message, ref_seq=None):
        peer.send(encode('error', dict(code=code, message=message, ref_seq=ref_seq)))

    def _flush(self, room_changed=False):
        """Drain exactly once after every mutation and publish ordered transition bundles."""
        bundle_open = False
        for event in self.sim.drain_events():
            if isinstance(event, PhaseChanged):
                if bundle_open:
                    self._broadcast_room()
                if event.state.phase == 'lobby':
                    self._clear_readiness()
                self._broadcast(encode('phase.changed', dict(state=plain(event.state))))
                bundle_open = True
            elif isinstance(event, RolesChanged):
                self._clear_readiness()
                self._broadcast(encode('roles.changed', dict(assignments=plain(event.assignments),
                    assignment_version=event.assignment_version, epoch=event.epoch)))
                bundle_open = True
            elif isinstance(event, InputRejected):
                peer = self.peers.get(event.member_id)
                if peer:
                    self._error(peer, event.code, event.message, event.ref_seq)
        if bundle_open or room_changed:
            self._broadcast_room()
        if bundle_open:
            self._broadcast_snapshot()

    # --- connection lifecycle -------------------------------------------------
    def attach(self, socket, facts):
        member_id = facts['member_id']
        self.facts = facts
        prior = self.peers.pop(member_id, None)
        if prior:
            prior.close(4409)
            if self._required(member_id):
                self._abort('device replaced')
        peer = Peer(socket, member_id)
        self.peers[member_id] = peer
        # Reconnect restores identity only; calibration and readiness must be earned again.
        st = self.status.setdefault(member_id, dict(ready=False, permission='unknown', calibrated=False))
        st.update(ready=False, calibrated=False)
        self._sync_assignments()
        self._push_facts()
        # The new peer is not welcomed yet, so these broadcasts reach everyone else only.
        self._flush(room_changed=True)
        state = self.sim.snapshot()
        peer.send(encode('session.welcome', dict(member_id=member_id, room=self._room(), state=plain(state))))
        peer.welcomed = True
        return peer

    def membership(self, facts):
        active = {m['member_id'] for m in facts['members']}
        for mid, peer in list(self.peers.items()):
            if mid not in active:
                self.detach(peer)
                peer.close(4401)
        self.facts = facts
        self.status = {mid: st for mid, st in self.status.items() if mid in active}
        self._sync_assignments()
        self._push_facts()
        self._flush(room_changed=True)

    def detach(self, peer):
        if self.peers.get(peer.member_id) is not peer:
            return  # superseded: the replacement owns this seat now
        del self.peers[peer.member_id]
        self.cameras.pop(peer.member_id, None)
        peer.close()
        self.status[peer.member_id].update(ready=False, calibrated=False)
        self._push_facts()
        if self._required(peer.member_id) or (self._device(peer.member_id) == 'screen' and not self._screens()):
            self._abort('required device disconnected')
        self._flush(room_changed=True)

    # --- inbound ----------------------------------------------------------------
    def handle(self, peer, message):
        if self.peers.get(peer.member_id) is not peer:
            return
        kind, payload = message.type, message.payload
        if kind == 'controller.ready':
            self._ready(peer, payload)
        elif kind in ('match.start', 'match.reset', 'match.rematch'):
            if peer.member_id != self.facts['host_id']:
                return self._error(peer, 'FORBIDDEN', 'Only the host screen can do that')
            try:
                self.sim.control(kind.split('.')[1])
            except SimulationError as exc:
                self._error(peer, exc.code, exc.message)
            self._flush()
        elif kind in ('input.legs', 'input.arms'):
            self._input(peer, kind, payload)
        elif kind == 'camera.claim':
            self._camera(peer, payload)

    def _camera(self, peer, p):
        if self._device(peer.member_id) != 'screen':
            return self._error(peer, 'FORBIDDEN', 'Only screens have a camera')
        if p.team is None:
            self.cameras.pop(peer.member_id, None)
        else:
            # One camera per team: the latest claim wins.
            for mid in [mid for mid, team in self.cameras.items() if team == p.team]:
                del self.cameras[mid]
            self.cameras[peer.member_id] = p.team
        self._flush(room_changed=True)

    def _ready(self, peer, p):
        if self._device(peer.member_id) != 'phone':
            return self._error(peer, 'FORBIDDEN', 'Only phones report controller status')
        state = self.sim.snapshot()
        if p.epoch != state.epoch:
            return self._error(peer, 'STALE_EPOCH', 'Status is from an earlier phase')
        if p.assignment_version != state.assignment_version:
            return self._error(peer, 'STALE_ASSIGNMENT', 'Roles changed; recalibrate')
        if p.ready:
            if state.phase not in ('lobby', 'role_switch'):
                return self._error(peer, 'INVALID_PHASE', 'Ready is only accepted between rounds')
            if not self._assigned(peer.member_id):
                return self._error(peer, 'NOT_READY', 'This phone has no role yet')
            if p.permission != 'granted' or not p.calibrated:
                return self._error(peer, 'NOT_READY', 'Grant motion access and calibrate first')
        self.status[peer.member_id].update(ready=p.ready, permission=p.permission, calibrated=p.calibrated)
        self._push_facts()
        if not p.ready and state.phase in PLAYING and self._assigned(peer.member_id):
            self._abort('controller not ready')
        self._flush(room_changed=True)

    def _input(self, peer, kind, p):
        device = self._device(peer.member_id)
        camera_team = self.cameras.get(peer.member_id)
        if device == 'screen' and (kind != 'input.legs' or camera_team is None):
            return self._error(peer, 'FORBIDDEN', 'Only a screen whose camera claimed a team sends movement', p.seq)
        if device not in ('phone', 'screen'):
            return self._error(peer, 'FORBIDDEN', 'Only phones send gameplay input', p.seq)
        if p.seq <= peer.last_seq:
            return self._error(peer, 'OLD_SEQ', 'Input sequence must increase', p.seq)
        peer.last_seq = p.seq
        actor = peer.member_id
        if device == 'screen':
            # The camera moves whoever is this team's Legs right now; players swap spots each round.
            actor = next((a.member_id for a in self.sim.snapshot().assignments
                          if a.team == camera_team and a.role == 'legs'), None)
            if actor is None:
                return
        elif kind == 'input.legs' and self._camera_drives(actor):
            return  # this team's movement comes from the screen camera
        if kind == 'input.legs':
            command = LegsCommand(seq=p.seq, epoch=p.epoch, move=Vec2(p.move.x, p.move.z))
        else:
            command = ArmsCommand(seq=p.seq, epoch=p.epoch, aim=Vec2(p.aim.x, p.aim.z),
                action=p.action, strength=p.strength)
        self.ordinal += 1
        try:
            self.sim.apply_input(actor, command, received_ms=now_ms(), ordinal=self.ordinal)
        except SimulationError as exc:
            self._error(peer, exc.code, exc.message, p.seq)

    # --- fixed-step runner ------------------------------------------------------
    async def _run(self):
        last = monotonic()
        backlog = 0.0
        while True:
            await asyncio.sleep(TICK_S)
            now = monotonic()
            backlog += now - last
            last = now
            try:
                if backlog > OVERLOAD_S:
                    # Never skip authoritative collision steps: reset instead (plan 01).
                    log.warning('room=%s overloaded by %.0f ms', self.code, backlog * 1000)
                    backlog = 0.0
                    self._abort('server overloaded')
                    self._flush()
                    continue
                for _ in range(MAX_CATCH_UP):
                    if backlog < TICK_S:
                        break
                    backlog -= TICK_S
                    self.sim.step(now_ms())
                    self._flush()
                    self.steps += 1
                    if self.steps % SNAPSHOT_EVERY == 0 and self.sim.snapshot().phase != 'lobby':
                        self._broadcast_snapshot()
            except Exception:
                log.exception('room=%s runner step failed', self.code)

    def close(self):
        self.task.cancel()
        for peer in self.peers.values():
            peer.close()


class GameHub:
    """Process-local registry of live rooms. Rooms end when their last socket leaves."""

    def __init__(self):
        self.rooms = {}

    def attach(self, socket, facts):
        room = self.rooms.get(facts['room_code'])
        if room is None:
            room = self.rooms[facts['room_code']] = GameRoom(facts)
        return room, room.attach(socket, facts)

    def detach(self, room, peer):
        room.detach(peer)
        if not room.peers and self.rooms.get(room.code) is room:
            room.close()
            del self.rooms[room.code]

    def close(self):
        for room in self.rooms.values():
            room.close()
        self.rooms.clear()
