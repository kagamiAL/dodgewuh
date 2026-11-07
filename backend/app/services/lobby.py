"""Process-local lobby connectivity and baseline delivery; no SQL or gameplay rules."""
import asyncio
from time import monotonic
from fastapi import WebSocketDisconnect
from app.protocol import server_messages

BOOT = monotonic()

class LobbyHub:
    def __init__(self):
        self.sockets = {}
        self.locks = {}
        self.revisions = {}

    async def send(self, socket, event, payload):
        message = server_messages.validate_python(dict(v=1, type=event,
            server_ms=int((monotonic() - BOOT) * 1000), payload=payload))
        await asyncio.wait_for(socket.send_text(message.model_dump_json()), 2)

    def baseline(self, facts):
        code = facts['room_code']
        members = [dict(member_id=m['member_id'], name=m['name'], device=m['device'],
            connected=(code, m['member_id']) in self.sockets, ready=False,
            permission='unknown', calibrated=False) for m in facts['members']]
        phones = sorted((m for m in facts['members'] if m['device'] == 'phone'), key=lambda m: m['slot'])
        assignments = [dict(member_id=m['member_id'], team=1 + m['slot']//2,
            role='arms' if m['slot'] % 2 == 0 else 'legs') for m in phones]
        room = dict(room_id=facts['room_id'], room_code=code, host_id=facts['host_id'],
            revision=self.revisions[code], members=members, assignments=assignments,
            assignment_version=len(assignments), phase='lobby')
        # Static reset entities only. This is a development handshake baseline,
        # never a simulation and never allowed to start a match.
        state = dict(tick=0, epoch=0, round=0, phase='lobby', remaining_ms=60000,
            phase_remaining_ms=None, score=dict(t1=0,t2=0), assignments=assignments,
            assignment_version=len(assignments), result=None, winner=None,
            characters=[dict(team=t, pos=dict(x=0,z=-6 if t==1 else 6),
                aim=dict(x=0,z=1 if t==1 else -1), held_ball_id=None) for t in (1,2)],
            balls=[dict(ball_id=f'b{i+1}', mode='ground', pos=dict(x=x,z=z),
                velocity=dict(x=0,z=0), owner_team=None, shooter_team=None,
                respawn_in_ms=0) for i,(x,z) in enumerate(((-2,-.6),(2,-.6),(-2,.6),(2,.6)))])
        return room, state

    async def broadcast(self, code, room):
        # Bounded send time keeps a slow browser from blocking a lobby forever.
        peers = [s for (c, _), s in self.sockets.items() if c == code]
        async def deliver(s):
            try:
                await self.send(s, 'room.updated', dict(room=room))
            except (TimeoutError, RuntimeError, WebSocketDisconnect):
                await s.close(code=4400)
        await asyncio.gather(*(deliver(s) for s in peers), return_exceptions=True)
