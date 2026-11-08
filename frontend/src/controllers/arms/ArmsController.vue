<script setup lang="ts">
// Arms role: hold the phone like a stick at chest height, screen facing left, facing the TV.
//
// Enable motion → hold steady + "Set forward" (calibration) → live:
//   - aim follows where the phone points (throwGesture.pointingHeading), sent 20 Hz while active
//   - Hold the pad = press (server picks up the nearest ball)
//   - flick while holding = release, aimed at the flick's peak, strength from flick speed
//   - lift without a flick, hidden page, stale sensors, unmount = cancel (never a throw)
// The server decides pickup, possession, no-throw zone and whether a release is legal (02).

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { RoleComponentProps } from '@/phone/roleComponent'
import type { Permission, Vec2 } from '@/contracts/pending'
import { SENSOR_STALE_MS, type SensorSample } from '@/sensors/sensorService'
import { TEAM_HEX } from '@/theme'
import {
  DEFAULT_SWING, angleDiff, createSwingDetector, pointingHeading, rotationSpeed, screenNormal, yawToWorldAim,
} from './throwGesture'

const props = defineProps<RoleComponentProps>()
const emit = defineEmits<{ calibrated: [value: boolean]; availability: [value: Permission] }>()

const SEND_MS = 50 // 20 Hz (03)
const CAL_MS = 600
const CAL_MIN_SAMPLES = 10
const CAL_MAX_SPREAD_DEG = 8
const GRIP_OK = 0.7 // horizontal length of the screen normal needed to calibrate
const NO_THROW_Z = 2.0 // 02: centre abs(z) ≤ 2 m
const RAD = 180 / Math.PI

type Stage = 'start' | 'aim' | 'calibrating' | 'live' | 'blocked'
const stage = ref<Stage>('start')
const note = ref('')
const holding = ref(false)
const flash = ref<'throw' | 'cancel' | null>(null)
const yawDeg = ref<number | null>(null)
const sideways = ref<number | null>(null)

let unsubscribe: (() => void) | null = null
let sendTimer: ReturnType<typeof setInterval> | null = null
let flashTimer: ReturnType<typeof setTimeout> | null = null
let wakeLock: WakeLockSentinel | null = null
let pointerId: number | null = null
let heading: number | null = null
let forward: number | null = null
let orientationMs: number | null = null
let motionMs: number | null = null
let lastMotionFed: number | null = null
let calHeadings: number[] | null = null
let availability: Permission | null = null
let isCalibrated = false

const detector = createSwingDetector(() => DEFAULT_SWING)

const me = computed(() => props.state.characters.find((c) => c.team === props.team) ?? null)
const hasBall = computed(() => !!me.value?.held_ball_id)
const inNoThrowZone = computed(() => !!me.value && Math.abs(me.value.pos.z) <= NO_THROW_Z)
const active = computed(() => props.connected && props.state.phase === 'active')

function setAvailability(p: Permission): void {
  if (p !== availability) emit('availability', (availability = p))
}
function setCalibrated(v: boolean): void {
  if (v !== isCalibrated) emit('calibrated', (isCalibrated = v))
}

function sensorsFresh(now = performance.now()): boolean {
  return orientationMs !== null && now - orientationMs < SENSOR_STALE_MS &&
    motionMs !== null && now - motionMs < SENSOR_STALE_MS && heading !== null
}

function aimFrom(h: number | null): Vec2 {
  const y = h !== null && forward !== null ? angleDiff(h, forward) : 0
  return yawToWorldAim(y, props.team)
}

function send(action: 'aim' | 'press' | 'release' | 'cancel', aim: Vec2, strength: number | null = null): void {
  if (!active.value) return
  props.transport.send({
    v: 1, type: 'input.arms',
    payload: { seq: props.transport.nextInputSeq(), epoch: props.epoch, aim, action, strength },
  })
}

function showFlash(kind: 'throw' | 'cancel'): void {
  flash.value = kind
  if (flashTimer) clearTimeout(flashTimer)
  flashTimer = setTimeout(() => (flash.value = null), 600)
}

function cancelHold(): void {
  if (!holding.value) return
  holding.value = false
  send('cancel', aimFrom(heading))
  showFlash('cancel')
}

function tick(): void {
  const fresh = sensorsFresh()
  setAvailability(fresh ? 'granted' : 'unknown')
  if (stage.value !== 'live') return
  if (!fresh) {
    cancelHold()
    return
  }
  send('aim', aimFrom(heading))
}

