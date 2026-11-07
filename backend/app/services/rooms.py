"""Registration policy and transaction orchestration; repositories own SQL."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import uuid4

from app.db.models import MemberRecord, RoomRecord
from app.protocol import Registration
from app.repositories.members import MemberRepository
from app.repositories.rooms import RoomRepository

ROOM_LIMIT = 10
DEVICE_CAPACITY = 4
LOBBY_IDLE_TTL = timedelta(minutes=30)
ROOM_TTL = timedelta(hours=4)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class RoomError(Exception):
    """Expected registration rejection translated into the public REST error shape."""

    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


class Rooms:
    """Own registration decisions and transactions for one coordinator lifetime.

    Both repositories share a session, so room and member changes commit together.
    Repositories never commit independently or decide HTTP rejection behavior.
    """

    def __init__(self, sessions):
        self.sessions = sessions
        self.runtime_id = uuid4()

    def start(self):
        """End former runtime sessions while preserving their durable records.

        Run one coordinator only: startup invalidates previous memberships rather
        than attempting to recover an interrupted game.
        """
        with self.sessions.begin() as db:
            now = datetime.now(timezone.utc)
            RoomRepository(db).close_open(at=now, reason="server_restart")
            MemberRepository(db).revoke_active(at=now)

    def _expire(self, rooms: RoomRepository, now: datetime):
        rooms.close_expired(at=now, idle_before=now - LOBBY_IDLE_TTL)

    def count(self):
        """Check SQL readiness, expire stale rooms and count this runtime's open rooms."""
        with self.sessions.begin() as db:
            rooms = RoomRepository(db)
            self._expire(rooms, datetime.now(timezone.utc))
            return rooms.count_open(self.runtime_id)

    def _create_room(self, rooms: RoomRepository, now: datetime) -> RoomRecord:
        # Hold the creation lock through commit so capacity checks and code selection
        # remain valid even when multiple HTTP requests create rooms simultaneously.
        rooms.lock_creation()
        self._expire(rooms, now)
        if rooms.count_open() >= ROOM_LIMIT:
            raise RoomError(429, "SERVER_BUSY", "Room capacity reached")

        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if not rooms.code_exists(code):
                break

        room = RoomRecord(
            id=uuid4(),
            code=code,
            host_id=uuid4(),
            runtime_id=self.runtime_id,
            created_at=now,
            last_activity_at=now,
            expires_at=now + ROOM_TTL,
        )
        rooms.add(room)
        return room

    def _validate_join(self, room: RoomRecord | None, device: str, now: datetime):
        if room is None or room.closed_at or room.runtime_id != self.runtime_id:
            raise RoomError(404, "ROOM_NOT_FOUND", "Room not found")
        idle = room.phase == "lobby" and room.last_activity_at <= now - LOBBY_IDLE_TTL
        if room.expires_at <= now or idle:
            raise RoomError(404, "ROOM_NOT_FOUND", "Room expired")
        if device == "phone" and room.phase != "lobby":
            raise RoomError(409, "INVALID_PHASE", "Phones can join only in lobby")

    def register(self, name, device="screen", code=None):
        """Atomically create room+host, or validate and join a locked existing room.

        No code means creation. The context manager commits before the result
        reaches the HTTP handler; a rejected registration rolls back all writes.
        """
        now = datetime.now(timezone.utc)
        with self.sessions.begin() as db:
            rooms = RoomRepository(db)
            members = MemberRepository(db)
            if code is None:
                room = self._create_room(rooms, now)
                member_id, slot = room.host_id, 0
            else:
                room = rooms.get_by_code_for_update(code.strip().upper())
                self._validate_join(room, device, now)
                occupied = members.occupied_slots(room.id, device)
                # Lowest vacant slot preserves the initial phone assignment order.
                slot = next((i for i in range(DEVICE_CAPACITY) if i not in occupied), None)
                if slot is None:
                    raise RoomError(409, "ROOM_FULL", "Device slots are full")
                member_id = uuid4()
                rooms.touch(room, at=now)

            # Generate 32 random bytes; store only a hash of this high-entropy secret.
            token = secrets.token_urlsafe(32)
            members.add(MemberRecord(
                id=member_id,
                room_id=room.id,
                name=name,
                device=device,
                slot=slot,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                created_at=now,
            ))
            return Registration(
                room_id=str(room.id),
                room_code=room.code,
                member_id=str(member_id),
                token=token,
                ws_path=f"/ws/rooms/{room.code}",
            )
