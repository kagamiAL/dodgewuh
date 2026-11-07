<script setup lang="ts">
// /sensors: run the real LegsController without a backend. Outgoing input.legs messages go to a
// recording Transport, move a dot on a local court at the 02 speed (3.5 m/s), and can be scored
// against spoken cues ("Face left and jog" … "Stop") while the phone is in the pocket.

import { computed, onBeforeUnmount, reactive, ref, shallowRef } from 'vue'
import type { State, Team } from '@/contracts/pending'
import { createSensorService } from '@/sensors/sensorService'
import LegsController from '@/controllers/legs/LegsController.vue'
import { jogTuning } from '@/controllers/legs/jogTracker'
import { beep, say } from '@/controllers/legs/voice'
import { createRecordingTransport, type SentMessage } from './recordingTransport'

type Dir = 'forward' | 'left' | 'right' | 'back'

const SPEED = 3.5 // m/s, 02
const HALF_W = 6
const HALF_D = 9
const JOG_MS = 5000
const STOP_MS = 3000
const JOG_GRACE_MS = 1500 // time to turn and get jogging before a jog cue is judged
const STOP_GRACE_MS = 1200
const CUE_TEXT: Record<Dir, string> = {
  forward: 'Face the screen and jog',
  left: 'Face left and jog',
  right: 'Face right and jog',
  back: 'Face away from the screen and jog',
}

const team = ref<Team>(1)
const scoredTest = ref(true)
const speakMoves = ref(false)
const calibrated = ref(false)
const availability = ref('unknown')
const sent = ref(0)
const problems = ref<string[]>([])
const log = ref<string[]>([])
const pos = ref({ r: 0, f: 0 }) // team-local metres: +right, +forward
const trail = ref('')
const tuning = reactive(jogTuning) // edits apply to the running tracker

interface Cue {
  text: string
  at: number
  end: number
  expect: Dir | 'still'
  result: 'pending' | 'ok' | 'bad'
  detail: string
}
const cues = ref<Cue[]>([])
const testState = ref<'idle' | 'running' | 'done'>('idle')
const score = computed(() => cues.value.filter((c) => c.result === 'ok').length)

const sensors = createSensorService()
const transport = createRecordingTransport(onSent)
const state = shallowRef<State>({
  tick: 0, epoch: 1, round: 1, phase: 'active', remaining_ms: 60000, phase_remaining_ms: null,
  score: { t1: 0, t2: 0 },
  characters: [
    { team: 1, pos: { x: 0, z: -6 }, aim: { x: 0, z: 1 }, held_ball_id: null },
    { team: 2, pos: { x: 0, z: 6 }, aim: { x: 0, z: -1 }, held_ball_id: null },
  ],
  balls: [], assignments: [], assignment_version: 1, result: null, winner: null,
})

let lastAt: number | null = null
let lastDir: Dir | null = null
const timeline: { at: number; dir: Dir | null }[] = []
const timers = new Set<ReturnType<typeof setTimeout>>()
function later(ms: number, fn: () => void): void {
  const id = setTimeout(() => {
    timers.delete(id)
    fn()
  }, ms)
  timers.add(id)
}

function localDir(r: number, f: number): Dir | null {
  if (r === 0 && f === 0) return null
  return Math.abs(r) >= Math.abs(f) ? (r > 0 ? 'right' : 'left') : f > 0 ? 'forward' : 'back'
}

function onSent({ at, message, problem }: SentMessage): void {
  sent.value++
  if (problem) problems.value = [problem, ...problems.value].slice(0, 10)
  if (message.type !== 'input.legs') return
  const s = team.value === 1 ? 1 : -1
  const r = message.payload.move.x * s
  const f = message.payload.move.z * s
  // Integrate like the server would: latest move × speed over the time since the previous message.
  if (lastAt !== null) {
    const dt = Math.min((at - lastAt) / 1000, 0.1)
    pos.value = {
      r: Math.max(-HALF_W, Math.min(HALF_W, pos.value.r + r * SPEED * dt)),
      f: Math.max(-HALF_D, Math.min(HALF_D, pos.value.f + f * SPEED * dt)),
    }
  }
  lastAt = at
  const dir = localDir(r, f)
  timeline.push({ at, dir })
  if (dir !== lastDir) {
    trail.value += ` ${pos.value.r.toFixed(2)},${(-pos.value.f).toFixed(2)}`
    log.value = [`${dir ?? 'stop'}  @${(at / 1000).toFixed(1)}s`, ...log.value].slice(0, 30)
    if (speakMoves.value && testState.value !== 'running') say(dir ?? 'stop')
  }
  lastDir = dir
}

function judge(cue: Cue): void {
  const isStop = cue.text === 'Stop'
  const grace = isStop ? STOP_GRACE_MS : cue.expect === 'still' ? 500 : JOG_GRACE_MS
  const window = timeline.filter((m) => m.at >= cue.at + grace && m.at < cue.end)
  const moving = window.filter((m) => m.dir !== null)
  if (cue.expect === 'still') {
    const ok = window.length > 0 && moving.length / window.length <= 0.1
    cue.result = ok ? 'ok' : 'bad'
    cue.detail = `${Math.round((100 * moving.length) / (window.length || 1))}% moving`
  } else {
    const counts = new Map<Dir, number>()
    for (const m of moving) counts.set(m.dir!, (counts.get(m.dir!) ?? 0) + 1)
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null
    const firstMove = timeline.find((m) => m.at >= cue.at && m.dir !== null)
    const ok = window.length > 0 && moving.length / window.length >= 0.6 && top === cue.expect
    cue.result = ok ? 'ok' : 'bad'
    cue.detail = `${top ?? 'none'}, ${Math.round((100 * moving.length) / (window.length || 1))}% moving` +
      (firstMove ? `, started after ${((firstMove.at - cue.at) / 1000).toFixed(1)}s` : '')
  }
  cues.value = [...cues.value]
  beep(cue.result === 'ok' ? 1400 : 250, 150)
}

