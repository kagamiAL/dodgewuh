<script setup lang="ts">
// /sensors → Arms tuning: see the chop gesture live and tune it on a real phone, no backend.
//
// Shows the top-of-phone pitch (90 = up, 0 = at the TV), a 2 s pitch graph and every detected
// chop (no Hold needed here). The sliders edit chopTuning, which ArmsController reads live, so
// switching to the Practice tab uses whatever you set here (until the page reloads).

import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { type SensorSample, type SensorService } from '@/sensors/sensorService'
import {
  DEFAULT_CHOP, MIN_SIDEWAYS, chopTuning, createChopDetector, pointingHeading, screenNormal, topPitch,
  type Chop, type ScreenSide,
} from '@/controllers/arms/throwGesture'

const props = defineProps<{ sensors: SensorService }>()

const GRAPH_MS = 2000
const RAD = 180 / Math.PI

const permission = ref('unknown')
const side = ref<ScreenSide>('left')
const tuning = reactive(chopTuning) // writes go straight to the shared object
const pitch = ref<number | null>(null)
const drop = ref(0)
const sideways = ref<number | null>(null)
const graph = ref<{ t: number; p: number }[]>([])
const chops = ref<(Chop & { n: number })[]>([])
const flash = ref(false)

const detector = createChopDetector(() => chopTuning)
let unsubscribe: (() => void) | null = null
let lastOrientationFed: number | null = null
let n = 0
let flashTimer: ReturnType<typeof setTimeout> | null = null

function onSample(s: SensorSample): void {
  if (s.orientation_ms === lastOrientationFed) return
  lastOrientationFed = s.orientation_ms
  if (s.alpha_deg === null || s.beta_deg === null || s.gamma_deg === null) {
    pitch.value = null
    detector.push(s.time_ms, null, null)
    return
  }
  const nrm = screenNormal(s.alpha_deg, s.beta_deg, s.gamma_deg)
  sideways.value = Math.hypot(nrm.x, nrm.y)
  const p = topPitch(s.alpha_deg, s.beta_deg, s.gamma_deg, side.value)
  pitch.value = p
  const chop = detector.push(s.time_ms, p, pointingHeading(s.alpha_deg, s.beta_deg, s.gamma_deg))
  drop.value = detector.drop
  if (p !== null) {
    const cut = s.time_ms - GRAPH_MS
    graph.value = [...graph.value.filter((g) => g.t >= cut), { t: s.time_ms, p }]
  }
  if (chop) {
    chops.value = [{ ...chop, n: ++n }, ...chops.value].slice(0, 20)
    flash.value = true
    if (flashTimer) clearTimeout(flashTimer)
    flashTimer = setTimeout(() => (flash.value = false), 400)
  }
}

function enable(): void {
  // Must start synchronously in the tap (iOS).
  props.sensors.requestPermissionFromGesture().then((p) => {
    permission.value = p
    if (p === 'granted') unsubscribe ??= props.sensors.subscribe(onSample)
  })
}

function resetTuning(): void {
  Object.assign(tuning, DEFAULT_CHOP)
}

onBeforeUnmount(() => {
  if (flashTimer) clearTimeout(flashTimer)
  unsubscribe?.()
})

// Graph: x = time (0..GRAPH_MS), y = pitch from 150 (top) to -90 (bottom).
const P_TOP = 150
const P_BOT = -90
const gy = (p: number) => P_TOP - Math.max(P_BOT, Math.min(P_TOP, p))
const graphPoints = computed(() => {
  const end = graph.value.at(-1)?.t ?? 0
  return graph.value.map((g) => `${(GRAPH_MS - (end - g.t)).toFixed(0)},${gy(g.p).toFixed(1)}`).join(' ')
})
// Needle for the side view: 0° = pointing right (at the TV), 90° = up.
const needle = computed(() => {
  const p = (pitch.value ?? 90) / RAD
  return { x: Math.cos(p) * 40, y: -Math.sin(p) * 40 }
})
function f(v: number | null | undefined, d = 0): string {
  return v === null || v === undefined ? '—' : v.toFixed(d)
}
</script>

