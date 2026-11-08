// Vertical reference and stand-still calibration for a pocketed phone.
//
// The player faces the screen and stands still for a second: that moment defines heading 0 and
// gives the gyro's resting bias. Only the vertical axis matters afterwards (turning is rotation
// about it), so the phone may sit in the pocket any way round.

export type Vec3 = { x: number; y: number; z: number }

export interface StillSample {
  beta_deg: number
  gamma_deg: number
  /** |accel| m/s², null if motion unavailable. */
  accel_mag: number | null
  /** Rotation rate in device axes (deg/s), null if unavailable. */
  rot: Vec3 | null
}

export type CalibrationResult =
  | { ok: true; gyroBias: Vec3; samples: number }
  | { ok: false; reason: 'too_few' | 'moving'; samples: number }

const DEG = Math.PI / 180

export function dot(a: Vec3, b: Vec3): number {
  return a.x * b.x + a.y * b.y + a.z * b.z
}

/** Unit "up" in device coordinates from W3C beta/gamma (alpha does not affect it). */
export function upFromOrientation(beta_deg: number, gamma_deg: number): Vec3 {
  const b = beta_deg * DEG, g = gamma_deg * DEG
  return { x: -Math.cos(b) * Math.sin(g), y: Math.sin(b), z: Math.cos(b) * Math.cos(g) }
}

/** Device-axis rotation vector (deg/s) from a spec-convention rotationRate. */
export function rotationVector(r: { alpha: number; beta: number; gamma: number }): Vec3 {
  return { x: r.beta, y: r.gamma, z: r.alpha }
}

export const CALIBRATION = {
  min_samples: 15,
  max_accel: 0.8, // m/s², pocket-still peaks observed 0.2–0.4
  max_rot: 30, // deg/s
  max_bias: 5, // deg/s; a larger "bias" is body sway, not sensor offset
}

export function calibrate(samples: StillSample[]): CalibrationResult {
  if (samples.length < CALIBRATION.min_samples) return { ok: false, reason: 'too_few', samples: samples.length }
  const moving = samples.some(
    (s) => (s.accel_mag !== null && s.accel_mag > CALIBRATION.max_accel) || (s.rot !== null && Math.hypot(s.rot.x, s.rot.y, s.rot.z) > CALIBRATION.max_rot),
  )
  if (moving) return { ok: false, reason: 'moving', samples: samples.length }

  const rots = samples.flatMap((s) => (s.rot ? [s.rot] : []))
  const n = rots.length || 1
  const mean = rots.reduce((a, r) => ({ x: a.x + r.x / n, y: a.y + r.y / n, z: a.z + r.z / n }), { x: 0, y: 0, z: 0 })
  const gyroBias = Math.hypot(mean.x, mean.y, mean.z) <= CALIBRATION.max_bias ? mean : { x: 0, y: 0, z: 0 }
  return { ok: true, gyroBias, samples: samples.length }
}
