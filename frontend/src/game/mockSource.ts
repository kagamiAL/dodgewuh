// Development-only snapshot feed (plans/04: /screen?mock=1).
//
// Replays a scripted rally as full ServerMessages at 20 Hz through the same handler
// the live Transport will feed. It is a recording, not a simulation: positions are
// keyframed by time, no rules are evaluated and nothing reacts to input.
//
// Loop (seconds): countdown 0–3, active 3–14 (both teams fetch a ball, retreat,
// throw and dodge; thrown balls leave the court and respawn), then a host reset to
// lobby 14–15, then a 1.5 s silent gap to exercise stale-stream handling.

import type { Room, ServerMessage } from '@/contracts/pending'
import type { Ball, Character, Phase, State, Team, Vec2 } from './state'

const SNAPSHOT_MS = 50 // 20 Hz, per 03
const TICKS_PER_SNAPSHOT = 3 // 60 Hz simulation
const THROW_SPEED = 11 // 8 + 6 × fixed strength 0.5 (02)
const RESPAWN_S = 1
const LOOP_S = 16.5

const BALL_SPAWNS: Record<string, Vec2> = {
  b1: { x: -2, z: -0.6 },
  b2: { x: 2, z: -0.6 },
  b3: { x: -2, z: 0.6 },
  b4: { x: 2, z: 0.6 },
}
const FORWARD: Record<Team, Vec2> = { 1: { x: 0, z: 1 }, 2: { x: 0, z: -1 } }

const ASSIGNMENTS = [
  { member_id: 'p1', team: 1 as const, role: 'arms' as const },
  { member_id: 'p2', team: 1 as const, role: 'legs' as const },
  { member_id: 'p3', team: 2 as const, role: 'arms' as const },
  { member_id: 'p4', team: 2 as const, role: 'legs' as const },
]

const ROOM: Room = {
  room_id: 'r-mock',
  room_code: 'MOCK23',
  host_id: 's1',
  revision: 1,
  members: [
    { member_id: 's1', name: 'Mock screen', device: 'screen', connected: true, ready: false, permission: 'unknown', calibrated: false },
    ...ASSIGNMENTS.map((a) => ({
      member_id: a.member_id, name: a.member_id.toUpperCase(), device: 'phone' as const,
      connected: true, ready: true, permission: 'granted' as const, calibrated: true,
    })),
  ],
  assignments: ASSIGNMENTS,
  assignment_version: 1,
  phase: 'active',
}

// ---- keyframes ------------------------------------------------------------

type Key = [t: number, x: number, z: number]

/** Piecewise-linear position over time with ease-in-out between keys. */
function along(keys: Key[], t: number): Vec2 {
  if (t <= keys[0][0]) return { x: keys[0][1], z: keys[0][2] }
  for (let i = 1; i < keys.length; i++) {
    const [t1, x1, z1] = keys[i]
    if (t <= t1) {
      const [t0, x0, z0] = keys[i - 1]
      const u = (t - t0) / (t1 - t0)
      const e = u * u * (3 - 2 * u)
      return { x: x0 + (x1 - x0) * e, z: z0 + (z1 - z0) * e }
    }
  }
  const last = keys[keys.length - 1]
  return { x: last[1], z: last[2] }
}

// Active-phase time (s since active start). Team 1 fetches b2, Team 2 fetches b3.
const T1_PATH: Key[] = [[0, 0, -6], [2.5, 1.9, -1.7], [3.2, 1.9, -1.7], [5, 1, -4.5], [6.2, 1, -4.5], [6.8, -1.6, -4.3], [9, -0.5, -5], [11, 0, -6]]
const T2_PATH: Key[] = [[0, 0, 6], [2.8, -1.9, 1.7], [3.4, -1.9, 1.7], [5.2, -1, 4.5], [5.6, -1, 4.5], [6.1, 1.6, 4.6], [8, 0.5, 5], [11, 0, 6]]
const T1_GRAB = 3.0
const T2_GRAB = 3.2
const T1_THROW = 5.5 // at T2's position before the dodge -> miss
const T2_THROW = 6.6 // at T1's position before the dodge -> miss

function aimToward(from: Vec2, to: Vec2): Vec2 {
  const dx = to.x - from.x
  const dz = to.z - from.z
  const len = Math.hypot(dx, dz) || 1
  return { x: dx / len, z: dz / len }
}

/** Arms player's aim: forward with a slow sweep, locked on target just before throwing. */
function aimFor(team: Team, t: number, self: Vec2, target: Vec2, throwAt: number): Vec2 {
  if (t > throwAt - 0.8 && t <= throwAt) return aimToward(self, target)
  const yaw = Math.sin(t * 1.3 + team) * 0.5
  const f = FORWARD[team]
  return { x: Math.sin(yaw) * f.z, z: Math.cos(yaw) * f.z }
}

interface ThrowPlan { ball: string; team: Team; grabAt: number; throwAt: number; path: Key[]; targetPath: Key[] }
const THROWS: ThrowPlan[] = [
  { ball: 'b2', team: 1, grabAt: T1_GRAB, throwAt: T1_THROW, path: T1_PATH, targetPath: T2_PATH },
  { ball: 'b3', team: 2, grabAt: T2_GRAB, throwAt: T2_THROW, path: T2_PATH, targetPath: T1_PATH },
]

