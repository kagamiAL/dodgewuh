<script setup lang="ts">
// /sensors → Arms: tune throw detection and pointing aim on a real phone, no backend.
//
// Grip: hold the phone like a stick at chest height, screen facing left, facing the TV. Tap "Set forward". The arrow follows where the phone points.
// Hold the pad, flick: a gyro spike auto-releases with the aim read at the flick (not frozen).
// Lifting without a flick cancels. Flicks without Hold never throw; they are logged ("no hold") only for tuning.
// Messages go through the recording Transport, which flags anything the server would reject.

import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import type { Team, Vec2 } from '@/contracts/pending'
import { SENSOR_STALE_MS, type SensorSample, type SensorService } from '@/sensors/sensorService'
import {
  DEFAULT_SWING, MAX_YAW_DEG, MIN_SIDEWAYS, angleDiff, screenNormal, createSwingDetector, pointingHeading, rotationSpeed,
  yawToWorldAim, type Swing, type SwingConfig,
} from '@/controllers/arms/throwGesture'
import { createRecordingTransport, type SentMessage } from './recordingTransport'

const props = defineProps<{ sensors: SensorService }>()

const SEND_MS = 50 // 20 Hz aim (03)
const SPARK_MS = 2000
const SPARK_MAX = 1200 // deg/s at top of the graph
const RAD = 180 / Math.PI

type AimSource = 'start' | 'peak' | 'end'

const team = ref<Team>(1)
const permission = ref('unknown')
const config = reactive<SwingConfig>({ ...DEFAULT_SWING })
const aimSource = ref<AimSource>('peak')

const raw = ref<SensorSample | null>(null)
const speed = ref<number | null>(null)
const heading = ref<number | null>(null)
const forward = ref<number | null>(null)
const holding = ref(false)
const swinging = ref(false)
const spark = ref<{ t: number; v: number }[]>([])

interface ThrowRow {
  n: number
  held: boolean
  swing: Swing
  yaw_deg: { start: number | null; peak: number | null; end: number | null }
  sent: Vec2 | null
}
const throws = ref<ThrowRow[]>([])
const sentCount = ref(0)
const problems = ref<string[]>([])
const msgLog = ref<string[]>([])

const transport = createRecordingTransport(onSent)
const detector = createSwingDetector(() => config)

let unsubscribe: (() => void) | null = null
let sendTimer: ReturnType<typeof setInterval> | null = null
let pointerId: number | null = null
let throwN = 0
let lastMotionFed: number | null = null

// Horizontal length of the screen normal: 1 = screen facing straight sideways, 0 = facing up/down.
const sideways = computed(() => {
  const s = raw.value
  if (!s || s.alpha_deg === null || s.beta_deg === null || s.gamma_deg === null) return null
  const n = screenNormal(s.alpha_deg, s.beta_deg, s.gamma_deg)
  return Math.hypot(n.x, n.y)
})
const yaw = computed(() => (heading.value !== null && forward.value !== null ? angleDiff(heading.value, forward.value) : null))
const clampedYawDeg = computed(() => (yaw.value === null ? null : Math.max(-MAX_YAW_DEG, Math.min(MAX_YAW_DEG, yaw.value * RAD))))

function yawDeg(h: number | null): number | null {
  return h !== null && forward.value !== null ? angleDiff(h, forward.value) * RAD : null
}

function currentAim(h: number | null = heading.value): Vec2 {
  const y = h !== null && forward.value !== null ? angleDiff(h, forward.value) : 0
  return yawToWorldAim(y, team.value)
}

function send(action: 'aim' | 'press' | 'release' | 'cancel', aim: Vec2, strength: number | null = null): void {
  transport.send({ v: 1, type: 'input.arms', payload: { seq: transport.nextInputSeq(), epoch: 1, aim, action, strength } })
}

