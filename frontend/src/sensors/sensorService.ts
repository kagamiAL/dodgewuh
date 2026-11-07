// Shared browser sensor capture: one event source per phone (plans/03, "Frontend module seams").
// Arms and Legs subscribe; raw samples never leave the device.

export type Permission = 'unknown' | 'granted' | 'denied' | 'unsupported'

/**
 * Local-only sample. accel is gravity-excluded m/s² in the W3C device frame (+x screen right,
 * +y screen top, +z out of the screen); rotation rates are deg/s. orientation_ms / motion_ms are the
 * last receipt times of each stream on performance.now(); a cached stream never gets a fresh
 * timestamp from the other one. Null fields are unavailable, never zero-filled.
 */
export interface SensorSample {
  time_ms: number
  orientation_ms: number | null
  motion_ms: number | null
  beta_deg: number | null
  gamma_deg: number | null
  accel: { x: number; y: number; z: number } | null
  rotation_rate: { alpha: number; beta: number; gamma: number } | null
}

export interface SensorService {
  requestPermissionFromGesture(): Promise<Permission>
  subscribe(handler: (sample: SensorSample) => void): () => void
  stop(): void
}

/** A stream is stale once its last event is this old (03). */
export const SENSOR_STALE_MS = 250

// WebKit on iOS reports DeviceMotion acceleration with the opposite sign to the W3C spec
// (measured on iOS 18.7: upright phone reads accelerationIncludingGravity.y ≈ −9.8, spec says +9.8).
// Normalize here so every consumer sees spec-convention values.
const ACCEL_SIGN = isAppleTouchDevice() ? -1 : 1

function isAppleTouchDevice(): boolean {
  if (typeof navigator === 'undefined') return false
  return /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
}

function fin(v: number | null | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

type PermissionRequester = { requestPermission?: () => Promise<'granted' | 'denied' | 'default'> }

export function createSensorService(): SensorService {
  const handlers = new Set<(sample: SensorSample) => void>()
  let permission: Permission = 'unknown'
  let listening = false
  let orientation_ms: number | null = null
  let motion_ms: number | null = null
  let beta_deg: number | null = null
  let gamma_deg: number | null = null
  let accel: SensorSample['accel'] = null
  let rotation_rate: SensorSample['rotation_rate'] = null

  function emit(): void {
    const sample: SensorSample = { time_ms: performance.now(), orientation_ms, motion_ms, beta_deg, gamma_deg, accel, rotation_rate }
    for (const h of handlers) h(sample)
  }

  function onOrientation(e: DeviceOrientationEvent): void {
    orientation_ms = performance.now()
    beta_deg = fin(e.beta)
    gamma_deg = fin(e.gamma)
    emit()
  }

  function onMotion(e: DeviceMotionEvent): void {
    motion_ms = performance.now()
    const a = e.acceleration
    const ax = fin(a?.x), ay = fin(a?.y), az = fin(a?.z)
    accel = ax !== null && ay !== null && az !== null ? { x: ax * ACCEL_SIGN, y: ay * ACCEL_SIGN, z: az * ACCEL_SIGN } : null
    const r = e.rotationRate
    const ra = fin(r?.alpha), rb = fin(r?.beta), rg = fin(r?.gamma)
    rotation_rate = ra !== null && rb !== null && rg !== null ? { alpha: ra, beta: rb, gamma: rg } : null
    emit()
  }

  function attach(): void {
    if (listening) return
    window.addEventListener('deviceorientation', onOrientation)
    window.addEventListener('devicemotion', onMotion)
    listening = true
  }

  function detach(): void {
    if (!listening) return
    window.removeEventListener('deviceorientation', onOrientation)
    window.removeEventListener('devicemotion', onMotion)
    listening = false
    orientation_ms = motion_ms = beta_deg = gamma_deg = null
    accel = rotation_rate = null
  }

  return {
    requestPermissionFromGesture() {
      if (typeof window === 'undefined' || !window.isSecureContext) return Promise.resolve<Permission>('unsupported')
      if (typeof DeviceMotionEvent === 'undefined' && typeof DeviceOrientationEvent === 'undefined') {
        return Promise.resolve<Permission>('unsupported')
      }
      // Both requests must start synchronously inside the tap; nothing may be awaited first.
      const motionReq = (globalThis.DeviceMotionEvent as unknown as PermissionRequester | undefined)?.requestPermission
      const orientReq = (globalThis.DeviceOrientationEvent as unknown as PermissionRequester | undefined)?.requestPermission
      const pending = [motionReq?.call(DeviceMotionEvent), orientReq?.call(DeviceOrientationEvent)].filter(
        (p): p is Promise<'granted' | 'denied' | 'default'> => p !== undefined,
      )
      if (pending.length === 0) {
        // No permission API (e.g. Android Chrome): subscribe and let consumers judge the data.
        permission = 'granted'
        if (handlers.size > 0) attach()
        return Promise.resolve(permission)
      }
      return Promise.allSettled(pending).then((results) => {
        const granted = results.every((r) => r.status === 'fulfilled' && r.value === 'granted')
        permission = granted ? 'granted' : 'denied'
        if (granted && handlers.size > 0) attach()
        return permission
      })
    },

    subscribe(handler) {
      handlers.add(handler)
      if (permission === 'granted') attach()
      return () => {
        handlers.delete(handler)
        if (handlers.size === 0) detach()
      }
    },

    stop() {
      handlers.clear()
      detach()
    },
  }
}