function onSample(s: SensorSample): void {
  if (s.orientation_ms !== null) orientationMs = s.orientation_ms
  if (s.motion_ms !== null) motionMs = s.motion_ms
  if (s.alpha_deg !== null && s.beta_deg !== null && s.gamma_deg !== null) {
    const n = screenNormal(s.alpha_deg, s.beta_deg, s.gamma_deg)
    sideways.value = Math.hypot(n.x, n.y)
    const h = pointingHeading(s.alpha_deg, s.beta_deg, s.gamma_deg)
    if (h !== null) heading = h
    if (calHeadings && h !== null && sideways.value >= GRIP_OK) calHeadings.push(h)
  }
  yawDeg.value = heading !== null && forward !== null ? angleDiff(heading, forward) * RAD : null

  if (stage.value !== 'live' || s.motion_ms === lastMotionFed) return
  lastMotionFed = s.motion_ms
  const swing = detector.push(s.time_ms, rotationSpeed(s.rotation_rate), heading)
  if (swing && holding.value) {
    holding.value = false // auto-release; a fresh press is needed for the next ball
    send('release', aimFrom(swing.heading_peak ?? heading), swing.strength)
    showFlash('throw')
  }
}

function start(): void {
  // Permission must be requested synchronously inside the tap (iOS).
  const permission = props.sensors.requestPermissionFromGesture()
  navigator.wakeLock?.request('screen').then((w) => (wakeLock = w)).catch(() => {})
  note.value = ''
  permission.then((p) => {
    if (p !== 'granted') {
      setAvailability(p)
      stage.value = 'blocked'
      note.value = p === 'denied'
        ? 'Motion access was denied. Close this tab, reopen the link and tap Allow.'
        : 'This browser has no motion sensors over HTTPS. Use Safari on an iPhone.'
      return
    }
    unsubscribe ??= props.sensors.subscribe(onSample)
    sendTimer ??= setInterval(tick, SEND_MS)
    stage.value = 'aim'
  })
}

function setForward(): void {
  if (stage.value === 'live') cancelHold()
  stage.value = 'calibrating'
  note.value = ''
  calHeadings = []
  setTimeout(finishCalibration, CAL_MS)
}

function finishCalibration(): void {
  const hs = calHeadings ?? []
  calHeadings = null
  if (stage.value !== 'calibrating') return
  if (hs.length < CAL_MIN_SAMPLES) return failCalibration('Turn the screen to face left and hold still.')
  // Circular mean, then spread around it.
  const mean = Math.atan2(hs.reduce((a, h) => a + Math.sin(h), 0), hs.reduce((a, h) => a + Math.cos(h), 0))
  const spread = Math.max(...hs.map((h) => Math.abs(angleDiff(h, mean)))) * RAD
  if (spread > CAL_MAX_SPREAD_DEG) return failCalibration('Too much movement — hold still while it sets forward.')
  forward = mean
  detector.reset()
  stage.value = 'live'
  setCalibrated(true)
}

function failCalibration(message: string): void {
  stage.value = 'aim'
  note.value = message
  setCalibrated(false)
}

function onPadDown(e: PointerEvent): void {
  if (stage.value !== 'live' || pointerId !== null || !sensorsFresh()) return
  pointerId = e.pointerId
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  holding.value = true
  detector.reset() // a swing already in progress before the press must not throw
  send('press', aimFrom(heading))
}

function onPadUp(e: PointerEvent): void {
  if (e.pointerId !== pointerId) return
  pointerId = null
  cancelHold() // no-op if a flick already released
}

function onVisibility(): void {
  if (!document.hidden) return
  cancelHold()
  if (stage.value === 'live' || stage.value === 'calibrating') {
    stage.value = 'aim'
    note.value = 'The page was hidden. Set forward again.'
    setCalibrated(false)
  }
}
document.addEventListener('visibilitychange', onVisibility)

// New epoch (countdown/active): the server already cleared Hold; drop the local latch, keep calibration.
watch(() => props.epoch, () => {
  holding.value = false
  detector.reset()
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibility)
  cancelHold()
  if (sendTimer) clearInterval(sendTimer)
  if (flashTimer) clearTimeout(flashTimer)
  wakeLock?.release().catch(() => {})
  setCalibrated(false)
  unsubscribe?.()
  unsubscribe = null
})

