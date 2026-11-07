<script setup lang="ts">
// Legs role: phone in a front trouser pocket, real steps move the character.
//
// Start tap (permission, audio, wake lock) → spoken "pocket it" → stand-still auto-calibration →
// each detected step sends a short movement burst as input.legs at 20 Hz. Stale sensors, a hidden
// page, an epoch change or unmount send zero immediately. See pocketFrame.ts / stepDetector.ts.

import { onBeforeUnmount, ref, watch } from 'vue'
import type { RoleComponentProps } from '@/phone/roleComponent'
import type { Permission, Vec2 } from '@/contracts/pending'
import { SENSOR_STALE_MS, type SensorSample } from '@/sensors/sensorService'
import { TEAM_HEX } from '@/theme'
import { calibrate, type StillSample } from './pocketFrame'
import { createStepDetector, type StepDir } from './stepDetector'
import { beep, say, silence, unlockAudio } from './voice'

const props = defineProps<RoleComponentProps>()
const emit = defineEmits<{ calibrated: [value: boolean]; availability: [value: Permission] }>()

const POCKET_MS = 6000 // time to pocket the phone while the instruction plays
const SETTLE_MS = 1200 // after "stand still" before sampling
const STILL_MS = 1000
const MAX_TRIES = 4
const BURST_MS = 400
const SEND_MS = 50 // 20 Hz (03)
const STOP_HOLD_MS = 1500

type Stage = 'start' | 'pocketing' | 'calibrating' | 'live' | 'blocked'
const stage = ref<Stage>('start')
const note = ref('')
const lastDir = ref<StepDir | null>(null)
const steps = ref(0)
const stopping = ref(false)

const ARROW: Record<StepDir, string> = { left: '←', right: '→', forward: '↑', back: '↓' }
const LOCAL: Record<StepDir, { r: number; f: number }> = {
  left: { r: -1, f: 0 }, right: { r: 1, f: 0 }, forward: { r: 0, f: 1 }, back: { r: 0, f: -1 },
}

// 02: Team 1 forward is +z and right is +x; Team 2 is mirrored.
function toWorld(dir: StepDir | null): Vec2 {
  if (!dir) return { x: 0, z: 0 }
  const s = props.team === 1 ? 1 : -1
  return { x: LOCAL[dir].r * s, z: LOCAL[dir].f * s }
}

let unsubscribe: (() => void) | null = null
let detector: ReturnType<typeof createStepDetector> | null = null
let still: StillSample[] = []
let collecting = false
let tries = 0
let lastMotionMs: number | null = null
let burst: { dir: StepDir; until: number } | null = null
let sendTimer: ReturnType<typeof setInterval> | null = null
let stopTimer: ReturnType<typeof setTimeout> | null = null
const timers = new Set<ReturnType<typeof setTimeout>>()
let wakeLock: WakeLockSentinel | null = null
let availability: Permission | null = null
let isCalibrated = false

function later(ms: number, fn: () => void): void {
  const id = setTimeout(() => {
    timers.delete(id)
    fn()
  }, ms)
  timers.add(id)
}

function setAvailability(p: Permission): void {
  if (p !== availability) emit('availability', (availability = p))
}
function setCalibrated(v: boolean): void {
  if (v !== isCalibrated) emit('calibrated', (isCalibrated = v))
}

function send(move: Vec2): void {
  // The server accepts movement only while active (03); calibration can finish in the lobby.
  if (!props.connected || props.state.phase !== 'active') return
  props.transport.send({ v: 1, type: 'input.legs', payload: { seq: props.transport.nextInputSeq(), epoch: props.epoch, move } })
}

function tick(): void {
  const now = performance.now()
  const fresh = lastMotionMs !== null && now - lastMotionMs < SENSOR_STALE_MS
  setAvailability(fresh ? 'granted' : 'unknown')
  if (!fresh || (burst && now >= burst.until)) burst = null
  send(toWorld(burst?.dir ?? null))
}

function onSample(s: SensorSample): void {
  if (s.motion_ms !== null) lastMotionMs = s.motion_ms
  if (collecting && s.beta_deg !== null && s.gamma_deg !== null) {
    still.push({
      beta_deg: s.beta_deg,
      gamma_deg: s.gamma_deg,
      accel_mag: s.accel ? Math.hypot(s.accel.x, s.accel.y, s.accel.z) : null,
      rot_mag: s.rotation_rate ? Math.hypot(s.rotation_rate.alpha, s.rotation_rate.beta, s.rotation_rate.gamma) : null,
    })
  }
  if (stage.value !== 'live' || !detector) return
  const step = detector.push(s)
  if (!step) return
  burst = { dir: step.dir, until: performance.now() + BURST_MS }
  lastDir.value = step.dir
  steps.value++
  tick() // send the edge now instead of waiting for the next 20 Hz slot
}

