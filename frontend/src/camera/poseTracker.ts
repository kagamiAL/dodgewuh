// Camera Legs: facing from MediaPipe pose landmarks. Pure and DOM-free.
// Port of the device-test camTracker. Jogging is NOT detected here: the Legs player's pocketed
// phone does that (controllers/legs/jogTracker.ts). Replayed on the recorded camera run, world
// knee lift peaked at only 6–10 cm against ±3 cm frame jitter, so a camera jog detector started
// 0.6–2.2 s late and dropped out mid-jog; the phone starts in ≈0.3 s with no dropouts.
//
// Input per frame for one person: world landmarks (metres, origin at the hip midpoint, +y down,
// smaller z = closer to the camera).
// - Facing: shoulder line L−R in world x/z → yaw. 0 = facing the camera, + = turned to the
//   player's left, ±180 = back to the camera. Smoothed as a unit vector so ±180 never averages
//   to 0. The move direction follows the yaw freely, snapping to straight within snap_deg.

export interface Landmark { x: number; y: number; z: number; visibility?: number }

export const poseTuning = {
  yaw_smooth_ms: 150,
  hysteresis_deg: 12,
  snap_deg: 10,
}

export type Facing = 'screen' | 'left' | 'right' | 'away'

export interface PoseState {
  /** A person is being tracked in the Legs half. */
  present: boolean
  facing: Facing | null
  yaw_deg: number | null
  /** Team-local unit direction the player faces: +r = their right, +f = toward the screen. */
  dir: { r: number; f: number } | null
}

const L = { lSh: 11, rSh: 12, lHip: 23, rHip: 24 }
const SECTORS: [Facing, number][] = [['screen', 0], ['left', 90], ['away', 180], ['right', -90]]

const angDiff = (a: number, b: number) => ((((a - b + 180) % 360) + 360) % 360) - 180

function yawToDir(yaw: number, snap: number): { r: number; f: number } {
  const c = Math.round(yaw / 90) * 90
  const y = ((Math.abs(yaw - c) <= snap ? c : yaw) * Math.PI) / 180
  const clean = (v: number) => (Math.abs(v) < 1e-9 ? 0 : v)
  return { r: clean(-Math.sin(y)), f: clean(Math.cos(y)) }
}

/**
 * The Legs player is whoever stands in the right half of the mirrored preview, i.e. raw image
 * x < 0.5. Picks the largest such person; the other half (Arms) is ignored entirely.
 */
export function pickLegsPerson(poses: Landmark[][]): number {
  let best = -1
  let bestSize = 0
  poses.forEach((lm, i) => {
    const hipX = (lm[L.lHip].x + lm[L.rHip].x) / 2
    if (hipX >= 0.5) return
    const xs = lm.map((p) => p.x)
    const ys = lm.map((p) => p.y)
    const size = (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys))
    if (size > bestSize) {
      bestSize = size
      best = i
    }
  })
  return best
}

export function createPoseTracker(p = poseTuning) {
  let vec: { c: number; s: number } | null = null
  let prevT: number | null = null
  let facing: Facing | null = null
  let state: PoseState = { present: false, facing: null, yaw_deg: null, dir: null }

  return {
    /** world is null when nobody is in the Legs half this frame. */
    push(t: number, world: Landmark[] | null): PoseState {
      if (!world) {
        state = { ...state, present: false }
        return state
      }
      const l = world[L.lSh]
      const r = world[L.rSh]
      const yawRaw = (Math.atan2(l.z - r.z, l.x - r.x) * 180) / Math.PI
      const dt = prevT === null ? 0 : t - prevT
      prevT = t
      const c = Math.cos((yawRaw * Math.PI) / 180)
      const s = Math.sin((yawRaw * Math.PI) / 180)
      const k = vec === null ? 1 : 1 - Math.exp(-dt / p.yaw_smooth_ms)
      vec = vec === null ? { c, s } : { c: vec.c + (c - vec.c) * k, s: vec.s + (s - vec.s) * k }
      const yaw = (Math.atan2(vec.s, vec.c) * 180) / Math.PI

      const nearest = SECTORS.reduce((best, sec) => (Math.abs(angDiff(yaw, sec[1])) < Math.abs(angDiff(yaw, best[1])) ? sec : best))
      // Switch the label only once clearly inside the new sector.
      if (facing === null || (nearest[0] !== facing && Math.abs(angDiff(yaw, nearest[1])) <= 45 - p.hysteresis_deg)) facing = nearest[0]

      const dir = yawToDir(yaw, p.snap_deg)
      state = { present: true, facing, yaw_deg: yaw, dir }
      return state
    },

    get state(): PoseState {
      return state
    },
  }
}