function onSent({ message, problem }: SentMessage): void {
  sentCount.value++
  if (problem) problems.value = [problem, ...problems.value].slice(0, 10)
  if (message.type !== 'input.arms') return
  const p = message.payload
  // Hemisphere rule from 02, which the transport can't check without the team.
  const zOk = team.value === 1 ? p.aim.z >= 0.2 : p.aim.z <= -0.2
  if (!zOk) problems.value = [`aim ${p.aim.x.toFixed(2)},${p.aim.z.toFixed(2)} outside team hemisphere`, ...problems.value].slice(0, 10)
  if (p.action !== 'aim') {
    const s = p.strength === null ? '' : ` strength ${p.strength.toFixed(2)}`
    msgLog.value = [`#${p.seq} ${p.action} aim ${p.aim.x.toFixed(2)},${p.aim.z.toFixed(2)}${s}`, ...msgLog.value].slice(0, 12)
  }
}

function fresh(ms: number | null, now: number): boolean {
  return ms !== null && now - ms < SENSOR_STALE_MS
}

function onSample(s: SensorSample): void {
  raw.value = s
  const now = s.time_ms
  const orientOk = fresh(s.orientation_ms, now) && s.alpha_deg !== null && s.beta_deg !== null && s.gamma_deg !== null
  const h = orientOk ? pointingHeading(s.alpha_deg!, s.beta_deg!, s.gamma_deg!) : null
  if (h !== null) heading.value = h
  const v = fresh(s.motion_ms, now) ? rotationSpeed(s.rotation_rate) : null
  speed.value = v

  // Only feed the detector on new motion events; orientation-only emits repeat the cached gyro value.
  if (s.motion_ms !== lastMotionFed) {
    lastMotionFed = s.motion_ms
    const swing = detector.push(now, v, h ?? heading.value)
    swinging.value = detector.swinging
    if (swing) onSwing(swing)
    if (v !== null) {
      const cut = now - SPARK_MS
      spark.value = [...spark.value.filter((p) => p.t >= cut), { t: now, v }]
    }
  }

  if (holding.value && (!orientOk || v === null)) cancelHold('sensor stale')
}

function onSwing(swing: Swing): void {
  const held = holding.value
  const pick = { start: swing.heading_start, peak: swing.heading_peak, end: swing.heading_end }[aimSource.value]
  let sent: Vec2 | null = null
  if (held && forward.value !== null) {
    sent = currentAim(pick)
    send('release', sent, swing.strength)
    holding.value = false // auto-release: a fresh press is required for the next throw
  }
  throws.value = [{
    n: ++throwN, held, swing, sent,
    yaw_deg: { start: yawDeg(swing.heading_start), peak: yawDeg(swing.heading_peak), end: yawDeg(swing.heading_end) },
  }, ...throws.value].slice(0, 20)
}

function enable(): void {
  // Must start synchronously in the tap (iOS).
  props.sensors.requestPermissionFromGesture().then((p) => {
    permission.value = p
    if (p === 'granted') unsubscribe ??= props.sensors.subscribe(onSample)
  })
}

// Neutral pose must be clearly sideways so the heading is well defined; top tilt doesn't matter.
const GRIP_OK = 0.7
const gripOk = computed(() => sideways.value !== null && sideways.value >= GRIP_OK && heading.value !== null)

function setForward(): void {
  if (gripOk.value) forward.value = heading.value
}

function onPadDown(e: PointerEvent): void {
  if (pointerId !== null || forward.value === null || speed.value === null) return
  pointerId = e.pointerId
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  holding.value = true
  detector.reset()
  send('press', currentAim())
  sendTimer ??= setInterval(() => {
    if (holding.value) send('aim', currentAim())
  }, SEND_MS)
}

function onPadUp(e: PointerEvent): void {
  if (e.pointerId !== pointerId) return
  pointerId = null
  // A swing already released; otherwise lifting without a flick is a cancel, never a throw.
  if (holding.value) cancelHold('lifted without a flick')
}

function cancelHold(_why: string): void {
  if (!holding.value) return
  holding.value = false
  send('cancel', currentAim())
}

function onVisibility(): void {
  if (document.hidden) cancelHold('page hidden')
}
document.addEventListener('visibilitychange', onVisibility)

onBeforeUnmount(() => {
  cancelHold('unmount')
  if (sendTimer) clearInterval(sendTimer)
  document.removeEventListener('visibilitychange', onVisibility)
  unsubscribe?.()
})

