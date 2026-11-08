// Camera Legs: jog-in-place + facing from MediaPipe pose landmarks. Pure and DOM-free.
// Port of the device-test camTracker; thresholds checked on a recorded run (jogging in four
// facings detected, none on knee lifts, slow walking, turning or fidgeting).
//
// Inputs per frame for one person: world landmarks (metres, origin at the hip midpoint, +y down,
// smaller z = closer to the camera) and image landmarks (normalised x/y, visibility).
// - Jogging: each knee's rise above its lowest point over the last baseline_ms. A knee-up is a
//   rise ≥ lift_up_m (re-armed below lift_down_m); jogging starts once start_events knee-ups with
//   both legs fall inside start_window_ms and stops after stop_ms without one.
// - Facing: shoulder line L−R in world x/z → yaw. 0 = facing the camera, + = turned to the
//   player's left, ±180 = back to the camera. Smoothed as a unit vector so ±180 never averages
//   to 0. The move direction follows the yaw freely, snapping to straight within snap_deg.

export interface Landmark { x: number; y: number; z: number; visibility?: number }

export const poseTuning = {
  lift_up_m: 0.08,
  lift_down_m: 0.03,
  baseline_ms: 2000,
  start_events: 3,
  start_window_ms: 1500,
  stop_ms: 800,
  yaw_smooth_ms: 150,
  hysteresis_deg: 12,
  snap_deg: 10,
}

export type Facing = 'screen' | 'left' | 'right' | 'away'

export interface PoseState {
  /** A person is being tracked in the Legs half. */
  present: boolean
  jogging: boolean
  facing: Facing | null
  yaw_deg: number | null
  /** Team-local unit direction the player faces: +r = their right, +f = toward the screen. */
  dir: { r: number; f: number } | null
  /** dir while jogging, else zero. */
  move: { r: number; f: number }
}

const L = { lSh: 11, rSh: 12, lHip: 23, rHip: 24, lKnee: 25, rKnee: 26 }
const SECTORS: [Facing, number][] = [['screen', 0], ['left', 90], ['away', 180], ['right', -90]]
const ZERO = { r: 0, f: 0 }

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
  const knees = { l: { hist: [] as { t: number; drop: number }[], armed: true }, r: { hist: [] as { t: number; drop: number }[], armed: true } }
  let events: { t: number; side: 'l' | 'r' }[] = []
  let lastEvent = -Infinity
  let jogging = false
  let vec: { c: number; s: number } | null = null
  let prevT: number | null = null
  let facing: Facing | null = null
  let state: PoseState = { present: false, jogging: false, facing: null, yaw_deg: null, dir: null, move: ZERO }

  function knee(k: typeof knees.l, side: 'l' | 'r', t: number, drop: number): void {
    k.hist.push({ t, drop })
    while (k.hist.length && t - k.hist[0].t > p.baseline_ms) k.hist.shift()
    const lift = Math.max(...k.hist.map((h) => h.drop)) - drop
    if (k.armed && lift >= p.lift_up_m) {
      k.armed = false
      events.push({ t, side })
      lastEvent = t
    } else if (!k.armed && lift < p.lift_down_m) k.armed = true
  }

  return {
    /** world/image are null when nobody is in the Legs half this frame. */
    push(t: number, world: Landmark[] | null): PoseState {
      if (!world) {
        jogging = false
        events = []
        state = { ...state, present: false, jogging: false, move: ZERO }
        return state
      }
      const hipY = (world[L.lHip].y + world[L.rHip].y) / 2
      knee(knees.l, 'l', t, world[L.lKnee].y - hipY)
      knee(knees.r, 'r', t, world[L.rKnee].y - hipY)
      events = events.filter((e) => t - e.t <= p.start_window_ms)
      const both = events.some((e) => e.side === 'l') && events.some((e) => e.side === 'r')
      if (!jogging && events.length >= p.start_events && both && t - lastEvent <= p.stop_ms) jogging = true
      else if (jogging && t - lastEvent > p.stop_ms) {
        jogging = false
        events = []
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
      state = { present: true, jogging, facing, yaw_deg: yaw, dir, move: jogging ? dir : ZERO }
      return state
    },

    get state(): PoseState {
      return state
    },
  }
}