<template>
  <section class="arms">
    <button v-if="permission !== 'granted'" class="big" @click="enable">Enable motion</button>
    <p v-if="permission === 'denied' || permission === 'unsupported'" class="bad">
      Motion {{ permission }}. Reload over HTTPS in Safari and tap Allow.
    </p>

    <template v-if="permission === 'granted'">
      <div class="hand">
        <button :class="{ on: side === 'left' }" @click="side = 'left'">Right hand · screen left</button>
        <button :class="{ on: side === 'right' }" @click="side = 'right'">Left hand · screen right</button>
      </div>
      <p v-if="sideways !== null && sideways < MIN_SIDEWAYS + 0.35" class="bad">Turn the screen to face sideways.</p>

      <section class="card" :class="{ flash }">
        <h3>Top of phone: {{ f(pitch) }}° · drop {{ f(drop) }}° / {{ tuning.minDropDeg }}°</h3>
        <p class="hint">Side view, TV to the right. Chop down toward the TV to throw.</p>
        <svg viewBox="-50 -50 100 60" class="side">
          <line x1="-45" y1="0" x2="45" y2="0" class="ground" />
          <text x="44" y="-3" class="tv">TV →</text>
          <line x1="0" y1="0" :x2="needle.x" :y2="needle.y" class="needle" />
        </svg>
        <div class="bar"><div class="fill" :style="{ width: `${Math.min(100, (drop / tuning.minDropDeg) * 100)}%` }" /></div>
      </section>

      <section class="card">
        <h3>Pitch, last 2 s (red = 0°, at the TV; grey = 90°, straight up)</h3>
        <svg :viewBox="`0 0 ${GRAPH_MS} ${P_TOP - P_BOT}`" preserveAspectRatio="none" class="graph">
          <line x1="0" :y1="gy(90)" :x2="GRAPH_MS" :y2="gy(90)" class="up" />
          <line x1="0" :y1="gy(0)" :x2="GRAPH_MS" :y2="gy(0)" class="level" />
          <polyline :points="graphPoints" class="trace" />
        </svg>
      </section>

      <section class="card">
        <h3>Tuning (applies to Practice too, until reload)</h3>
        <label class="slider">must chop down at least {{ tuning.minDropDeg }}°
          <input v-model.number="tuning.minDropDeg" type="range" min="30" max="150" step="5">
        </label>
        <label class="slider">…within {{ tuning.windowMs }} ms
          <input v-model.number="tuning.windowMs" type="range" min="150" max="1000" step="25">
        </label>
        <label class="slider">full strength at {{ tuning.fullStrengthRate }}°/s
          <input v-model.number="tuning.fullStrengthRate" type="range" min="200" max="1500" step="25">
        </label>
        <button class="reset" @click="resetTuning">Reset to defaults</button>
      </section>

      <section v-if="chops.length" class="card small">
        <h3>Chops detected</h3>
        <table>
          <tr><th>#</th><th>from°</th><th>to°</th><th>drop°</th><th>ms</th><th>°/s</th><th>str</th></tr>
          <tr v-for="c in chops" :key="c.n">
            <td>{{ c.n }}</td>
            <td>{{ f(c.from_deg) }}</td>
            <td>{{ f(c.to_deg) }}</td>
            <td>{{ f(c.drop_deg) }}</td>
            <td>{{ f(c.duration_ms) }}</td>
            <td>{{ f(c.rate) }}</td>
            <td>{{ f(c.strength, 2) }}</td>
          </tr>
        </table>
      </section>
    </template>
  </section>
</template>

<style scoped>
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
.hand {
  display: flex;
  gap: 0.5rem;
}
.hand button {
  flex: 1;
  padding: 0.6rem;
  font: inherit;
  font-size: 0.85rem;
  border: 2px solid #444;
  border-radius: 10px;
  background: #1c1c1c;
  color: #ccc;
}
.hand button.on {
  border-color: #3c6;
  color: #fff;
}
.card {
  margin-top: 1rem;
  padding: 0.75rem;
  border-radius: 10px;
  background: #1c1c1c;
  transition: background 0.2s;
}
.card.flash {
  background: #2a5;
}
.card h3 {
  margin: 0 0 0.5rem;
  font-size: 0.95rem;
}
.hint {
  margin: 0 0 0.5rem;
  color: #999;
  font-size: 0.8rem;
}
.side {
  width: 100%;
  max-height: 22vh;
}
.ground {
  stroke: #555;
  stroke-width: 0.8;
}
.tv {
  fill: #888;
  font-size: 6px;
  text-anchor: end;
}
.needle {
  stroke: #6cf;
  stroke-width: 4;
  stroke-linecap: round;
}
.bar {
  height: 10px;
  border-radius: 5px;
  background: #333;
  overflow: hidden;
}
.fill {
  height: 100%;
  background: #fc3;
}
.graph {
  width: 100%;
  height: 100px;
  background: #111;
}
.trace {
  fill: none;
  stroke: #6cf;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}
.level {
  stroke: #e55;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.up {
  stroke: #666;
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
.reset {
  margin-top: 0.75rem;
  padding: 0.4rem 0.75rem;
  border: 1px solid #444;
  border-radius: 8px;
  background: #222;
  color: #ccc;
  font: inherit;
}
.small {
  font: 12px/1.4 ui-monospace, monospace;
  color: #bbb;
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
