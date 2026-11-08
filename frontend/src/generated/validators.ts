// Protocol v1 Zod validators; mirrors backend/app/protocol.py and plan 03.
import { z } from 'zod';
import type { ClientMessage, ServerMessage } from './protocol';
/** Cross-field protocol rules shared with the Python model validators. */
import type { RefinementCtx } from 'zod';
function refine(name: string, value: any, ctx: RefinementCtx): void {
  const fail = (message: string) => ctx.addIssue({ code: 'custom', message });
  if (['Room', 'State', 'RolesChanged'].includes(name)) {
    const pairs = value.assignments.map((a: any) => `${a.team}:${a.role}`);
    const ids = value.assignments.map((a: any) => a.member_id);
    if (new Set(pairs).size !== pairs.length || new Set(ids).size !== ids.length) fail('Duplicate assignment');
  }
  if (name === 'State') {
    if (JSON.stringify(value.characters.map((c: any) => c.team)) !== '[1,2]' ||
        JSON.stringify(value.balls.map((b: any) => b.ball_id)) !== '["b1","b2","b3","b4","b5","b6"]') fail('Complete sorted entities required');
    if (value.phase !== 'lobby' && value.assignments.length !== 4) fail('Match requires four assignments');
    if (value.winner !== null && value.phase !== 'match_end') fail('Winner is match-end only');
  }
  if (name === 'Character' || name === 'Arms') {
    const length = Math.hypot(value.aim.x, value.aim.z);
    if (length < .99 || length > 1.01) fail('Invalid aim length');
  }
  if (name === 'Character' && value.aim.z * (value.team === 1 ? 1 : -1) < .2) fail('Invalid aim hemisphere');
  if (name === 'Ball') {
    if ((value.owner_team !== null) !== (value.mode === 'held') ||
        (value.shooter_team !== null) !== (value.mode === 'flying')) fail('Invalid ball ownership');
    if (value.mode !== 'flying' && (value.velocity.x !== 0 || value.velocity.z !== 0)) fail('Non-flying velocity must be zero');
    if (value.mode !== 'respawning' && value.respawn_in_ms !== 0) fail('Invalid respawn timer');
  }
  if (name === 'Welcome' && (JSON.stringify(value.room.assignments) !== JSON.stringify(value.state.assignments) ||
      value.room.assignment_version !== value.state.assignment_version || value.room.phase !== value.state.phase)) fail('Room/state boundary mismatch');
  if (name === 'Legs' || name === 'Arms') {
    if (value.seq < 1) fail('Input sequence starts at one');
    if (name === 'Legs' && (Math.abs(value.move.x) > 1 || Math.abs(value.move.z) > 1 || Math.hypot(value.move.x, value.move.z) > 1.001)) fail('Invalid movement');
    if (name === 'Arms' && ((value.action === 'release' && (value.strength === null || value.strength < 0 || value.strength > 1)) ||
        (value.action !== 'release' && value.strength !== null))) fail('Invalid strength');
  }
}

