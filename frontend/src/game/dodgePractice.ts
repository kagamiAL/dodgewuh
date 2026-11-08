// Camera dodge practice feed (/dodge): no backend, one screen with a camera.
//
// Team 1 throws at you (Team 2's Legs, standing still) over and over. Each throw starts a
// dodge exactly as the server would (backend/simulation/engine.py "camera dodge"): slow motion,
// you are frozen, the ball parks at you until your camera's verdict, a dodged ball passes through
// and a missed dodge (or no verdict in time) is a hit. Turn your back and there is no dodge. It is a small mirror of those rules for
// practice only; the server stays the authority. Snapshots go through session.apply like live.

import type { Room, ServerMessage } from '@/contracts/pending'
import { BALL_RADIUS, COURT_HALF_DEPTH, COURT_HALF_WIDTH, SLOWMO_FACTOR } from './constants'
import type { Ball, Dodge, State, Vec2 } from './state'

// Mirrored from backend/simulation/constants.py.
const DT = 1 / 60
const THROW_SPEED = 15.5 // medium throw: 12 + 7 × 0.5
const THROW_HEIGHT = 1.5
const THROW_OFFSET = 0.65
const GRAVITY = 1.9
const COMBINED_RADIUS = 0.75
const DODGE_LEAD_TICKS = 45
const DODGE_VERDICT_TIMEOUT_TICKS = 12
const DODGE_SLOWMO_TICKS = 45
const DODGE_BACK_DOT = 0.7071 // a ball within 45° of straight into your back: no dodge

const SNAPSHOT_MS = 50
const AIM_S = 1.5 // Team 1 holds and aims this long before each throw
const REST_S = 2 // pause after a throw is settled

// Mirrored from backend/simulation/constants.py BALL_SPAWNS.
const SPAWNS: Record<string, Vec2> = {
  b1: { x: -3, z: -0.6 }, b2: { x: 0, z: -0.6 }, b3: { x: 3, z: -0.6 },
  b4: { x: -3, z: 0.6 }, b5: { x: 0, z: 0.6 }, b6: { x: 3, z: 0.6 },
}
const outOfCourt = (p: Vec2) => Math.abs(p.x) > COURT_HALF_WIDTH || Math.abs(p.z) > COURT_HALF_DEPTH
const YOU: Vec2 = { x: 0, z: 6 }

const ASSIGNMENTS = [
  { member_id: 'p1', team: 1 as const, role: 'arms' as const },
  { member_id: 'p2', team: 1 as const, role: 'legs' as const },
  { member_id: 'p3', team: 2 as const, role: 'arms' as const },
  { member_id: 'p4', team: 2 as const, role: 'legs' as const },
]
const ROOM: Room = {
  room_id: 'r-practice', room_code: 'DODGE1', host_id: 's1', revision: 1,
  members: [{ member_id: 's1', name: 'Practice', device: 'screen', connected: true, ready: false, permission: 'unknown', calibrated: false, camera_team: 2 }],
  assignments: ASSIGNMENTS, assignment_version: 1, phase: 'active',
}

export interface PracticeTally { dodged: number; hit: number }

export interface DodgePractice {
  /** The camera's verdict for the pending dodge (CameraLegs' dodge-result). */
  verdict(ballId: string, dodged: boolean): void
  /** Which way the camera sees you face (world, unit), or null if unknown. */
  setFacing(dir: Vec2 | null): void
  stop(): void
}