const padText = computed(() => {
  if (flash.value === 'throw') return 'Thrown!'
  if (flash.value === 'cancel') return 'Dropped'
  if (!active.value) return 'Waiting for the round…'
  if (holding.value) return hasBall.value ? (inNoThrowZone.value ? 'Move back to throw' : 'Flick to throw!') : 'Grabbing…'
  return 'Hold to grab'
})
</script>

<template>
  <section class="arms" :style="{ '--team': TEAM_HEX[team] }">
    <template v-if="stage === 'start' || stage === 'blocked'">
      <h1>Arms</h1>
      <ol>
        <li>Tap <strong>Enable motion</strong>.</li>
        <li>Stand facing the TV. Hold the phone <strong>like a stick at chest height</strong>, <strong>screen facing left</strong>.</li>
        <li>Point where you want to throw. <strong>Hold</strong> the pad with your thumb to grab, <strong>flick</strong> to throw.</li>
      </ol>
      <p v-if="note" class="note">{{ note }}</p>
      <button v-if="stage === 'start'" class="big" @click="start">Enable motion</button>
    </template>

    <template v-else-if="stage === 'aim' || stage === 'calibrating'">
      <h1>{{ stage === 'calibrating' ? 'Hold still…' : 'Set forward' }}</h1>
      <p>Face the TV, phone like a stick at chest height, <strong>screen facing left</strong>.</p>
      <p v-if="sideways !== null && sideways < GRIP_OK" class="note">Turn the screen to face left.</p>
      <p v-if="note" class="note">{{ note }}</p>
      <button class="big" :disabled="stage === 'calibrating'" @click="setForward">
        {{ stage === 'calibrating' ? 'Setting…' : 'Set forward' }}
      </button>
    </template>

    <div v-else class="live">
      <div class="status">
        <span :class="{ on: hasBall }">{{ hasBall ? '● Ball' : '○ No ball' }}</span>
        <span>aim {{ yawDeg === null ? '—' : `${Math.round(yawDeg)}°` }}</span>
        <button class="reset" @click="setForward">Re-set forward</button>
      </div>
      <div class="dial" aria-hidden="true">
        <div class="needle" :style="{ transform: `rotate(${Math.max(-75, Math.min(75, yawDeg ?? 0))}deg)` }" />
      </div>
      <div
        class="pad"
        :class="{ holding, throw: flash === 'throw', cancel: flash === 'cancel', idle: !active }"
        @pointerdown="onPadDown"
        @pointerup="onPadUp"
        @pointercancel="onPadUp"
        @lostpointercapture="onPadUp"
      >
        {{ padText }}
      </div>
    </div>
  </section>
</template>

<style scoped>
.arms {
  min-height: 100%;
  padding: 1rem max(1rem, env(safe-area-inset-right)) max(1rem, env(safe-area-inset-bottom))
    max(1rem, env(safe-area-inset-left));
  box-sizing: border-box;
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
.big {
  width: 100%;
  min-height: 120px;
  font-size: 1.6rem;
  font-weight: 700;
  border: 0;
  border-radius: 14px;
  background: var(--team);
  color: #000;
}
.big:disabled {
  opacity: 0.5;
}
.live {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
}
.status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  color: #aaa;
}
.status .on {
  color: var(--team);
  font-weight: 700;
}
.reset {
  margin-left: auto;
  padding: 0.4rem 0.75rem;
  font: inherit;
  font-size: 0.85rem;
  border: 1px solid #444;
  border-radius: 8px;
  background: #222;
  color: #ccc;
}
.dial {
  position: relative;
  height: 90px;
  overflow: hidden;
}
.needle {
  position: absolute;
  left: calc(50% - 3px);
  bottom: 0;
  width: 6px;
  height: 84px;
  border-radius: 3px;
  background: var(--team);
  transform-origin: 50% 100%;
}
.pad {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  border-radius: 18px;
  border: 3px solid var(--team);
  background: #161616;
  font-size: 1.6rem;
  font-weight: 800;
  text-align: center;
  touch-action: none;
}
.pad.holding {
  background: var(--team);
  color: #000;
}
.pad.throw {
  background: #3c6;
  color: #000;
}
.pad.cancel {
  background: #333;
  color: #aaa;
}
.pad.idle {
  opacity: 0.5;
}
</style>
