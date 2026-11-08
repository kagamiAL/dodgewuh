// Arms aim + throw gesture. Pure functions, no Vue, so the playground and ArmsController share them.
// This only reads the player's gesture on the phone; the server (simulation) decides what a throw does.
//
// Grip: phone held like a stick at chest height, screen facing sideways (left in the right hand,
// right in the left hand), facing the TV.
//
// Aim: the phone's horizontal pointing heading (Wii-remote style), read live at the moment of the
// throw — never frozen.
//
// Throw: a "chop". The top of the phone must swing down toward the TV by at least minDropDeg from
// its highest point within the last windowMs. Measured from the motion itself, so no particular
// start pose is needed: the wind-up is the start. Raising the phone never triggers, and small
// twitches (or the jolt of a thumb press) can't cover the angle.

import type { Team, Vec2 } from '@/contracts/pending'

const DEG = Math.PI / 180

type V3 = { x: number; y: number; z: number }

/**
 * Device +y (top) and +z (screen normal) in the earth frame (x east, y north, z up).
 * W3C deviceorientation: R = Rz(alpha)·Rx(beta)·Ry(gamma) maps device → earth; these are R's columns.
 */
function deviceAxes(alpha_deg: number, beta_deg: number, gamma_deg: number): { top: V3; normal: V3 } {
  const sa = Math.sin(alpha_deg * DEG), ca = Math.cos(alpha_deg * DEG)
  const sb = Math.sin(beta_deg * DEG), cb = Math.cos(beta_deg * DEG)
  const sg = Math.sin(gamma_deg * DEG), cg = Math.cos(gamma_deg * DEG)
  return {
    top: { x: -sa * cb, y: ca * cb, z: sb },
    normal: { x: ca * sg + sa * sb * cg, y: sa * sg - ca * sb * cg, z: cb * cg },
  }
}

export function screenNormal(alpha_deg: number, beta_deg: number, gamma_deg: number): V3 {
  return deviceAxes(alpha_deg, beta_deg, gamma_deg).normal
}

/** Below this horizontal length of the screen normal (screen facing ~up/down) the heading is undefined. */
export const MIN_SIDEWAYS = 0.35

/**
 * Pointing heading in radians (clockwise from the frame's north), or null when unusable.
 * Heading of (normal × up): a chop rotates about the screen normal, so this stays put through the
 * throw while turning left/right moves it. Its fixed offset (0 or 180°, by which way the screen
 * faces) cancels against "Set forward".
 */
export function pointingHeading(alpha_deg: number, beta_deg: number, gamma_deg: number): number | null {
  const n = screenNormal(alpha_deg, beta_deg, gamma_deg)
  if (Math.hypot(n.x, n.y) < MIN_SIDEWAYS) return null
  return Math.atan2(n.y, -n.x)
}

/** Which way the screen faces. Screen left = right hand (default); screen right = left hand. */
export type ScreenSide = 'left' | 'right'

/**
 * Angle of the phone's top in the throwing plane, degrees: 90 = straight up, 0 = pointing at the
 * TV, > 90 = tilted back over the shoulder, < 0 = pointing at the floor in front. Null if unusable.
 */
export function topPitch(alpha_deg: number, beta_deg: number, gamma_deg: number, side: ScreenSide): number | null {
  const { top, normal } = deviceAxes(alpha_deg, beta_deg, gamma_deg)
  const len = Math.hypot(normal.x, normal.y)
  if (len < MIN_SIDEWAYS) return null
  // Toward the TV: normal × up for a screen facing left, the opposite for a screen facing right.
  const s = side === 'left' ? 1 : -1
  const fx = (s * normal.y) / len, fy = (-s * normal.x) / len
  return Math.atan2(top.z, top.x * fx + top.y * fy) / DEG
}

/** a − b wrapped to (−π, π]. */
export function angleDiff(a: number, b: number): number {
  let d = (a - b) % (2 * Math.PI)
  if (d > Math.PI) d -= 2 * Math.PI
  if (d <= -Math.PI) d += 2 * Math.PI
  return d
}

/**
 * Team-relative yaw → world aim. 02 requires T1 aim.z ≥ 0.2 (T2 ≤ −0.2), i.e. |yaw| ≤ ~78.5°,
 * so clamp a little inside that rather than have the server reject a wide throw.
 */
export const MAX_YAW_DEG = 75

export function yawToWorldAim(yaw_rad: number, team: Team): Vec2 {
  const y = Math.max(-MAX_YAW_DEG * DEG, Math.min(MAX_YAW_DEG * DEG, yaw_rad))
  const s = team === 1 ? 1 : -1
  return { x: Math.sin(y) * s, z: Math.cos(y) * s }
}

