"""Strict protocol v1 models; plan 03 is authoritative."""
import json
import math
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, model_validator, TypeAdapter, create_model

def numeric(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError('number required')
    return v

Fin = Annotated[float, BeforeValidator(numeric), Field(allow_inf_nan=False)]
UInt = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
ID = Annotated[str, Field(min_length=1, max_length=64)]
Name = Annotated[str, BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v), Field(min_length=1, max_length=24)]
Team = Literal[1, 2]
Role = Literal['arms', 'legs']
Device = Literal['screen', 'phone', 'spectator']
Phase = Literal['lobby','countdown','active','round_end','role_switch','match_end']
Permission = Literal['unknown','granted','denied','unsupported']

def validate_assignments(assignments):
    pairs = [(a.team, a.role) for a in assignments]
    ids = [a.member_id for a in assignments]
    if len(pairs) != len(set(pairs)) or len(ids) != len(set(ids)):
        raise ValueError('Duplicate assignment')


def validate_aim(aim):
    if not .99 <= math.hypot(aim.x, aim.z) <= 1.01:
        raise ValueError('Invalid aim length')




class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)

    @model_validator(mode='before')
    @classmethod
    def literal_numbers(cls, value):
        if isinstance(value, dict):
            for field in ('team', 'owner_team', 'shooter_team', 'victim_team', 'winner', 'v'):
                if field in value and value[field] is not None and type(value[field]) is not int:
                    raise ValueError('Integer literal required')
        return value



class Vec2(Model):
    x: Fin
    z: Fin


class CreateRoom(Model):
    name: Name


class JoinRoom(CreateRoom):
    device: Device


class Registration(Model):
    room_id: ID
    room_code: str
    member_id: ID
    token: str
    ws_path: str


class Health(Model):
    status: Literal['ok'] = 'ok'
    build: str
    rooms: UInt


class RestError(Model):
    code: str
    message: str


class Assignment(Model):
    member_id: ID
    team: Team
    role: Role


class Member(Model):
    member_id: ID
    name: Name
    device: Device
    connected: bool
    ready: bool
    permission: Permission
    calibrated: bool
    camera_team: Team | None  # screens only: whose Legs this screen's camera drives


class Room(Model):
    room_id: ID
    room_code: str
    host_id: ID
    revision: UInt
    members: list[Member]
    assignments: list[Assignment]
    assignment_version: UInt
    phase: Phase

    @model_validator(mode='after')
    def unique_assignments(self):
        validate_assignments(self.assignments)
        return self



class Character(Model):
    team: Team
    pos: Vec2
    aim: Vec2
    held_ball_id: ID | None
    # Cosmetic: the Arms phone's latest throwing-arm angle (degrees; 90 = up, >90 = back over the
    # shoulder, 0 = toward the opponent). Drives the throw animation only; never gameplay.
    arm_pitch: Fin | None = None

    @model_validator(mode='after')
    def valid_aim(self):
        validate_aim(self.aim)
        if self.aim.z * (1 if self.team == 1 else -1) < .2:
            raise ValueError('Invalid aim hemisphere')
        return self



class Ball(Model):
    ball_id: ID
    mode: Literal['ground','held','flying','respawning']
    pos: Vec2
    velocity: Vec2
    owner_team: Team | None
    shooter_team: Team | None
    respawn_in_ms: UInt
    height: Fin

    @model_validator(mode='after')
    def valid_ownership(self):
        if (self.owner_team is not None) != (self.mode == 'held'):
            raise ValueError('Only held balls have owners')
        if (self.shooter_team is not None) != (self.mode == 'flying'):
            raise ValueError('Only flying balls have shooters')
        if self.mode != 'flying' and (self.velocity.x != 0 or self.velocity.z != 0):
            raise ValueError('Non-flying velocity must be zero')
        if self.mode != 'respawning' and self.respawn_in_ms != 0:
            raise ValueError('Invalid respawn timer')
        return self



class Result(Model):
    reason: Literal['hit','timeout','simultaneous']
    winner: Team | None
    hit_ball_id: ID | None
    victim_team: Team | None


class Score(Model):
    t1: UInt
    t2: UInt


class Dodge(Model):
    """A camera dodge in progress (slow motion): `team` is the victim of `ball_id`."""
    ball_id: ID
    team: Team
    outcome: Literal['pending','dodged','hit']


class State(Model):
    tick: UInt
    epoch: UInt
    round: UInt
    phase: Phase
    remaining_ms: UInt
    phase_remaining_ms: UInt | None
    score: Score
    characters: list[Character]
    balls: list[Ball]
    assignments: list[Assignment]
    assignment_version: UInt
    result: Result | None
    winner: Team | None
    # Non-null only while a camera dodge runs; the room is in slow motion meanwhile.
    dodge: Dodge | None = None

    @model_validator(mode='after')
    def complete_state(self):
        validate_assignments(self.assignments)
        if [c.team for c in self.characters] != [1, 2]:
            raise ValueError('Two characters sorted by team required')
        if [b.ball_id for b in self.balls] != ['b1', 'b2', 'b3', 'b4', 'b5', 'b6']:
            raise ValueError('Six balls sorted by ID required')
        if self.phase != 'lobby' and len(self.assignments) != 4:
            raise ValueError('Match requires four assignments')
        if self.winner is not None and self.phase != 'match_end':
            raise ValueError('Winner is match-end only')
        return self



