// Step-direction detector for Legs. Pure and DOM-free.
//
// Input: SensorSamples (spec-convention accel from sensorService) plus the BodyFrame from pocket
// calibration. Only fresh motion events are used. Tuned on recorded steps (docs/device-tests):
//
// onset when horizontal |a| ≥ onset_ms2 → integrate body-frame (right, forward) acceleration for
// window_ms → the dominant axis and its sign give the direction. Each step is a push followed by a
// braking spike the opposite way, so after a detection new onsets wait until refractory_ms has
// passed AND the phone has settled (horizontal |a| < settle_ms2 for settle_ms), capped at max_block_ms.

import type { SensorSample } from '@/sensors/sensorService'
import { dot, type BodyFrame } from './pocketFrame'

export type StepDir = 'left' | 'right' | 'forward' | 'back'

export interface StepDetection {
  dir: StepDir
  /** Body-frame velocity change over the window (m/s): +right, +forward. */
  v_right: number
  v_forward: number
  t_onset: number
  t_detect: number
  peak_accel: number
}

export const STEP_DEFAULTS = {
  onset_ms2: 1.8,
  window_ms: 150,
  refractory_ms: 500,
  settle_ms2: 1.2,
  settle_ms: 100,
  max_block_ms: 1500,
  reject_refractory_ms: 300,
  min_v: 0.08,
  max_dt_ms: 50,
  max_gap_ms: 250,
}
export type StepParams = typeof STEP_DEFAULTS

interface Window { t0: number; vr: number; vf: number; peak: number }

export function createStepDetector(frame: BodyFrame, overrides: Partial<StepParams> = {}) {
  const p: StepParams = { ...STEP_DEFAULTS, ...overrides }
  let lastMotionMs: number | null = null
  let prevT: number | null = null
  let blockedUntil = -Infinity
  let settleNeeded = false
  let settleCap = -Infinity
  let quietSince: number | null = null
  let win: Window | null = null

  function integrate(ar: number, af: number, ah: number, dt: number): void {
    if (!win) return
    const s = Math.min(dt, p.max_dt_ms) / 1000
    win.vr += ar * s
    win.vf += af * s
    if (ah > win.peak) win.peak = ah
  }

  function finish(t: number): StepDetection | null {
    const w = win!
    win = null
    const lateral = Math.abs(w.vr) >= Math.abs(w.vf)
    const v = lateral ? w.vr : w.vf
    if (Math.abs(v) < p.min_v) {
      blockedUntil = t + p.reject_refractory_ms
      return null
    }
    blockedUntil = t + p.refractory_ms
    settleNeeded = true
    quietSince = null
    settleCap = t + Math.max(p.max_block_ms, p.refractory_ms)
    return {
      dir: lateral ? (v > 0 ? 'right' : 'left') : v > 0 ? 'forward' : 'back',
      v_right: w.vr,
      v_forward: w.vf,
      t_onset: w.t0,
      t_detect: t,
      peak_accel: w.peak,
    }
  }

  return {
    push(s: SensorSample): StepDetection | null {
      const t = s.time_ms
      if (s.motion_ms !== t || lastMotionMs === t) return null
      lastMotionMs = t
      const rawDt = prevT === null ? 0 : t - prevT
      const dt = Math.min(Math.max(rawDt, 0), p.max_dt_ms)
      prevT = t
      if (!s.accel) return null

      const ar = dot(s.accel, frame.right)
      const af = dot(s.accel, frame.forward)
      const ah = Math.hypot(ar, af)

      if (!win) {
        if (settleNeeded) {
          if (ah < p.settle_ms2) quietSince ??= t
          else quietSince = null
          const settled = quietSince !== null && t - quietSince >= p.settle_ms
          if (t >= blockedUntil && (settled || t >= settleCap)) settleNeeded = false
          else return null
        }
        if (t < blockedUntil || ah < p.onset_ms2) return null
        win = { t0: t, vr: 0, vf: 0, peak: 0 }
        integrate(ar, af, ah, dt || 1000 / 60)
        return null
      }
      if (rawDt > p.max_gap_ms) {
        win = null
        return null
      }
      integrate(ar, af, ah, dt)
      return t - win.t0 < p.window_ms ? null : finish(t)
    },

    reset(): void {
      lastMotionMs = prevT = null
      blockedUntil = settleCap = -Infinity
      settleNeeded = false
      quietSince = null
      win = null
    },
  }
}