function runTest(): void {
  cues.value = []
  testState.value = 'running'
  const order = (['forward', 'left', 'right', 'back'] as Dir[]).sort(() => Math.random() - 0.5)
  const plan: { text: string; ms: number; expect: Cue['expect'] }[] = [
    { text: 'Stand still and lift one knee a little', ms: 3000, expect: 'still' },
    ...order.flatMap((d) => [
      { text: CUE_TEXT[d], ms: JOG_MS, expect: d },
      { text: 'Stop', ms: STOP_MS, expect: 'still' as const },
    ]),
  ]
  let t = 2500 // let "Go" finish
  for (const step of plan) {
    later(t, () => {
      say(step.text)
      const now = performance.now()
      const cue: Cue = { text: step.text, at: now, end: now + step.ms, expect: step.expect, result: 'pending', detail: '' }
      cues.value = [...cues.value, cue]
      later(step.ms, () => judge(cue))
    })
    t += step.ms
  }
  later(t + 100, () => {
    testState.value = 'done'
    say(`Score: ${score.value} out of ${cues.value.length}`)
  })
}

function onCalibrated(v: boolean): void {
  calibrated.value = v
  if (v) {
    pos.value = { r: 0, f: 0 }
    trail.value = '0,0'
    timeline.length = 0
    if (scoredTest.value) runTest()
  } else if (testState.value === 'running') {
    for (const id of timers) clearTimeout(id)
    timers.clear()
    testState.value = 'done'
  }
}

onBeforeUnmount(() => {
  for (const id of timers) clearTimeout(id)
  sensors.stop()
})
</script>

<template>
  <main class="playground">
    <h2>Sensor playground · Legs (jog + face)</h2>
    <div class="row">
      <label>Team
        <select v-model.number="team" :disabled="calibrated">
          <option :value="1">1 (blue)</option>
          <option :value="2">2 (orange)</option>
        </select>
      </label>
      <label><input v-model="scoredTest" type="checkbox"> scored test after "Go"</label>
      <label><input v-model="speakMoves" type="checkbox"> speak moves</label>
    </div>

    <LegsController
      :transport="transport"
      :sensors="sensors"
      member_id="playground"
      :team="team"
      :epoch="1"
      :assignment_version="1"
      :state="state"
      :connected="true"
      @calibrated="onCalibrated"
      @availability="availability = $event"
    />

    <section v-if="cues.length" class="card">
      <h3>Scored test: {{ score }} / {{ cues.length }} {{ testState === 'running' ? '(running)' : '' }}</h3>
      <table>
        <tr v-for="(c, i) in cues" :key="i" :class="c.result">
          <td>{{ c.text }}</td><td>{{ c.result === 'pending' ? '…' : c.detail }}</td>
        </tr>
      </table>
    </section>

    <section class="card">
      <h3>Court (your half, forward = up)</h3>
      <svg :viewBox="`${-HALF_W} ${-HALF_D} ${HALF_W * 2} ${HALF_D * 2}`" class="court">
        <rect :x="-HALF_W" :y="-HALF_D" :width="HALF_W * 2" :height="HALF_D * 2" class="lines" />
        <polyline :points="trail" class="trail" />
        <circle :cx="pos.r" :cy="-pos.f" r="0.45" class="dot" />
      </svg>
    </section>

    <section class="card tuning">
      <h3>Tuning (applies live)</h3>
      <label>start jogging above <input v-model.number="tuning.start_rms" type="number" step="0.5"> m/s²</label>
      <label>…held for <input v-model.number="tuning.start_hold_ms" type="number" step="50"> ms</label>
      <label>stop below <input v-model.number="tuning.stop_rms" type="number" step="0.5"> m/s²</label>
      <label>…held for <input v-model.number="tuning.stop_hold_ms" type="number" step="50"> ms</label>
      <label>after stopping, ignore turns slower than <input v-model.number="tuning.settle_turn_dps" type="number" step="5"> °/s</label>
      <label>…for <input v-model.number="tuning.settle_ms" type="number" step="100"> ms</label>
    </section>

    <section class="card small">
      <p>availability: {{ availability }} · calibrated: {{ calibrated }} · messages sent: {{ sent }}</p>
      <p v-for="(p, i) in problems" :key="i" class="bad">rejected: {{ p }}</p>
      <p v-for="(l, i) in log" :key="i">{{ l }}</p>
    </section>
  </main>
</template>

<style scoped>
.playground {
  padding: 0 1rem 3rem;
  max-width: 32rem;
  margin: 0 auto;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.25rem;
  margin-bottom: 0.75rem;
}
.card {
  margin-top: 1rem;
  padding: 0.75rem;
  border-radius: 10px;
  background: #1c1c1c;
}
.tuning label {
  display: block;
  margin: 0.3rem 0;
}
.tuning input {
  width: 5em;
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
  max-height: 50vh;
}
.lines {
  fill: #0d1a0d;
  stroke: #555;
  stroke-width: 0.08;
}
.trail {
  fill: none;
  stroke: #666;
  stroke-width: 0.06;
}
.dot {
  fill: #3c6;
}
.ok {
  color: #3c6;
}
.bad {
  color: #e55;
}
table {
  width: 100%;
}
</style>