class Hello(Model):
    token: str


class Ping(Model):
    nonce: UInt


class Ready(Model):
    epoch: UInt
    assignment_version: UInt
    ready: bool
    permission: Permission
    calibrated: bool


class Empty(Model):
    pass


class CameraClaim(Model):
    """A screen's camera drives this team's Legs (null releases it)."""
    team: Team | None


class DodgeResult(Model):
    """The victim's camera screen: did the Legs player get out of the overlaid ball?"""
    epoch: UInt
    ball_id: ID
    dodged: bool


class Legs(Model):
    seq: UInt
    epoch: UInt
    move: Vec2

    @model_validator(mode='after')
    def valid_movement(self):
        if self.seq < 1:
            raise ValueError('Input sequence starts at one')
        if abs(self.move.x) > 1 or abs(self.move.z) > 1 or math.hypot(self.move.x, self.move.z) > 1.001:
            raise ValueError('Invalid movement vector')
        return self



class Arms(Model):
    seq: UInt
    epoch: UInt
    aim: Vec2
    action: Literal['aim','press','release','cancel']
    strength: Fin | None
    # Optional, cosmetic: throwing-arm angle in degrees for the screen's throw animation.
    arm_pitch: Fin | None = None

    @model_validator(mode='after')
    def valid_throw(self):
        validate_aim(self.aim)
        if self.arm_pitch is not None and not -360 <= self.arm_pitch <= 360:
            raise ValueError('arm_pitch must be within [-360, 360] degrees')
        if self.seq < 1:
            raise ValueError('Input sequence starts at one')
        if self.action == 'release':
            if self.strength is None or not 0 <= self.strength <= 1:
                raise ValueError('Release requires bounded strength')
        elif self.strength is not None:
            raise ValueError('Strength is release-only')
        return self



class Welcome(Model):
    member_id: ID
    room: Room
    state: State

    @model_validator(mode='after')
    def consistent_baseline(self):
        if (self.room.assignments != self.state.assignments
                or self.room.assignment_version != self.state.assignment_version
                or self.room.phase != self.state.phase):
            raise ValueError('Room/state boundary mismatch')
        return self



class RoomUpdate(Model):
    room: Room


class Snapshot(Model):
    state: State


class PhaseChange(Snapshot):
    pass


class RolesChanged(Model):
    assignments: list[Assignment]
    assignment_version: UInt
    epoch: UInt

    @model_validator(mode='after')
    def unique_assignments(self):
        validate_assignments(self.assignments)
        return self



class ErrorPayload(Model):
    code: str
    message: str
    ref_seq: UInt | None


class Closed(Model):
    reason: Literal['host_left','expired','server_shutdown']

# One registry supplies decoding and schema export; no untyped event payloads.

CLIENT_PAYLOADS = {
    'session.hello': Hello, 'session.ping': Ping, 'controller.ready': Ready,
    'match.start': Empty, 'match.reset': Empty, 'match.rematch': Empty,
    'input.legs': Legs, 'input.arms': Arms, 'camera.claim': CameraClaim, 'team.choose': CameraClaim,
    'dodge.result': DodgeResult,
}
SERVER_PAYLOADS = {
    'session.welcome': Welcome, 'session.pong': Ping, 'room.updated': RoomUpdate,
    'state.snapshot': Snapshot, 'phase.changed': PhaseChange,
    'roles.changed': RolesChanged, 'error': ErrorPayload, 'room.closed': Closed,
}


def envelopes(registry, server=False):
    models = []
    for event, payload in registry.items():
        fields = dict(v=(Literal[1], ...), type=(Literal[event], ...), payload=(payload, ...))
        if server:
            fields['server_ms'] = (UInt, ...)
        models.append(create_model(event.replace('.', '_'), __base__=Model, **fields))
    return TypeAdapter(Annotated[Union[tuple(models)], Field(discriminator='type')])


client_messages = envelopes(CLIENT_PAYLOADS)
server_messages = envelopes(SERVER_PAYLOADS, True)


def decode_client(raw: str):
    def reject(value):
        raise ValueError('Nonfinite JSON number')
    data = json.loads(raw, parse_constant=reject)
    if not isinstance(data, dict):
        raise ValueError('Message object required')
    # Literal[1] otherwise accepts True and 1.0 in Python.
    if type(data.get('v')) is not int:
        raise ValueError('Integer protocol version required')
    message = client_messages.validate_python(data)
    return message