// ---- display helpers (SVG: team-local, x = right, y = −forward, metres) ----
const THROWER = { x: 0, y: 6 }
const RAY = 11
function rayEnd(yaw_deg: number | null): { x: number; y: number } {
  const y = Math.max(-MAX_YAW_DEG, Math.min(MAX_YAW_DEG, yaw_deg ?? 0)) / RAD
  return { x: THROWER.x + Math.sin(y) * RAY, y: THROWER.y - Math.cos(y) * RAY }
}
const liveEnd = computed(() => rayEnd(clampedYawDeg.value))
const sparkPoints = computed(() => {
  const end = spark.value.at(-1)?.t ?? 0
  return spark.value.map((p) => `${(SPARK_MS - (end - p.t)).toFixed(0)},${(SPARK_MAX - Math.min(p.v, SPARK_MAX)).toFixed(0)}`).join(' ')
})
function f(v: number | null | undefined, d = 0): string {
  return v === null || v === undefined ? '—' : v.toFixed(d)
}
</script>

<template>
  <section class="arms">
    <div class="row">
      <label>Team
        <select v-model.number="team">
          <option :value="1">1 (blue)</option>
          <option :value="2">2 (orange)</option>
        </select>
      </label>
      <label>Aim from
        <select v-model="aimSource">
          <option value="start">swing start</option>
          <option value="peak">swing peak</option>
          <option value="end">swing end</option>
        </select>
      </label>
    </div>

    <button v-if="permission !== 'granted'" class="big" @click="enable">Enable motion</button>
    <p v-if="permission === 'denied' || permission === 'unsupported'" class="bad">
      Motion {{ permission }}. Reload over HTTPS in Safari and tap Allow.
    </p>

    <template v-else>
      <p class="grip">
        Stand facing the TV. Hold the phone <strong>like a stick at chest height</strong>:
        <strong>screen facing left</strong>, top pointing up or tipped toward the TV (the angle doesn't matter).
      </p>
      <p v-if="sideways !== null && sideways < MIN_SIDEWAYS + 0.15" class="bad">
        Screen is facing too far up/down — turn it to face sideways.
      </p>
      <button class="big secondary" :disabled="!gripOk" @click="setForward">
        {{ !gripOk ? 'Turn the screen to face left' : forward === null ? 'Facing the TV? Tap: Set forward' : 'Re-set forward' }}
      </button>

      <div
        class="pad"
        :class="{ holding, swinging, off: forward === null }"
        @pointerdown="onPadDown"
        @pointerup="onPadUp"
        @pointercancel="onPadUp"
        @lostpointercapture="onPadUp"
      >
        {{ forward === null ? 'Set forward first' : holding ? 'Holding — flick to throw' : 'Hold here' }}
      </div>

      <section class="card">
        <h3>Aim (top-down, forward = up) · yaw {{ f(yaw === null ? null : yaw * RAD) }}°</h3>
        <svg viewBox="-7 -6 14 13" class="court">
          <rect x="-6" y="-5" width="12" height="11.5" class="lines" />
          <line
            v-for="t in throws.filter((t) => t.held).slice(0, 8)"
            :key="t.n"
            :x1="THROWER.x" :y1="THROWER.y"
            :x2="rayEnd(t.yaw_deg[aimSource]).x" :y2="rayEnd(t.yaw_deg[aimSource]).y"
            class="past"
          />
          <line v-if="forward !== null" :x1="THROWER.x" :y1="THROWER.y" :x2="liveEnd.x" :y2="liveEnd.y" class="live" />
          <circle :cx="THROWER.x" :cy="THROWER.y" r="0.45" class="dot" />
        </svg>
      </section>

      <section class="card">
        <h3>Gyro {{ f(speed) }}°/s {{ swinging ? '· SWING' : '' }}</h3>
        <svg :viewBox="`0 0 ${SPARK_MS} ${SPARK_MAX}`" preserveAspectRatio="none" class="spark">
          <line x1="0" :y1="SPARK_MAX - config.threshold" :x2="SPARK_MS" :y2="SPARK_MAX - config.threshold" class="thresh" />
          <line x1="0" :y1="SPARK_MAX - config.threshold * config.rearmRatio" :x2="SPARK_MS" :y2="SPARK_MAX - config.threshold * config.rearmRatio" class="rearm" />
          <polyline :points="sparkPoints" class="trace" />
        </svg>
        <label class="slider">threshold {{ config.threshold }}°/s
          <input v-model.number="config.threshold" type="range" min="80" max="600" step="10">
        </label>
        <label class="slider">full strength at {{ config.fullStrengthRate }}°/s
          <input v-model.number="config.fullStrengthRate" type="range" :min="config.threshold + 50" max="1500" step="25">
        </label>
      </section>

      <section v-if="throws.length" class="card small">
        <h3>Swings (yaw° at start / peak / end)</h3>
        <table>
          <tr><th>#</th><th>kind</th><th>peak°/s</th><th>str</th><th>start</th><th>peak</th><th>end</th><th>ms</th></tr>
          <tr v-for="t in throws" :key="t.n" :class="t.held ? 'ok' : ''">
            <td>{{ t.n }}</td>
            <td>{{ t.held ? 'THROW' : 'no hold' }}</td>
            <td>{{ f(t.swing.peak_rate) }}</td>
            <td>{{ f(t.swing.strength, 2) }}</td>
            <td>{{ f(t.yaw_deg.start) }}</td>
            <td>{{ f(t.yaw_deg.peak) }}</td>
            <td>{{ f(t.yaw_deg.end) }}</td>
            <td>{{ f(t.swing.end_ms - t.swing.start_ms) }}</td>
          </tr>
        </table>
      </section>

      <section class="card small">
        <p>α {{ f(raw?.alpha_deg, 1) }} · β {{ f(raw?.beta_deg, 1) }} · γ {{ f(raw?.gamma_deg, 1) }} · heading {{ f(heading === null ? null : heading * RAD, 1) }}° · sideways {{ f(sideways, 2) }}</p>
        <p>rate α {{ f(raw?.rotation_rate?.alpha) }} β {{ f(raw?.rotation_rate?.beta) }} γ {{ f(raw?.rotation_rate?.gamma) }} · sent {{ sentCount }}</p>
        <p v-for="(p, i) in problems" :key="'p' + i" class="bad">rejected: {{ p }}</p>
        <p v-for="(l, i) in msgLog" :key="'m' + i">{{ l }}</p>
      </section>
    </template>
  </section>
</template>

<style scoped>
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.25rem;
  margin-bottom: 0.75rem;
}
.big {
  width: 100%;
  min-height: 56px;
  margin-bottom: 0.75rem;
  font-size: 1.1rem;
  font-weight: 700;
  border: 0;
  border-radius: 12px;
  background: #3c6;
  color: #000;
}
.big.secondary {
  background: #333;
  color: #eee;
}
.grip {
  margin: 0 0 0.5rem;
  color: #ccc;
}
.pad {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  border-radius: 16px;
  background: #223;
  color: #ccd;
  font-size: 1.3rem;
  font-weight: 700;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
}
.pad.holding {
  background: #2a5;
  color: #000;
}
.pad.swinging {
  background: #fc3;
}
.pad.off {
  opacity: 0.4;
}
.card {
  margin-top: 1rem;
  padding: 0.75rem;
  border-radius: 10px;
  background: #1c1c1c;
}
.card h3 {
  margin: 0 0 0.5rem;
  font-size: 0.95rem;
}
.small {
  font: 12px/1.4 ui-monospace, monospace;
  color: #bbb;
}
.small p {
  margin: 0.2rem 0;
}
.court {
  width: 100%;
  max-height: 40vh;
}
.lines {
  fill: #0d1a0d;
  stroke: #555;
  stroke-width: 0.08;
}
.live {
  stroke: #3c6;
  stroke-width: 0.15;
  stroke-linecap: round;
}
.past {
  stroke: #fc3;
  stroke-width: 0.06;
  opacity: 0.7;
}
.dot {
  fill: #3c6;
}
.spark {
  width: 100%;
  height: 90px;
  background: #111;
}
.trace {
  fill: none;
  stroke: #6cf;
  stroke-width: 12;
  vector-effect: non-scaling-stroke;
}
.thresh {
  stroke: #e55;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.rearm {
  stroke: #555;
  stroke-dasharray: 4 4;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.slider {
  display: block;
  margin-top: 0.5rem;
  font-size: 0.85rem;
}
.slider input {
  width: 100%;
}
.ok {
  color: #3c6;
}
.bad {
  color: #e55;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th, td {
  text-align: right;
  padding: 0 0.25rem;
}
</style>