function start(): void {
  // Everything gesture-gated starts synchronously inside this tap.
  unlockAudio()
  navigator.wakeLock?.request('screen').then((w) => (wakeLock = w)).catch(() => {})
  const permission = props.sensors.requestPermissionFromGesture()
  say('Put your phone in your front pocket. Top of the phone up, screen facing your leg.')
  note.value = ''
  permission.then((p) => {
    if (p !== 'granted') {
      setAvailability(p)
      stage.value = 'blocked'
      note.value = p === 'denied'
        ? 'Motion access was denied. Close this tab, reopen the link and tap Allow.'
        : 'This browser has no motion sensors over HTTPS. Use Safari on an iPhone.'
      silence()
      return
    }
    unsubscribe ??= props.sensors.subscribe(onSample)
    stage.value = 'pocketing'
    tries = 0
    later(POCKET_MS, beginCalibration)
  })
}

function beginCalibration(): void {
  stage.value = 'calibrating'
  say('Stand still')
  later(SETTLE_MS, () => {
    still = []
    collecting = true
    later(STILL_MS, finishCalibration)
  })
}

function finishCalibration(): void {
  collecting = false
  const result = calibrate(still)
  if (result.ok) {
    detector = createStepDetector(result.frame)
    burst = null
    stage.value = 'live'
    setCalibrated(true)
    beep(1200, 200)
    say('Go')
    sendTimer ??= setInterval(tick, SEND_MS)
    return
  }
  tries++
  if (tries < MAX_TRIES) {
    note.value = result.reason === 'flat' ? 'Phone is lying flat — stand it upright in the pocket.' : 'Moving — stand still.'
    beep(300, 250)
    if (result.reason === 'flat') say('Stand the phone upright in your pocket')
    later(result.reason === 'flat' ? 2500 : 0, beginCalibration)
    return
  }
  stop('Could not calibrate. Take the phone out and tap Start again.')
  say('Calibration failed. Take out your phone and try again.')
}

function stop(message = ''): void {
  if (stage.value === 'live') send({ x: 0, z: 0 })
  for (const id of timers) clearTimeout(id)
  timers.clear()
  if (sendTimer) clearInterval(sendTimer)
  sendTimer = null
  collecting = false
  detector = null
  burst = null
  setCalibrated(false)
  wakeLock?.release().catch(() => {})
  wakeLock = null
  stage.value = 'start'
  note.value = message
}

// Touch lock while pocketed: only a deliberate press-and-hold leaves play.
function holdStop(): void {
  stopping.value = true
  stopTimer = setTimeout(() => {
    stopping.value = false
    silence()
    stop()
  }, STOP_HOLD_MS)
}
function releaseStop(): void {
  stopping.value = false
  if (stopTimer) clearTimeout(stopTimer)
  stopTimer = null
}

function onVisibility(): void {
  if (document.hidden && stage.value !== 'start' && stage.value !== 'blocked') {
    stop('The screen turned off. Take the phone out and tap Start again.')
  }
}
document.addEventListener('visibilitychange', onVisibility)

// A new epoch (countdown/active) clears the input latch but keeps calibration (roleComponent.ts).
watch(() => props.epoch, () => {
  burst = null
  if (stage.value === 'live') send({ x: 0, z: 0 })
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibility)
  releaseStop()
  stop()
  silence()
  unsubscribe?.()
  unsubscribe = null
})
</script>

<template>
  <section class="legs" :style="{ '--team': TEAM_HEX[team] }">
    <template v-if="stage === 'start' || stage === 'blocked'">
      <h1>Legs</h1>
      <ol>
        <li>Tap <strong>Start</strong>.</li>
        <li>Put the phone in your <strong>front pocket</strong>: top up, <strong>screen facing your leg</strong>.</li>
        <li>Stand still when the voice says so, then <strong>step</strong> to move: left, right, forward, back.</li>
      </ol>
      <p v-if="note" class="note">{{ note }}</p>
      <button v-if="stage === 'start'" class="start" @click="start">Start</button>
    </template>

    <template v-else-if="stage === 'pocketing' || stage === 'calibrating'">
      <h1>{{ stage === 'pocketing' ? 'Pocket your phone' : 'Stand still…' }}</h1>
      <p>Top up, screen facing your leg.</p>
      <p v-if="note" class="note">{{ note }}</p>
    </template>

    <div v-else class="lock">
      <div class="arrow">{{ lastDir ? ARROW[lastDir] : '•' }}</div>
      <p>{{ steps }} step{{ steps === 1 ? '' : 's' }}</p>
      <button
        class="stop"
        :class="{ holding: stopping }"
        @pointerdown="holdStop"
        @pointerup="releaseStop"
        @pointercancel="releaseStop"
        @pointerleave="releaseStop"
      >
        Hold to stop
      </button>
    </div>
  </section>
</template>

<style scoped>
.legs {
  min-height: 100%;
  padding: 1.5rem 1rem;
  box-sizing: border-box;
  border-top: 6px solid var(--team);
}
ol {
  padding-left: 1.2rem;
  line-height: 1.6;
}
.note {
  color: #fb4;
}
.start {
  width: 100%;
  min-height: 120px;
  font-size: 1.6rem;
  font-weight: 700;
  border: 0;
  border-radius: 14px;
  background: var(--team);
  color: #000;
}
.lock {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  background: #000;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}
.arrow {
  font-size: 9rem;
  line-height: 1;
  color: var(--team);
}
.stop {
  padding: 1rem 2rem;
  border: 1px solid #444;
  border-radius: 12px;
  background: #222;
  color: #aaa;
  transition: background 1.5s linear;
}
.stop.holding {
  background: #a33;
}
</style>
