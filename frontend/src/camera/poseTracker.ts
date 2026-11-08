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

// --- Camera dodge -------------------------------------------------------------------------------
// The victim's screen overlays a ball on the preview and, when the dodge window closes, checks
// whether it overlaps the Legs player's body. The body is built from the pose landmarks (torso
// quad, head circle, limb capsules) in raw image pixels, so the check matches the drawn skeleton.

/** A ball on the camera image: centre in raw normalized coords (as landmarks), radius in pixels. */
export interface OverlayBall { x: number; y: number; r: number }

const B = { nose: 0, lSh: 11, rSh: 12, lEl: 13, rEl: 14, lWr: 15, rWr: 16, lHip: 23, rHip: 24, lKn: 25, rKn: 26, lAn: 27, rAn: 28 }
const LIMBS: [number, number][] = [
  [B.lSh, B.lEl], [B.lEl, B.lWr], [B.rSh, B.rEl], [B.rEl, B.rWr],
  [B.lHip, B.lKn], [B.lKn, B.lAn], [B.rHip, B.rKn], [B.rKn, B.rAn],
]
const VISIBLE = 0.3
const HEAD_R = 0.45 // × shoulder width
const LIMB_R = 0.12 // × shoulder width

const seen = (p: Landmark, min = VISIBLE) => (p.visibility ?? 1) >= min

/** Mean of the shoulders and hips, raw normalized coords. */
export function torsoCenter(lm: Landmark[]): { x: number; y: number } {
  const pts = [lm[B.lSh], lm[B.rSh], lm[B.lHip], lm[B.rHip]]
  return { x: pts.reduce((s, p) => s + p.x, 0) / 4, y: pts.reduce((s, p) => s + p.y, 0) / 4 }
}

/** Shoulder width in pixels; scales the ball and body so camera distance doesn't matter. */
export function shoulderWidth(lm: Landmark[], w: number, h: number): number {
  return Math.hypot((lm[B.lSh].x - lm[B.rSh].x) * w, (lm[B.lSh].y - lm[B.rSh].y) * h)
}

/**
 * Still a fair dodge position: shoulders and hips clearly visible, hips inside the frame and in
 * the Legs half (raw x < 0.5, the right half of the mirrored preview). Jumping out of frame or
 * into the Arms half fails.
 */
export function inLegsHalf(lm: Landmark[]): boolean {
  if (![B.lSh, B.rSh, B.lHip, B.rHip].every((i) => seen(lm[i], 0.5))) return false
  const hipX = (lm[B.lHip].x + lm[B.rHip].x) / 2
  const hipY = (lm[B.lHip].y + lm[B.rHip].y) / 2
  return hipX > 0.02 && hipX < 0.5 && hipY > 0 && hipY < 1
}

function segDist(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy
  const t = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy))
}

function inPolygon(px: number, py: number, poly: { x: number; y: number }[]): boolean {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i]
    const b = poly[j]
    if (a.y > py !== b.y > py && px < ((b.x - a.x) * (py - a.y)) / (b.y - a.y) + a.x) inside = !inside
  }
  return inside
}

/** Does the overlay ball touch the player's body (torso, head or any visible limb)? */
export function bodyHitsBall(lm: Landmark[], w: number, h: number, ball: OverlayBall): boolean {
  const px = (i: number) => ({ x: lm[i].x * w, y: lm[i].y * h })
  const cx = ball.x * w
  const cy = ball.y * h
  const sw = shoulderWidth(lm, w, h)

  const torso = [px(B.lSh), px(B.rSh), px(B.rHip), px(B.lHip)]
  if (inPolygon(cx, cy, torso)) return true
  for (let i = 0; i < 4; i++) {
    const a = torso[i]
    const b = torso[(i + 1) % 4]
    if (segDist(cx, cy, a.x, a.y, b.x, b.y) <= ball.r) return true
  }
  if (seen(lm[B.nose])) {
    const n = px(B.nose)
    if (Math.hypot(cx - n.x, cy - n.y) <= ball.r + HEAD_R * sw) return true
  }
  for (const [i, j] of LIMBS) {
    if (!seen(lm[i]) || !seen(lm[j])) continue
    const a = px(i)
    const b = px(j)
    if (segDist(cx, cy, a.x, a.y, b.x, b.y) <= ball.r + LIMB_R * sw) return true
  }
  return false
}
