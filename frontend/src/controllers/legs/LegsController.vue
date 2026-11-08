<script setup lang="ts">
// Legs role: phone in a front trouser pocket. Jog in place to move; the way you face is the way
// you go (face the screen = forward, face left = left, turn around = back).
//
// Start tap (permission, audio, wake lock) → spoken "pocket it" → face the screen and stand still
// (heading 0 + gyro bias) → while jogging, input.legs carries the facing direction at 20 Hz.
// Stale sensors, a hidden page, an epoch change or unmount send zero immediately.
// With a screen camera on this team the phone still says WHEN they jog; the server swaps in the
// direction the camera sees them face (backend/app/services/game.py).
// See pocketFrame.ts / jogTracker.ts.

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { RoleComponentProps } from '@/phone/roleComponent'
import type { Permission, Vec2 } from '@/contracts/pending'
import { SENSOR_STALE_MS, type SensorSample } from '@/sensors/sensorService'
import { session } from '@/stores/session'
import { TEAM_HEX } from '@/theme'
import { calibrate, rotationVector, type StillSample } from './pocketFrame'
import { createJogTracker, type JogState } from './jogTracker'
import { beep, say, silence, unlockAudio } from './voice'

const props = defineProps<RoleComponentProps>()
const emit = defineEmits<{ calibrated: [value: boolean]; availability: [value: Permission] }>()

const POCKET_MS = 6000 // time to pocket the phone while the instruction plays
const SETTLE_MS = 1200 // after "stand still" before sampling
const STILL_MS = 1000
const MAX_TRIES = 4
const SEND_MS = 50 // 20 Hz (03)
const STOP_HOLD_MS = 1500

type Stage = 'start' | 'pocketing' | 'calibrating' | 'live' | 'blocked'
const stage = ref<Stage>('start')
const note = ref('')
const live = ref<JogState>({ jogging: false, heading_deg: 0, intensity: 0, dir: null })
const stopping = ref(false)

// 02: Team 1 forward is +z and right is +x; Team 2 is mirrored.
function toWorld(dir: JogState['dir']): Vec2 {
  if (!dir) return { x: 0, z: 0 }
  const s = props.team === 1 ? 1 : -1
  return { x: dir.r * s, z: dir.f * s }
}

let unsubscribe: (() => void) | null = null
let tracker: ReturnType<typeof createJogTracker> | null = null
let still: StillSample[] = []
let collecting = false
let tries = 0
let lastMotionMs: number | null = null
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

// A screen camera can steer this team's Legs (src/camera/CameraLegs.vue): the pocketed phone
// still detects jogging (much faster than pose landmarks) and the camera supplies the facing.
const cameraMode = computed(() =>
  !!session.data.room?.members.some((m) => m.device === 'screen' && m.connected && m.camera_team === props.team),
)

function send(move: Vec2): void {
  // The server accepts movement only while active (03); calibration can finish in the lobby.
  if (!props.connected || props.state.phase !== 'active') return
  props.transport.send({ v: 1, type: 'input.legs', payload: { seq: props.transport.nextInputSeq(), epoch: props.epoch, move } })
}

function tick(): void {
  const now = performance.now()
  const fresh = lastMotionMs !== null && now - lastMotionMs < SENSOR_STALE_MS
  setAvailability(fresh ? 'granted' : 'unknown')
  if (!tracker) return
  if (!fresh) tracker.halt()
  live.value = tracker.state
  send(toWorld(live.value.dir))
}

function onSample(s: SensorSample): void {
  if (s.motion_ms !== null) lastMotionMs = s.motion_ms
  if (collecting && s.beta_deg !== null && s.gamma_deg !== null) {
    still.push({
      beta_deg: s.beta_deg,
      gamma_deg: s.gamma_deg,
      accel_mag: s.accel ? Math.hypot(s.accel.x, s.accel.y, s.accel.z) : null,
      rot: s.rotation_rate ? rotationVector(s.rotation_rate) : null,
    })
  }
  if (stage.value !== 'live' || !tracker) return
  const wasJogging = tracker.state.jogging
  if (tracker.push(s).jogging !== wasJogging) tick() // send start/stop edges without waiting for the 20 Hz slot
}

function start(): void {
  // Everything gesture-gated starts synchronously inside this tap.
  unlockAudio()
  navigator.wakeLock?.request('screen').then((w) => (wakeLock = w)).catch(() => {})
  const permission = props.sensors.requestPermissionFromGesture()
  say('Put your phone in your front pocket, then face the screen.')
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
  say('Face the screen and stand still')
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
    tracker = createJogTracker(result.gyroBias)
    live.value = tracker.state
    stage.value = 'live'
    setCalibrated(true)
    beep(1200, 200)
    say('Go')
    sendTimer ??= setInterval(tick, SEND_MS)
    return
  }
  tries++
  if (tries < MAX_TRIES) {
    note.value = 'Moving — face the screen and stand still.'
    beep(300, 250)
    later(0, beginCalibration)
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
  tracker = null
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
  tracker?.halt()
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
      <h1>Legs{{ cameraMode ? ' · camera' : '' }}</h1>
      <ol v-if="cameraMode">
        <li>Tap <strong>Start</strong> and put the phone in your <strong>front pocket</strong>. It senses when you jog.</li>
        <li><strong>Face the screen</strong> and stand still when the voice says so.</li>
        <li>Stand in the <strong>right half</strong> of the camera view (Arms takes the left half). The camera sees which way you face.</li>
        <li><strong>Jog in place</strong> to move. Face the way you want to go: the screen = forward; turn to steer.</li>
      </ol>
      <ol v-else>
        <li>Tap <strong>Start</strong>.</li>
        <li>Put the phone in your <strong>front pocket</strong> (any way round).</li>
        <li><strong>Face the screen</strong> and stand still when the voice says so.</li>
        <li><strong>Jog in place</strong> to move. Face the way you want to go: screen = forward, turn left = left, turn right = right, turn around = back. Turn while standing, then jog.</li>
      </ol>
      <p v-if="note" class="note">{{ note }}</p>
      <button v-if="stage === 'start'" class="start" @click="start">Start</button>
    </template>

    <template v-else-if="stage === 'pocketing' || stage === 'calibrating'">
      <h1>{{ stage === 'pocketing' ? 'Pocket your phone' : 'Face the screen, stand still…' }}</h1>
      <p v-if="note" class="note">{{ note }}</p>
    </template>

    <div v-else class="lock">
      <div class="arrow" :class="{ moving: live.jogging }" :style="{ transform: `rotate(${-live.heading_deg}deg)` }">↑</div>
      <p>{{ live.jogging ? 'Jogging' : 'Standing' }} · facing {{ Math.round(live.heading_deg) }}° · intensity {{ live.intensity.toFixed(1) }}</p>
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
  padding: 1.5rem max(1rem, env(safe-area-inset-right)) max(1.5rem, env(safe-area-inset-bottom))
    max(1rem, env(safe-area-inset-left));
  box-sizing: border-box;
  border-top: 6px solid var(--team);
  overflow-wrap: break-word;
}
h1 {
  font-size: clamp(1.5rem, 8vw, 2rem);
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
  min-width: 0;
  min-height: min(120px, 22vh);
  font-size: clamp(1.25rem, 6vw, 1.6rem);
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
  padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom)
    env(safe-area-inset-left);
  background: #000;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}
.arrow {
  /* Shrink rather than clip on short/landscape phones. */
  font-size: min(9rem, 40vh, 45vw);
  line-height: 1;
  color: var(--team);
  opacity: 0.35;
}
.arrow.moving {
  opacity: 1;
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