export function startDodgePractice(handler: (msg: ServerMessage) => void, onTally: (t: PracticeTally) => void): DodgePractice {
  const tally: PracticeTally = { dodged: 0, hit: 0 }
  let tick = 0
  let realTicks = 0
  let thrower: Vec2 = { x: 0, z: -6 }
  // The thrown ball: 'held' while aiming, then 'flying'; null between throws.
  let ball: { mode: 'held' | 'flying'; pos: Vec2; vel: Vec2; height: number; vv: number } | null = null
  let dodge: (Dodge & { ticks: number }) | null = null
  let dodged = false
  let wait = AIM_S // seconds of real time until the next scripted action
  let lastResult: 'hit' | null = null
  let facing: Vec2 | null = null

  const aim = (): Vec2 => {
    const dx = YOU.x - thrower.x
    const dz = YOU.z - thrower.z
    const len = Math.hypot(dx, dz)
    return { x: dx / len, z: dz / len }
  }

  function settle(outcome: 'dodged' | 'hit' | 'miss'): void {
    if (outcome === 'dodged') tally.dodged += 1
    if (outcome === 'hit') tally.hit += 1
    onTally({ ...tally })
    lastResult = outcome === 'hit' ? 'hit' : null
    ball = null
    dodge = null
    dodged = false
    wait = REST_S
  }

  /** Thrown at your back: the ball travels within 45° of the way you face. */
  function atBack(b: NonNullable<typeof ball>): boolean {
    if (!facing || (!facing.x && !facing.z)) return false
    const speed = Math.hypot(b.vel.x, b.vel.z) || 1
    return (b.vel.x * facing.x + b.vel.z * facing.z) / speed > DODGE_BACK_DOT
  }

  /** Ticks until the flying ball reaches you standing still, within the dodge lead. */
  function ticksToContact(b: NonNullable<typeof ball>): number | null {
    let { pos, height, vv } = b
    for (let n = 0; n < DODGE_LEAD_TICKS; n++) {
      if (Math.hypot(pos.x - YOU.x, pos.z - YOU.z) <= COMBINED_RADIUS) return n
      if (height <= BALL_RADIUS || outOfCourt(pos)) return null
      pos = { x: pos.x + b.vel.x * DT, z: pos.z + b.vel.z * DT }
      height += vv * DT - 0.5 * GRAVITY * DT * DT
      vv -= GRAVITY * DT
    }
    return null
  }

  /** One simulation tick (60 Hz, or every SLOWMO_FACTOR-th real tick in slow motion). */
  function step(): void {
    tick += 1
    if (!ball) {
      wait -= DT
      if (wait <= 0) {
        lastResult = null
        thrower = { x: Math.round((Math.random() * 4 - 2) * 10) / 10, z: -6 }
        ball = { mode: 'held', pos: thrower, vel: { x: 0, z: 0 }, height: THROW_HEIGHT, vv: 0 }
        wait = AIM_S
      }
      return
    }
    if (ball.mode === 'held') {
      wait -= DT
      if (wait <= 0) {
        const a = aim()
        ball = {
          mode: 'flying', pos: { x: thrower.x + a.x * THROW_OFFSET, z: thrower.z + a.z * THROW_OFFSET },
          vel: { x: a.x * THROW_SPEED, z: a.z * THROW_SPEED }, height: THROW_HEIGHT, vv: 0,
        }
      }
      return
    }

    if (!dodge && !dodged && !atBack(ball) && ticksToContact(ball) !== null) dodge = { ball_id: 'b1', team: 2, outcome: 'pending', ticks: 0 }

    const next = { x: ball.pos.x + ball.vel.x * DT, z: ball.pos.z + ball.vel.z * DT }
    const contact = !dodged && Math.hypot(next.x - YOU.x, next.z - YOU.z) <= COMBINED_RADIUS
    if (contact && dodge?.outcome === 'pending') {
      // Parked short of you until the camera decides.
    } else if (contact) {
      return settle('hit')
    } else {
      ball.pos = next
      ball.height += ball.vv * DT - 0.5 * GRAVITY * DT * DT
      ball.vv -= GRAVITY * DT
      if (ball.height <= BALL_RADIUS || outOfCourt(next)) {
        return settle(dodged ? 'dodged' : 'miss')
      }
    }

    if (dodge) {
      dodge.ticks += 1
      if (dodge.outcome === 'pending') {
        if (dodge.ticks >= DODGE_VERDICT_TIMEOUT_TICKS) dodge.outcome = 'hit'
      } else if (dodge.ticks >= DODGE_SLOWMO_TICKS) {
        dodge = null
      }
    }
  }

  function state(): State {
    const balls: Ball[] = Object.keys(SPAWNS).map((id) => {
      const ground: Ball = {
        ball_id: id, mode: 'ground', pos: SPAWNS[id], velocity: { x: 0, z: 0 },
        owner_team: null, shooter_team: null, respawn_in_ms: 0, height: BALL_RADIUS,
      }
      if (id !== 'b1' || !ball) return ground
      if (ball.mode === 'held') return { ...ground, mode: 'held', pos: thrower, owner_team: 1, height: THROW_HEIGHT }
      return { ...ground, mode: 'flying', pos: ball.pos, velocity: ball.vel, shooter_team: 1, height: ball.height }
    })
    return {
      tick, epoch: 1, round: 1, phase: 'active', remaining_ms: 60000, phase_remaining_ms: null,
      score: { t1: tally.hit, t2: tally.dodged },
      characters: [
        { team: 1, pos: thrower, aim: aim(), held_ball_id: ball?.mode === 'held' ? 'b1' : null },
        { team: 2, pos: YOU, aim: { x: 0, z: -1 }, held_ball_id: null },
      ],
      balls, assignments: ASSIGNMENTS, assignment_version: 1,
      result: lastResult ? { reason: 'hit', winner: 1, hit_ball_id: 'b1', victim_team: 2 } : null,
      winner: null,
      dodge: dodge ? { ball_id: dodge.ball_id, team: dodge.team, outcome: dodge.outcome } : null,
    }
  }

  handler({ v: 1, type: 'session.welcome', server_ms: 0, payload: { member_id: 's1', room: ROOM, state: state() } })
  const startedAt = performance.now()
  const stepTimer = setInterval(() => {
    realTicks += 1
    if (dodge && realTicks % SLOWMO_FACTOR) return
    step()
  }, 1000 / 60)
  const sendTimer = setInterval(() => {
    handler({ v: 1, type: 'state.snapshot', server_ms: Math.round(performance.now() - startedAt), payload: { state: state() } })
  }, SNAPSHOT_MS)

  return {
    verdict(ballId, wasDodged) {
      if (!dodge || dodge.outcome !== 'pending' || dodge.ball_id !== ballId) return
      dodge.outcome = wasDodged ? 'dodged' : 'hit'
      dodged = wasDodged
    },
    setFacing(dir) {
      facing = dir
    },
    stop() {
      clearInterval(stepTimer)
      clearInterval(sendTimer)
    },
  }
}