const defs: Record<string, z.ZodTypeAny> = {};
defs.Arms = z.lazy(() => z.object({"seq":z.number().finite().int().min(0).max(9007199254740991),"epoch":z.number().finite().int().min(0).max(9007199254740991),"aim":defs.Vec2,"action":z.union([z.literal("aim"),z.literal("press"),z.literal("release"),z.literal("cancel")]),"strength":z.union([z.number().finite(),z.null()]),"arm_pitch":z.union([z.number().finite().min(-360).max(360),z.null()]).optional()}).strict().superRefine((value, ctx) => refine("Arms", value, ctx)));
defs.CameraClaim = z.lazy(() => z.object({"team":z.union([z.union([z.literal(1),z.literal(2)]),z.null()])}).strict().superRefine((value, ctx) => refine("CameraClaim", value, ctx)));
defs.camera_claim = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("camera.claim"),"payload":defs.CameraClaim}).strict().superRefine((value, ctx) => refine("camera_claim", value, ctx)));
defs.Empty = z.lazy(() => z.object({}).strict().superRefine((value, ctx) => refine("Empty", value, ctx)));
defs.Hello = z.lazy(() => z.object({"token":z.string()}).strict().superRefine((value, ctx) => refine("Hello", value, ctx)));
defs.Legs = z.lazy(() => z.object({"seq":z.number().finite().int().min(0).max(9007199254740991),"epoch":z.number().finite().int().min(0).max(9007199254740991),"move":defs.Vec2}).strict().superRefine((value, ctx) => refine("Legs", value, ctx)));
defs.Ping = z.lazy(() => z.object({"nonce":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("Ping", value, ctx)));
defs.Ready = z.lazy(() => z.object({"epoch":z.number().finite().int().min(0).max(9007199254740991),"assignment_version":z.number().finite().int().min(0).max(9007199254740991),"ready":z.boolean(),"permission":z.union([z.literal("unknown"),z.literal("granted"),z.literal("denied"),z.literal("unsupported")]),"calibrated":z.boolean()}).strict().superRefine((value, ctx) => refine("Ready", value, ctx)));
defs.Vec2 = z.lazy(() => z.object({"x":z.number().finite(),"z":z.number().finite()}).strict().superRefine((value, ctx) => refine("Vec2", value, ctx)));
defs.controller_ready = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("controller.ready"),"payload":defs.Ready}).strict().superRefine((value, ctx) => refine("controller_ready", value, ctx)));
defs.input_arms = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("input.arms"),"payload":defs.Arms}).strict().superRefine((value, ctx) => refine("input_arms", value, ctx)));
defs.input_legs = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("input.legs"),"payload":defs.Legs}).strict().superRefine((value, ctx) => refine("input_legs", value, ctx)));
defs.match_rematch = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("match.rematch"),"payload":defs.Empty}).strict().superRefine((value, ctx) => refine("match_rematch", value, ctx)));
defs.match_reset = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("match.reset"),"payload":defs.Empty}).strict().superRefine((value, ctx) => refine("match_reset", value, ctx)));
defs.match_start = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("match.start"),"payload":defs.Empty}).strict().superRefine((value, ctx) => refine("match_start", value, ctx)));
defs.session_hello = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("session.hello"),"payload":defs.Hello}).strict().superRefine((value, ctx) => refine("session_hello", value, ctx)));
defs.session_ping = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("session.ping"),"payload":defs.Ping}).strict().superRefine((value, ctx) => refine("session_ping", value, ctx)));
defs.Assignment = z.lazy(() => z.object({"member_id":z.string().min(1).max(64),"team":z.union([z.literal(1),z.literal(2)]),"role":z.union([z.literal("arms"),z.literal("legs")])}).strict().superRefine((value, ctx) => refine("Assignment", value, ctx)));
defs.Ball = z.lazy(() => z.object({"ball_id":z.string().min(1).max(64),"mode":z.union([z.literal("ground"),z.literal("held"),z.literal("flying"),z.literal("respawning")]),"pos":defs.Vec2,"velocity":defs.Vec2,"owner_team":z.union([z.union([z.literal(1),z.literal(2)]),z.null()]),"shooter_team":z.union([z.union([z.literal(1),z.literal(2)]),z.null()]),"respawn_in_ms":z.number().finite().int().min(0).max(9007199254740991),"height":z.number().finite()}).strict().superRefine((value, ctx) => refine("Ball", value, ctx)));
defs.Character = z.lazy(() => z.object({"team":z.union([z.literal(1),z.literal(2)]),"pos":defs.Vec2,"aim":defs.Vec2,"held_ball_id":z.union([z.string().min(1).max(64),z.null()]),"arm_pitch":z.union([z.number().finite(),z.null()]).optional()}).strict().superRefine((value, ctx) => refine("Character", value, ctx)));
defs.Closed = z.lazy(() => z.object({"reason":z.union([z.literal("host_left"),z.literal("expired"),z.literal("server_shutdown")])}).strict().superRefine((value, ctx) => refine("Closed", value, ctx)));
defs.ErrorPayload = z.lazy(() => z.object({"code":z.string(),"message":z.string(),"ref_seq":z.union([z.number().finite().int().min(0).max(9007199254740991),z.null()])}).strict().superRefine((value, ctx) => refine("ErrorPayload", value, ctx)));
defs.Member = z.lazy(() => z.object({"member_id":z.string().min(1).max(64),"name":z.string().trim().min(1).max(24),"device":z.union([z.literal("screen"),z.literal("phone")]),"connected":z.boolean(),"ready":z.boolean(),"permission":z.union([z.literal("unknown"),z.literal("granted"),z.literal("denied"),z.literal("unsupported")]),"calibrated":z.boolean(),"camera_team":z.union([z.union([z.literal(1),z.literal(2)]),z.null()])}).strict().superRefine((value, ctx) => refine("Member", value, ctx)));
defs.PhaseChange = z.lazy(() => z.object({"state":defs.State}).strict().superRefine((value, ctx) => refine("PhaseChange", value, ctx)));
defs.Result = z.lazy(() => z.object({"reason":z.union([z.literal("hit"),z.literal("timeout"),z.literal("simultaneous")]),"winner":z.union([z.union([z.literal(1),z.literal(2)]),z.null()]),"hit_ball_id":z.union([z.string().min(1).max(64),z.null()]),"victim_team":z.union([z.union([z.literal(1),z.literal(2)]),z.null()])}).strict().superRefine((value, ctx) => refine("Result", value, ctx)));
defs.RolesChanged = z.lazy(() => z.object({"assignments":z.array(defs.Assignment),"assignment_version":z.number().finite().int().min(0).max(9007199254740991),"epoch":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("RolesChanged", value, ctx)));
defs.Room = z.lazy(() => z.object({"room_id":z.string().min(1).max(64),"room_code":z.string(),"host_id":z.string().min(1).max(64),"revision":z.number().finite().int().min(0).max(9007199254740991),"members":z.array(defs.Member),"assignments":z.array(defs.Assignment),"assignment_version":z.number().finite().int().min(0).max(9007199254740991),"phase":z.union([z.literal("lobby"),z.literal("countdown"),z.literal("active"),z.literal("round_end"),z.literal("role_switch"),z.literal("match_end")])}).strict().superRefine((value, ctx) => refine("Room", value, ctx)));
defs.RoomUpdate = z.lazy(() => z.object({"room":defs.Room}).strict().superRefine((value, ctx) => refine("RoomUpdate", value, ctx)));
defs.Score = z.lazy(() => z.object({"t1":z.number().finite().int().min(0).max(9007199254740991),"t2":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("Score", value, ctx)));
defs.Snapshot = z.lazy(() => z.object({"state":defs.State}).strict().superRefine((value, ctx) => refine("Snapshot", value, ctx)));
defs.State = z.lazy(() => z.object({"tick":z.number().finite().int().min(0).max(9007199254740991),"epoch":z.number().finite().int().min(0).max(9007199254740991),"round":z.number().finite().int().min(0).max(9007199254740991),"phase":z.union([z.literal("lobby"),z.literal("countdown"),z.literal("active"),z.literal("round_end"),z.literal("role_switch"),z.literal("match_end")]),"remaining_ms":z.number().finite().int().min(0).max(9007199254740991),"phase_remaining_ms":z.union([z.number().finite().int().min(0).max(9007199254740991),z.null()]),"score":defs.Score,"characters":z.array(defs.Character),"balls":z.array(defs.Ball),"assignments":z.array(defs.Assignment),"assignment_version":z.number().finite().int().min(0).max(9007199254740991),"result":z.union([defs.Result,z.null()]),"winner":z.union([z.union([z.literal(1),z.literal(2)]),z.null()])}).strict().superRefine((value, ctx) => refine("State", value, ctx)));
defs.Welcome = z.lazy(() => z.object({"member_id":z.string().min(1).max(64),"room":defs.Room,"state":defs.State}).strict().superRefine((value, ctx) => refine("Welcome", value, ctx)));
defs.error = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("error"),"payload":defs.ErrorPayload,"server_ms":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("error", value, ctx)));
defs.phase_changed = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("phase.changed"),"payload":defs.PhaseChange,"server_ms":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("phase_changed", value, ctx)));
defs.roles_changed = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("roles.changed"),"payload":defs.RolesChanged,"server_ms":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("roles_changed", value, ctx)));
defs.room_closed = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("room.closed"),"payload":defs.Closed,"server_ms":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("room_closed", value, ctx)));
defs.room_updated = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("room.updated"),"payload":defs.RoomUpdate,"server_ms":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("room_updated", value, ctx)));
defs.session_pong = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("session.pong"),"payload":defs.Ping,"server_ms":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("session_pong", value, ctx)));
defs.session_welcome = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("session.welcome"),"payload":defs.Welcome,"server_ms":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("session_welcome", value, ctx)));
defs.state_snapshot = z.lazy(() => z.object({"v":z.literal(1),"type":z.literal("state.snapshot"),"payload":defs.Snapshot,"server_ms":z.number().finite().int().min(0).max(9007199254740991)}).strict().superRefine((value, ctx) => refine("state_snapshot", value, ctx)));
export const clientSchema = z.union([defs.session_hello,defs.session_ping,defs.controller_ready,defs.match_start,defs.match_reset,defs.match_rematch,defs.input_legs,defs.input_arms,defs.camera_claim] as [z.ZodTypeAny, z.ZodTypeAny, ...z.ZodTypeAny[]]);
export const serverSchema = z.union([defs.session_welcome,defs.session_pong,defs.room_updated,defs.state_snapshot,defs.phase_changed,defs.roles_changed,defs.error,defs.room_closed] as [z.ZodTypeAny, z.ZodTypeAny, ...z.ZodTypeAny[]]);
export function validateClientMessage(value: unknown): ClientMessage { return clientSchema.parse(value) as ClientMessage; }
export function validateServerMessage(value: unknown): ServerMessage { return serverSchema.parse(value) as ServerMessage; }
