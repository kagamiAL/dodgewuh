<script setup lang="ts">
// /sensors: run the real LegsController without a backend. Outgoing input.legs messages go to a
// recording Transport, move a dot on a local court at the 02 speed (3.5 m/s), and can be scored
// against spoken cues ("Step left" … "Back to center") while the phone is in the pocket.

import { computed, onBeforeUnmount, ref, shallowRef } from 'vue'
import type { State, Team } from '@/contracts/pending'
import { createSensorService } from '@/sensors/sensorService'
import LegsController from '@/controllers/legs/LegsController.vue'
import type { StepDir } from '@/controllers/legs/stepDetector'
import { beep, say } from '@/controllers/legs/voice'
import { createRecordingTransport, type SentMessage } from './recordingTransport'

const SPEED = 3.5 // m/s, 02
const HALF_W = 6
const HALF_D = 9
const CUE_MS = 3000
const CUE_PAIRS = 5
const DIRS: StepDir[] = ['left', 'right', 'forward', 'back']
const OPPOSITE: Record<StepDir, StepDir> = { left: 'right', right: 'left', forward: 'back', back: 'forward' }

const team = ref<Team>(1)
const scoredTest = ref(true)
const speakSteps = ref(false)
const calibrated = ref(false)
const availability = ref('unknown')
const sent = ref(0)
const problems = ref<string[]>([])
const log = ref<string[]>([])
const pos = ref({ r: 0, f: 0 }) // team-local metres: +right, +forward
const trail = ref<string>('')
const counts = ref<Record<StepDir, number>>({ left: 0, right: 0, forward: 0, back: 0 })

interface Cue { at: number; expect: StepDir; got: StepDir | null; extra: number }
const cues = ref<Cue[]>([])
const testState = ref<'idle' | 'running' | 'done'>('idle')
const score = computed(() => cues.value.filter((c) => c.got === c.expect).length)

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
let lastDir: StepDir | null = null
const timers = new Set<ReturnType<typeof setTimeout>>()
function later(ms: number, fn: () => void): void {
  const id = setTimeout(() => {
    timers.delete(id)
    fn()
  }, ms)
  timers.add(id)
}

function localDir(r: number, f: number): StepDir | null {
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
  if (dir && dir !== lastDir) onStep(dir, at)
  if (!dir && lastDir) trail.value += ` ${pos.value.r.toFixed(2)},${(-pos.value.f).toFixed(2)}`
  lastDir = dir
}

function onStep(dir: StepDir, at: number): void {
  counts.value = { ...counts.value, [dir]: counts.value[dir] + 1 }
  trail.value += ` ${pos.value.r.toFixed(2)},${(-pos.value.f).toFixed(2)}`
  log.value = [`${dir}  @${(at / 1000).toFixed(1)}s`, ...log.value].slice(0, 30)
  const cue = [...cues.value].reverse().find((c) => at >= c.at && at < c.at + CUE_MS)
  if (testState.value === 'running' && cue) {
    if (cue.got === null) {
      cue.got = dir
      beep(dir === cue.expect ? 1400 : 250, 150)
    } else cue.extra++
    cues.value = [...cues.value]
  } else if (speakSteps.value) say(dir)
}

function runTest(): void {
  cues.value = []
  testState.value = 'running'
  let t = 2500 // let "Go" finish
  for (let i = 0; i < CUE_PAIRS; i++) {
    const dir = DIRS[Math.floor(Math.random() * DIRS.length)]
    for (const [text, expect] of [[`Step ${dir}`, dir], ['Back to center', OPPOSITE[dir]]] as const) {
      later(t, () => {
        say(text)
        cues.value = [...cues.value, { at: performance.now(), expect, got: null, extra: 0 }]
      })
      t += CUE_MS
    }
  }
  later(t, () => {
    testState.value = 'done'
    say(`Score: ${score.value} out of ${cues.value.length}`)
  })
}

function onCalibrated(v: boolean): void {
  calibrated.value = v
  if (v) {
    pos.value = { r: 0, f: 0 }
    trail.value = '0,0'
    counts.value = { left: 0, right: 0, forward: 0, back: 0 }
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
    <h2>Sensor playground · Legs</h2>
    <div class="row">
      <label>Team
        <select v-model.number="team" :disabled="calibrated">
          <option :value="1">1 (blue)</option>
          <option :value="2">2 (orange)</option>
        </select>
      </label>
      <label><input v-model="scoredTest" type="checkbox"> scored test after "Go"</label>
      <label><input v-model="speakSteps" type="checkbox"> speak steps</label>
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
        <tr v-for="(c, i) in cues" :key="i" :class="c.got === c.expect ? 'ok' : 'bad'">
          <td>{{ c.expect }}</td><td>{{ c.got ?? 'missed' }}</td><td>{{ c.extra ? `+${c.extra} extra` : '' }}</td>
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
      <p>← {{ counts.left }} · → {{ counts.right }} · ↑ {{ counts.forward }} · ↓ {{ counts.back }}</p>
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
