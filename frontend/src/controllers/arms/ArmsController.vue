<script setup lang="ts">
// Arms role: hold the phone like a stick at chest height, screen facing left, facing the TV.
//
// Enable motion → hold steady + "Set forward" (calibration) → live:
//   - aim follows where the phone points (throwGesture.pointingHeading), sent 20 Hz while active
//   - thumb anywhere on the screen = press (server picks up the nearest ball)
//   - chop while holding (top of the phone swings down ≥ 90° toward the TV) = release,
//     aimed where the phone points at that moment, strength from chop speed
//   - lift without a flick, hidden page, stale sensors, unmount = cancel (never a throw)
// The server decides pickup, possession, no-throw zone and whether a release is legal (02).

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { RoleComponentProps } from '@/phone/roleComponent'
import type { Permission, Vec2 } from '@/contracts/pending'
import { SENSOR_STALE_MS, type SensorSample } from '@/sensors/sensorService'
import { TEAM_HEX } from '@/theme'
import {
  angleDiff, assistTuning, assistYaw, chopTuning, createChopDetector, pointingHeading, screenNormal, topPitch,
  yawToWorldAim,
  type ScreenSide,
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
const locked = ref(false) // aim assist would pull this aim onto the opponent
const side = ref<ScreenSide>('left')

let unsubscribe: (() => void) | null = null
let sendTimer: ReturnType<typeof setInterval> | null = null
let flashTimer: ReturnType<typeof setTimeout> | null = null
let wakeLock: WakeLockSentinel | null = null
let pointerId: number | null = null
let heading: number | null = null
let forward: number | null = null
let orientationMs: number | null = null
let motionMs: number | null = null
let lastOrientationFed: number | null = null
let calHeadings: number[] | null = null
let availability: Permission | null = null
let isCalibrated = false

const detector = createChopDetector(() => chopTuning)

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

// Opponent velocity from recent authoritative snapshots, for aim-assist lead.
const oppHistory: { t: number; x: number; z: number }[] = []
watch(() => props.state, (st) => {
  const opp = st.characters.find((c) => c.team !== props.team)
  if (!opp) return
  const t = performance.now()
  oppHistory.push({ t, x: opp.pos.x, z: opp.pos.z })
  while (oppHistory.length && t - oppHistory[0].t > 300) oppHistory.shift()
})
function oppVelocity(): Vec2 | null {
  if (oppHistory.length < 2) return null
  const a = oppHistory[0], b = oppHistory[oppHistory.length - 1]
  const dt = (b.t - a.t) / 1000
  return dt < 0.08 ? null : { x: (b.x - a.x) / dt, z: (b.z - a.z) / dt }
}

/** Throw aim with aim assist applied (see throwGesture.assistYaw). */
function assistedAim(h: number | null, strength: number): { aim: Vec2; locked: boolean } {
  const y = h !== null && forward !== null ? angleDiff(h, forward) : 0
  const me = props.state.characters.find((c) => c.team === props.team)
  const opp = props.state.characters.find((c) => c.team !== props.team)
  if (!me || !opp) return { aim: yawToWorldAim(y, props.team), locked: false }
  const a = assistYaw(y, props.team, me.pos, opp.pos, oppVelocity(), strength, assistTuning)
  return { aim: yawToWorldAim(a.yaw, props.team), locked: a.locked }
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
  // Only new orientation events matter below; motion-only emits repeat the cached angles.
  if (s.orientation_ms === lastOrientationFed) return
  lastOrientationFed = s.orientation_ms
  let pitch: number | null = null
  if (s.alpha_deg !== null && s.beta_deg !== null && s.gamma_deg !== null) {
    const n = screenNormal(s.alpha_deg, s.beta_deg, s.gamma_deg)
    sideways.value = Math.hypot(n.x, n.y)
    const h = pointingHeading(s.alpha_deg, s.beta_deg, s.gamma_deg)
    if (h !== null) heading = h
    if (calHeadings && h !== null && sideways.value >= GRIP_OK) calHeadings.push(h)
    pitch = topPitch(s.alpha_deg, s.beta_deg, s.gamma_deg, side.value)
  }
  yawDeg.value = heading !== null && forward !== null ? angleDiff(heading, forward) * RAD : null
  locked.value = stage.value === 'live' && forward !== null && assistedAim(heading, 0.5).locked

  if (stage.value !== 'live') return
  const chop = detector.push(s.time_ms, pitch, heading)
  if (chop && holding.value) {
    holding.value = false // auto-release; a fresh press is needed for the next ball
    send('release', assistedAim(chop.heading ?? heading, chop.strength).aim, chop.strength)
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
  if (hs.length < CAL_MIN_SAMPLES) return failCalibration(`Turn the screen to face ${side.value} and hold still.`)
  // Circular mean, then spread around it.
  const mean = Math.atan2(hs.reduce((a, h) => a + Math.sin(h), 0), hs.reduce((a, h) => a + Math.cos(h), 0))
  const spread = Math.max(...hs.map((h) => Math.abs(angleDiff(h, mean)))) * RAD
  if (spread > CAL_MAX_SPREAD_DEG) return failCalibration('Too much movement — hold still while it sets forward.')
  forward = mean
  detector.reset()
  note.value = ''
  stage.value = 'live'
  setCalibrated(true)
}

function failCalibration(message: string): void {
  note.value = message
  if (forward !== null) {
    // A failed re-set keeps the previous forward: dropping calibration mid-round would make
    // PhoneShell send ready=false, and the simulation's device guard aborts the match.
    stage.value = 'live'
    return
  }
  stage.value = 'aim'
  setCalibrated(false)
}

function onPadDown(e: PointerEvent): void {
  if (stage.value !== 'live' || pointerId !== null || !sensorsFresh()) return
  pointerId = e.pointerId
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  holding.value = true
  detector.press(performance.now()) // forget earlier motion and ignore the thumb-press jolt
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
    forward = null // a hidden page loses calibration (03); the next Set forward starts fresh
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
        <li>Stand facing the TV. Hold the phone <strong>like a stick at chest height</strong>, <strong>screen facing sideways</strong> under your thumb.</li>
        <li>Point where you want to throw. <strong>Thumb on the screen</strong> to grab, then <strong>chop down toward the TV</strong> to throw.</li>
      </ol>
      <p v-if="note" class="note">{{ note }}</p>
      <button v-if="stage === 'start'" class="big" @click="start">Enable motion</button>
    </template>

    <template v-else-if="stage === 'aim' || stage === 'calibrating'">
      <h1>{{ stage === 'calibrating' ? 'Hold still…' : 'Set forward' }}</h1>
      <p>Face the TV, phone like a stick at chest height, <strong>screen facing {{ side }}</strong>.</p>
      <div class="hand">
        <button :class="{ on: side === 'left' }" @click="side = 'left'">Right hand<br><small>screen faces left</small></button>
        <button :class="{ on: side === 'right' }" @click="side = 'right'">Left hand<br><small>screen faces right</small></button>
      </div>
      <p v-if="sideways !== null && sideways < GRIP_OK" class="note">Turn the screen to face {{ side }}.</p>
      <p v-if="note" class="note">{{ note }}</p>
      <button class="big" :disabled="stage === 'calibrating'" @click="setForward">
        {{ stage === 'calibrating' ? 'Setting…' : 'Set forward' }}
      </button>
    </template>

    <!-- The whole live area is the Hold button: thumb anywhere on the screen grabs. -->
    <div
      v-else
      class="live"
      :class="{ holding, throw: flash === 'throw', cancel: flash === 'cancel', idle: !active }"
      @pointerdown="onPadDown"
      @pointerup="onPadUp"
      @pointercancel="onPadUp"
      @lostpointercapture="onPadUp"
    >
      <div class="status">
        <span :class="{ on: hasBall }">{{ hasBall ? '● Ball' : '○ No ball' }}</span>
        <span>aim {{ yawDeg === null ? '—' : `${Math.round(yawDeg)}°` }}</span>
        <span v-if="locked" class="lock">LOCKED</span>
        <button class="reset" @pointerdown.stop @click="setForward">Re-set forward</button>
      </div>
      <p v-if="note" class="note">{{ note }} (kept the old forward)</p>
      <div class="dial" :class="{ locked }" aria-hidden="true">
        <div class="needle" :style="{ transform: `rotate(${Math.max(-75, Math.min(75, yawDeg ?? 0))}deg)` }" />
      </div>
      <div class="label">{{ padText }}</div>
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
.hand {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.hand button {
  flex: 1;
  padding: 0.6rem;
  font: inherit;
  border: 2px solid #444;
  border-radius: 10px;
  background: #1c1c1c;
  color: #ccc;
}
.hand button.on {
  border-color: var(--team);
  color: #fff;
}
.big:disabled {
  opacity: 0.5;
}
.live {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  /* Fill the phone below PhoneShell's header so a thumb anywhere lands on it. */
  min-height: calc(100dvh - 9rem);
  margin: -0.5rem;
  padding: 0.75rem;
  box-sizing: border-box;
  border-radius: 18px;
  border: 3px solid var(--team);
  background: #161616;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
}
.live.holding {
  background: var(--team);
  color: #000;
}
.live.holding .status {
  color: #000;
}
.live.throw {
  background: #3c6;
  color: #000;
}
.live.cancel {
  background: #333;
}
.live.idle {
  opacity: 0.6;
}
.label {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.8rem;
  font-weight: 800;
  text-align: center;
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
.lock {
  color: #3c6;
  font-weight: 800;
}
.live.holding .lock {
  color: #000;
}
.dial.locked .needle {
  background: #3c6;
  box-shadow: 0 0 12px #3c6;
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
</style>