export interface ChopConfig {
  /** Degrees the top must drop from its recent highest point. */
  minDropDeg: number
  /** The drop must happen within this long. */
  windowMs: number
  /** Ignore motion this long after the thumb goes down (the press itself jolts the phone). */
  pressGuardMs: number
  /** Minimum time between throws. */
  cooldownMs: number
  /**
   * Strength by average chop speed (deg/s; 90° in 0.36 s = 250°/s, in 0.18 s = 500°/s):
   * at or below weakRate the weakest throw (0), at or above hardRate the hardest (1),
   * scaling smoothly in between. With `stepped`, it snaps to weak 0 / medium 0.5 / hard 1 instead
   * (medium from the midpoint rate).
   */
  weakRate: number
  hardRate: number
  stepped: boolean
}

export const DEFAULT_CHOP: ChopConfig = {
  minDropDeg: 90,
  windowMs: 500,
  pressGuardMs: 100,
  cooldownMs: 300,
  weakRate: 250, // 90° in 0.36 s or slower: weakest throw (~75% of the court)
  hardRate: 500, // 90° in 0.18 s or faster: hardest throw (clears corner to corner)
  stepped: false, // smooth scaling; true = three fixed levels
}

/** Live-tunable copy the controller reads on every sample; the /sensors tuning tab edits it. */
export const chopTuning: ChopConfig = { ...DEFAULT_CHOP }

export interface Chop {
  time_ms: number
  /** Degrees dropped from the highest point to the trigger point. */
  drop_deg: number
  /** Pitch at the highest point and at the trigger. */
  from_deg: number
  to_deg: number
  duration_ms: number
  /** Average chop speed, deg/s. */
  rate: number
  /** Rough label for display: weak / medium / hard thirds of the strength range. */
  level: ThrowLevel
  /** 0 … 1 (or exactly 0 / 0.5 / 1 when stepped). */
  strength: number
  /** Pointing heading (rad) at the trigger, or null. */
  heading: number | null
}

export type ThrowLevel = 'weak' | 'medium' | 'hard'

/** Chop speed → strength in [0,1], smooth or stepped per the config. */
export function throwStrength(rate: number, c: ChopConfig): number {
  const t = Math.max(0, Math.min(1, (rate - c.weakRate) / Math.max(1, c.hardRate - c.weakRate)))
  return c.stepped ? (t >= 1 ? 1 : t >= 0.5 ? 0.5 : 0) : t
}

export function throwLevel(strength: number): ThrowLevel {
  return strength >= 0.99 ? 'hard' : strength >= 0.33 ? 'medium' : 'weak'
}

/** Feed every new orientation sample. Returns a Chop the moment the drop reaches minDropDeg. */
export function createChopDetector(config: () => ChopConfig) {
  let buf: { t: number; p: number }[] = []
  let ignoreUntil = -Infinity
  let lastPitch: number | null = null

  function clear(): void {
    buf = []
    lastPitch = null
  }

  return {
    /** Current drop from the highest point in the window, for live display. */
    get drop(): number {
      if (!buf.length) return 0
      return Math.max(...buf.map((s) => s.p)) - buf[buf.length - 1].p
    },
    push(time_ms: number, pitch: number | null, heading: number | null): Chop | null {
      const c = config()
      if (pitch === null) {
        clear()
        return null
      }
      // Unwrap so a swing past straight-back/straight-down doesn't jump by 360°.
      let p = pitch
      if (lastPitch !== null) {
        while (p - lastPitch > 180) p -= 360
        while (p - lastPitch < -180) p += 360
      }
      lastPitch = p
      if (time_ms < ignoreUntil) {
        buf = [{ t: time_ms, p }]
        return null
      }
      buf.push({ t: time_ms, p })
      while (buf.length && time_ms - buf[0].t > c.windowMs) buf.shift()
      let top = buf[0]
      for (const s of buf) if (s.p > top.p) top = s
      const drop = top.p - p
      if (drop < c.minDropDeg) return null
      const duration_ms = Math.max(1, time_ms - top.t)
      const rate = (drop / duration_ms) * 1000
      const strength = throwStrength(rate, c)
      ignoreUntil = time_ms + c.cooldownMs
      buf = []
      return { time_ms, drop_deg: drop, from_deg: top.p, to_deg: p, duration_ms, rate, level: throwLevel(strength), strength, heading }
    },
    /** Call when the thumb goes down: forget earlier motion and ignore the press jolt. */
    press(time_ms: number): void {
      buf = []
      ignoreUntil = time_ms + config().pressGuardMs
    },
    reset(): void {
      clear()
      ignoreUntil = -Infinity
    },
  }
}

