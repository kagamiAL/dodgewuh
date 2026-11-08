// Arms aim + throw detection. Pure functions, no Vue, so the playground and ArmsController share them.
//
// Aim is the phone's horizontal pointing heading (Wii-remote style), read live at the moment of the
// throw — never frozen. Throw is a gyro-magnitude spike (same idea as Aircade's SwingDetector:
// threshold, hysteresis re-arm, cooldown), plus peak tracking so strength and aim come from the
// fastest point of the flick.

import type { Team, Vec2 } from '@/contracts/pending'

const DEG = Math.PI / 180

/**
 * Screen normal (device +z) in the earth frame (x east, y north, z up).
 * W3C deviceorientation: R = Rz(alpha)·Rx(beta)·Ry(gamma) maps device → earth; this is R's third column.
 */
export function screenNormal(alpha_deg: number, beta_deg: number, gamma_deg: number): { x: number; y: number; z: number } {
  const sa = Math.sin(alpha_deg * DEG), ca = Math.cos(alpha_deg * DEG)
  const sb = Math.sin(beta_deg * DEG), cb = Math.cos(beta_deg * DEG)
  const sg = Math.sin(gamma_deg * DEG), cg = Math.cos(gamma_deg * DEG)
  return { x: ca * sg + sa * sb * cg, y: sa * sg - ca * sb * cg, z: cb * cg }
}

/** Below this horizontal length of the screen normal (screen facing ~up/down) the heading is undefined. */
export const MIN_SIDEWAYS = 0.35

/**
 * Pointing heading in radians (clockwise from the frame's north), or null when unusable.
 *
 * Grip: phone on its side, screen facing left (or right), top pointing at the TV — like a remote
 * held in a handshake grip. A wrist/forearm flick in that grip rotates about the screen normal, so
 * the normal stays put through the throw while turning left/right swings it horizontally. Heading
 * is the horizontal perpendicular of the normal (normal × up). Its fixed offset from where the top
 * points (±90°, depending on which way the screen faces) cancels out against "Set forward".
 */
export function pointingHeading(alpha_deg: number, beta_deg: number, gamma_deg: number): number | null {
  const n = screenNormal(alpha_deg, beta_deg, gamma_deg)
  if (Math.hypot(n.x, n.y) < MIN_SIDEWAYS) return null
  // normal × up = (n.y, −n.x, 0)
  return Math.atan2(n.y, -n.x)
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

/** Gyro magnitude in deg/s, or null. */
export function rotationSpeed(r: { alpha: number; beta: number; gamma: number } | null): number | null {
  return r ? Math.hypot(r.alpha, r.beta, r.gamma) : null
}

export interface SwingConfig {
  /** deg/s that starts a swing. Aircade used 3 rad/s ≈ 172°/s. */
  threshold: number
  /** Swing ends once speed falls below threshold × this (also the re-arm level). */
  rearmRatio: number
  /** Maximum swing window after the threshold crossing. */
  maxSwingMs: number
  /** Minimum time between swings. */
  cooldownMs: number
  /** deg/s that maps to strength 1. */
  fullStrengthRate: number
}

export const DEFAULT_SWING: SwingConfig = {
  threshold: 200,
  rearmRatio: 0.55,
  maxSwingMs: 200,
  cooldownMs: 300,
  fullStrengthRate: 900,
}

export interface Swing {
  start_ms: number
  peak_ms: number
  end_ms: number
  peak_rate: number
  strength: number
  /** Heading (rad) at the threshold crossing, at the peak, and at the end of the swing (null if unusable). */
  heading_start: number | null
  heading_peak: number | null
  heading_end: number | null
}

/**
 * Feed every sample (time, gyro speed, current heading). Returns a Swing once, when the swing
 * finishes (speed drops below the re-arm level or the window closes), so strength/aim use the peak.
 */
export function createSwingDetector(config: () => SwingConfig) {
  let armed = true
  let lastSwingMs = -Infinity
  let current: Omit<Swing, 'end_ms' | 'heading_end' | 'strength'> | null = null

  function finish(time_ms: number, heading: number | null): Swing {
    const c = config()
    const cur = current!
    current = null
    const strength = Math.max(0, Math.min(1, (cur.peak_rate - c.threshold) / (c.fullStrengthRate - c.threshold)))
    return { ...cur, end_ms: time_ms, heading_end: heading, strength }
  }

  return {
    get swinging(): boolean {
      return current !== null
    },
    push(time_ms: number, speed: number | null, heading: number | null): Swing | null {
      const c = config()
      if (speed === null) {
        // Gyro dropped mid-swing: abandon rather than throw on partial data.
        current = null
        return null
      }
      if (current) {
        if (speed > current.peak_rate) {
          current.peak_rate = speed
          current.peak_ms = time_ms
          if (heading !== null) current.heading_peak = heading
        }
        if (speed < c.threshold * c.rearmRatio) {
          armed = true
          return finish(time_ms, heading)
        }
        if (time_ms - current.start_ms >= c.maxSwingMs) return finish(time_ms, heading)
        return null
      }
      if (speed < c.threshold * c.rearmRatio) armed = true
      if (armed && speed >= c.threshold && time_ms - lastSwingMs > c.cooldownMs) {
        armed = false
        lastSwingMs = time_ms
        current = {
          start_ms: time_ms, peak_ms: time_ms, peak_rate: speed,
          heading_start: heading, heading_peak: heading,
        }
      }
      return null
    },
    reset(): void {
      armed = true
      current = null
    },
  }
}
