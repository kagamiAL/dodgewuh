// Jog-in-place + facing direction for Legs. Pure and DOM-free.
//
// Tuned on a scripted pocket recording (knee lifts, jogging in four facings, walking, turning,
// fidgeting):
// - Jogging is detected from the RMS of gravity-excluded acceleration over 500 ms: jogging read
//   19–28 m/s², slow walking 7, turning steps 3–6, knee lifts 2.4, fidgeting 2.1, still 0.3.
//   Start after start_hold_ms above start_rms; stop after stop_hold_ms below stop_rms
//   (≈0.55 s to start and ≈0.6 s to stop after the body does).
// - Facing is the rotation about vertical (gyro · up from beta/gamma), 0 = facing the screen at
//   calibration, + = turned left. A pocketed thigh twists up to ~65° while jogging in place and
//   untwists after stopping, so facing is frozen while jogging, and for settle_ms afterwards only
//   fast turns (smoothed rate ≥ settle_turn_dps; untwisting peaked at 12°/s, real turns 109–219°/s)
//   count. Turn first, then jog: turning while jogging is not tracked.

import type { SensorSample } from '@/sensors/sensorService'
import { dot, rotationVector, upFromOrientation, type Vec3 } from './pocketFrame'

/** Live-tunable from the /sensors playground; trackers read it on every sample. */
export const jogTuning = {
  rms_window_ms: 500,
  start_rms: 9,
  stop_rms: 5,
  start_hold_ms: 300,
  stop_hold_ms: 300,
  settle_ms: 1500,
  settle_turn_dps: 40,
  turn_smooth_ms: 300,
  snap_deg: 45, // snap to forward/left/right/back within this; 45 = always
  max_dt_ms: 50,
}

export interface JogState {
  jogging: boolean
  heading_deg: number
  /** 500 ms RMS of |accel| (m/s²): the jog-intensity signal. */
  intensity: number
  /** Team-local unit direction while jogging (+r right, +f toward the screen), else null. */
  dir: { r: number; f: number } | null
}

function wrap(deg: number): number {
  return ((((deg + 180) % 360) + 360) % 360) - 180
}

export function headingToLocal(heading_deg: number, snap_deg = jogTuning.snap_deg): { r: number; f: number } {
  const cardinal = Math.round(heading_deg / 90) * 90
  const h = Math.abs(heading_deg - cardinal) <= snap_deg ? cardinal : heading_deg
  const rad = (h * Math.PI) / 180
  const clean = (v: number) => (Math.abs(v) < 1e-9 ? 0 : v)
  return { r: clean(-Math.sin(rad)), f: clean(Math.cos(rad)) }
}

export function createJogTracker(gyroBias: Vec3, p = jogTuning) {
  let heading = 0
  let up: Vec3 | null = null
  let lastMotionMs: number | null = null
  let prevT: number | null = null
  const window: { t: number; a2: number }[] = []
  let sumA2 = 0
  let intensity = 0
  let jogging = false
  let aboveSince: number | null = null
  let belowSince: number | null = null
  let jogEnded = -Infinity
  let yawSmooth = 0

  function state(): JogState {
    return { jogging, heading_deg: heading, intensity, dir: jogging ? headingToLocal(heading, p.snap_deg) : null }
  }

  function updateJogging(t: number): void {
    if (!jogging) {
      aboveSince = intensity >= p.start_rms ? (aboveSince ?? t) : null
      if (aboveSince !== null && t - aboveSince >= p.start_hold_ms) {
        jogging = true
        belowSince = null
      }
    } else {
      belowSince = intensity < p.stop_rms ? (belowSince ?? t) : null
      if (belowSince !== null && t - belowSince >= p.stop_hold_ms) {
        jogging = false
        aboveSince = null
        jogEnded = t
      }
    }
  }

  return {
    push(s: SensorSample): JogState {
      if (s.beta_deg !== null && s.gamma_deg !== null) up = upFromOrientation(s.beta_deg, s.gamma_deg)
      const t = s.time_ms
      if (s.motion_ms !== t || lastMotionMs === t) return state()
      lastMotionMs = t
      const dt = prevT === null ? 0 : Math.min(Math.max(t - prevT, 0), p.max_dt_ms)
      prevT = t

      if (s.accel) {
        const a2 = s.accel.x ** 2 + s.accel.y ** 2 + s.accel.z ** 2
        window.push({ t, a2 })
        sumA2 += a2
        while (window.length && t - window[0].t > p.rms_window_ms) sumA2 -= window.shift()!.a2
        intensity = Math.sqrt(Math.max(sumA2, 0) / window.length)
        updateJogging(t)
      }

      if (s.rotation_rate && up) {
        const raw = rotationVector(s.rotation_rate)
        const yaw = dot({ x: raw.x - gyroBias.x, y: raw.y - gyroBias.y, z: raw.z - gyroBias.z }, up)
        if (dt > 0) yawSmooth += (yaw - yawSmooth) * (1 - Math.exp(-dt / p.turn_smooth_ms))
        let rate = yaw
        if (jogging) rate = 0
        else if (t - jogEnded < p.settle_ms) rate = Math.abs(yawSmooth) >= p.settle_turn_dps ? yawSmooth : 0
        heading = wrap(heading + (rate * dt) / 1000)
      }
      return state()
    },

    /** Stop moving immediately (stale data, epoch change); facing is kept. */
    halt(): void {
      if (jogging) jogEnded = prevT ?? -Infinity
      jogging = false
      aboveSince = belowSince = null
    },

    get state(): JogState {
      return state()
    },
  }
}