function insideCourt(p: Vec2): boolean {
  return Math.abs(p.x) <= 6 && Math.abs(p.z) <= 9
}

function ballAt(id: string, t: number | null): Ball {
  const ground: Ball = {
    ball_id: id, mode: 'ground', pos: BALL_SPAWNS[id], velocity: { x: 0, z: 0 },
    owner_team: null, shooter_team: null, respawn_in_ms: 0,
  }
  const plan = THROWS.find((p) => p.ball === id)
  if (!plan || t === null || t < plan.grabAt) return ground

  const self = along(plan.path, Math.min(t, plan.throwAt))
  if (t < plan.throwAt) {
    return { ...ground, mode: 'held', pos: self, owner_team: plan.team }
  }

  const aim = aimToward(self, along(plan.targetPath, plan.throwAt))
  const start = { x: self.x + aim.x * 0.65, z: self.z + aim.z * 0.65 }
  const velocity = { x: aim.x * THROW_SPEED, z: aim.z * THROW_SPEED }
  // Find when the ball leaves the court (or the 2 s lifetime ends).
  let exit = 2
  for (let s = 0; s <= 2; s += 0.01) {
    if (!insideCourt({ x: start.x + velocity.x * s, z: start.z + velocity.z * s })) { exit = s; break }
  }
  const since = t - plan.throwAt
  if (since < exit) {
    return {
      ...ground, mode: 'flying', velocity, shooter_team: plan.team,
      pos: { x: start.x + velocity.x * since, z: start.z + velocity.z * since },
    }
  }
  if (since < exit + RESPAWN_S) {
    return { ...ground, mode: 'respawning', respawn_in_ms: Math.ceil((exit + RESPAWN_S - since) * 1000) }
  }
  return ground
}

// ---- state assembly -------------------------------------------------------

interface Frame { phase: Phase; active: number | null; phaseRemainingMs: number | null; silent: boolean }

function frameAt(loopT: number): Frame {
  if (loopT < 3) return { phase: 'countdown', active: null, phaseRemainingMs: Math.ceil((3 - loopT) * 1000), silent: false }
  if (loopT < 14) return { phase: 'active', active: loopT - 3, phaseRemainingMs: null, silent: false }
  if (loopT < 15) return { phase: 'lobby', active: null, phaseRemainingMs: null, silent: false }
  return { phase: 'lobby', active: null, phaseRemainingMs: null, silent: true }
}

function buildState(frame: Frame, tick: number, epoch: number, round: number): State {
  const t = frame.active
  const characters: Character[] = ([1, 2] as const).map((team) => {
    const plan = THROWS.find((p) => p.team === team)!
    const pos = t === null ? (team === 1 ? { x: 0, z: -6 } : { x: 0, z: 6 }) : along(plan.path, t)
    const aim = t === null ? FORWARD[team] : aimFor(team, t, pos, along(plan.targetPath, t), plan.throwAt)
    const held = t !== null && t >= plan.grabAt && t < plan.throwAt ? plan.ball : null
    return { team, pos, aim, held_ball_id: held }
  })
  return {
    tick,
    epoch,
    round,
    phase: frame.phase,
    remaining_ms: t === null ? 60000 : Math.max(0, Math.ceil((60 - t) * 1000)),
    phase_remaining_ms: frame.phaseRemainingMs,
    score: { t1: 0, t2: 0 },
    characters,
    balls: Object.keys(BALL_SPAWNS).map((id) => ballAt(id, t)),
    assignments: ASSIGNMENTS,
    assignment_version: 1,
    result: null,
    winner: null,
  }
}

/**
 * Starts the scripted feed. Emits session.welcome, then phase.changed at each phase
 * boundary and state.snapshot otherwise. Returns a stop function.
 */
export function startMockSource(handler: (msg: ServerMessage) => void): () => void {
  const startedAt = performance.now()
  let tick = 0
  let epoch = 0
  let lastPhase: Phase | null = null
  let loopIndex = -1

  const serverMs = () => Math.round(performance.now() - startedAt)

  handler({
    v: 1, type: 'session.welcome', server_ms: 0,
    payload: { member_id: 's1', room: ROOM, state: buildState(frameAt(0), 0, 0, 1) },
  })

  const timer = setInterval(() => {
    const elapsed = (performance.now() - startedAt) / 1000
    const loop = Math.floor(elapsed / LOOP_S)
    const frame = frameAt(elapsed - loop * LOOP_S)
    tick += TICKS_PER_SNAPSHOT
    if (frame.silent) return

    // Every phase change (including the reset to lobby and each new loop) bumps epoch.
    const phaseChanged = frame.phase !== lastPhase || loop !== loopIndex
    if (phaseChanged) epoch += 1
    lastPhase = frame.phase
    loopIndex = loop

    const state = buildState(frame, tick, epoch, loop + 1)
    handler(
      phaseChanged
        ? { v: 1, type: 'phase.changed', server_ms: serverMs(), payload: { state } }
        : { v: 1, type: 'state.snapshot', server_ms: serverMs(), payload: { state } },
    )
  }, SNAPSHOT_MS)

  return () => clearInterval(timer)
}
