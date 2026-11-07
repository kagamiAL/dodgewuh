// Body frame for a phone in a front trouser pocket, from a still moment only.
//
// Assumes the instruction "screen facing your leg": the screen normal (+z) then points back into the
// body, so body-forward is −z projected onto the horizontal plane, exactly as when the phone is held
// facing the player. Gravity handles tilt and upside-down placement. A screen-out phone mirrors
// every direction and cannot be told apart while standing still.

export type Vec3 = { x: number; y: number; z: number }

export interface BodyFrame {
  up: Vec3
  right: Vec3
  forward: Vec3
}

export type CalibrationResult =
  | { ok: true; frame: BodyFrame; samples: number }
  | { ok: false; reason: 'too_few' | 'moving' | 'flat'; samples: number }

const DEG = Math.PI / 180

function norm(v: Vec3): Vec3 {
  const n = Math.hypot(v.x, v.y, v.z) || 1
  return { x: v.x / n, y: v.y / n, z: v.z / n }
}
export function dot(a: Vec3, b: Vec3): number {
  return a.x * b.x + a.y * b.y + a.z * b.z
}
function cross(a: Vec3, b: Vec3): Vec3 {
  return { x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x }
}

/** Unit "up" in device coordinates from W3C beta/gamma (alpha does not affect it). */
export function upFromOrientation(beta_deg: number, gamma_deg: number): Vec3 {
  const b = beta_deg * DEG, g = gamma_deg * DEG
  return { x: -Math.cos(b) * Math.sin(g), y: Math.sin(b), z: Math.cos(b) * Math.cos(g) }
}

export interface StillSample {
  beta_deg: number
  gamma_deg: number
  /** Horizontal-ish motion energy at this instant (|accel| m/s²); null if motion unavailable. */
  accel_mag: number | null
  rot_mag: number | null
}

export const CALIBRATION = {
  min_samples: 15,
  max_accel: 0.8, // m/s², pocket-still peaks observed 0.2–0.4
  max_rot: 30, // deg/s
  min_horizontal: 0.5, // |−z projected| below this means the phone lies nearly flat
}

export function calibrate(samples: StillSample[]): CalibrationResult {
  if (samples.length < CALIBRATION.min_samples) return { ok: false, reason: 'too_few', samples: samples.length }
  const moving = samples.some(
    (s) => (s.accel_mag !== null && s.accel_mag > CALIBRATION.max_accel) || (s.rot_mag !== null && s.rot_mag > CALIBRATION.max_rot),
  )
  if (moving) return { ok: false, reason: 'moving', samples: samples.length }

  const sum = samples.reduce(
    (acc, s) => {
      const u = upFromOrientation(s.beta_deg, s.gamma_deg)
      return { x: acc.x + u.x, y: acc.y + u.y, z: acc.z + u.z }
    },
    { x: 0, y: 0, z: 0 },
  )
  const up = norm(sum)
  const back = { x: 0, y: 0, z: 1 }
  const backH = { x: back.x - dot(back, up) * up.x, y: back.y - dot(back, up) * up.y, z: back.z - dot(back, up) * up.z }
  if (Math.hypot(backH.x, backH.y, backH.z) < CALIBRATION.min_horizontal) return { ok: false, reason: 'flat', samples: samples.length }
  const forward = norm({ x: -backH.x, y: -backH.y, z: -backH.z })
  const right = norm(cross(forward, up))
  return { ok: true, frame: { up, right, forward }, samples: samples.length }
}