// --- Aim assist ---------------------------------------------------------------------------------
// Purely a phone-side aiming choice: it bends the aim it sends; the server still decides hits.
// Numbers mirror plans/02 / backend/simulation/constants.py.
const THROW_BASE_SPEED = 12
const THROW_SPEED_PER_STRENGTH = 8
const THROW_OFFSET = 0.65
// Ballistic flight (02 amended): released flat at THROW_HEIGHT, gravity pulls it down, and it can
// only hit before it lands. Fall time ≈ 1.12 s, so range = speed × 1.12: weak 13.5 m (~75% of
// the court), medium 18.0 m, hard 22.5 m (clears the ~21.5 m corner-to-corner worst case).
const THROW_HEIGHT = 1.5
const GROUND_HEIGHT = 0.3 // BALL_RADIUS
const GRAVITY = 1.9
export const FALL_S = Math.sqrt((2 * (THROW_HEIGHT - GROUND_HEIGHT)) / GRAVITY)

/** Ball speed for a strength in [0,1], m/s (02). */
export function throwSpeed(strength: number): number {
  return THROW_BASE_SPEED + THROW_SPEED_PER_STRENGTH * Math.max(0, Math.min(1, strength))
}

export interface AssistConfig {
  enabled: boolean
  /** Aim within this many degrees of the target gets pulled toward it. */
  coneDeg: number
  /** Within this many degrees the aim snaps fully onto the target; it fades out to coneDeg. */
  fullDeg: number
  /** Aim where a moving target will be when the ball arrives. */
  lead: boolean
}

// Light assist: at 9 m it turns throws up to ~5.5° off into hits (unassisted hits reach ~4.5°);
// 6° or more still misses. No lead. (Was 15°/8° with lead.)
export const DEFAULT_ASSIST: AssistConfig = { enabled: true, coneDeg: 7, fullDeg: 2, lead: false }

/** Live-tunable copy ArmsController reads; the /sensors Practice tab edits it. */
export const assistTuning: AssistConfig = { ...DEFAULT_ASSIST }

export interface Assist {
  /** Team-relative yaw to send (radians, before the ±MAX_YAW clamp). */
  yaw: number
  /** True when the aim was pulled onto the target. */
  locked: boolean
  /** Degrees the aim was moved. */
  pull_deg: number
}

/** Team-relative world vector → team-relative yaw (0 = team forward, + = team right). */
function localYaw(d: Vec2, team: Team): number {
  const s = team === 1 ? 1 : -1
  return Math.atan2(d.x * s, d.z * s)
}

/**
 * Pull a team-relative yaw toward the opponent (optionally leading a moving one).
 * me/target are world positions; targetVel is world m/s or null if unknown.
 */
export function assistYaw(
  yaw: number, team: Team, me: Vec2, target: Vec2, targetVel: Vec2 | null, strength: number, cfg: AssistConfig,
): Assist {
  if (!cfg.enabled) return { yaw, locked: false, pull_deg: 0 }
  const dir = yawToWorldAim(yaw, team)
  const launch = { x: me.x + dir.x * THROW_OFFSET, z: me.z + dir.z * THROW_OFFSET }
  let aimAt = target
  if (cfg.lead && targetVel && Math.hypot(targetVel.x, targetVel.z) > 0.2) {
    // Intercept: |target + v·t − launch| = speed·t, smallest positive t within the flight time.
    const speed = throwSpeed(strength)
    const rx = target.x - launch.x, rz = target.z - launch.z
    const a = targetVel.x ** 2 + targetVel.z ** 2 - speed ** 2
    const b = 2 * (rx * targetVel.x + rz * targetVel.z)
    const c = rx * rx + rz * rz
    let t: number | null = null
    if (Math.abs(a) < 1e-6) t = b < 0 ? -c / b : null
    else {
      const disc = b * b - 4 * a * c
      if (disc >= 0) {
        const roots = [(-b - Math.sqrt(disc)) / (2 * a), (-b + Math.sqrt(disc)) / (2 * a)].filter((r) => r > 0)
        t = roots.length ? Math.min(...roots) : null
      }
    }
    // Only lead to a meeting point the ball can reach before it lands.
    if (t !== null && t <= FALL_S) aimAt = { x: target.x + targetVel.x * t, z: target.z + targetVel.z * t }
  }
  // Lock if the aim is near the player OR near where they'll be; then pull to the lead point,
  // so aiming at a running player still hits.
  const bearing = localYaw({ x: aimAt.x - launch.x, z: aimAt.z - launch.z }, team)
  const now = localYaw({ x: target.x - launch.x, z: target.z - launch.z }, team)
  const diff = angleDiff(bearing, yaw)
  const off = Math.min(Math.abs(diff), Math.abs(angleDiff(now, yaw))) / DEG
  if (off > cfg.coneDeg) return { yaw, locked: false, pull_deg: 0 }
  const w = off <= cfg.fullDeg ? 1 : (cfg.coneDeg - off) / (cfg.coneDeg - cfg.fullDeg)
  return { yaw: yaw + diff * w, locked: true, pull_deg: (diff * w) / DEG }
}
