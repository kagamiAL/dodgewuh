<script setup lang="ts">
// /sensors → Practice: the real ArmsController against a tiny local stand-in for the server.
// A ball respawns beside you after each throw; tap to grab, chop to throw. Flight mirrors the
// server's ballistic rule: launched flat at 12 + 7 × strength m/s from centre + aim × 0.65 (weak 0 /
// medium 0.5 / hard 1), it lands after ~1.12 s (range 13.5 / 17.4 / 21.4 m) and can only hit the
// dummy before it lands.
// Numbers mirror backend/simulation/constants.py. Presentation only — the server stays authoritative.

import { computed, onBeforeUnmount, reactive, ref, shallowRef } from 'vue'
import type { ClientMessage, State, Vec2 } from '@/contracts/pending'
import type { SensorService } from '@/sensors/sensorService'
import ArmsController from '@/controllers/arms/ArmsController.vue'
import { DEFAULT_ASSIST, FALL_S, assistTuning, throwSpeed } from '@/controllers/arms/throwGesture'
import { createRecordingTransport, type SentMessage } from './recordingTransport'

defineProps<{ sensors: SensorService }>()

// backend/simulation/constants.py
const COURT_X = 6
const COURT_Z = 9
const COMBINED_RADIUS = 0.75
const BALL_R = 0.3
const LEGS_SPEED = 3.5 // 02 movement speed: the dummy runs like a real Legs player
const THROW_OFFSET = 0.65
const RESPAWN_MS = 1000
const ME: Vec2 = { x: 0, z: -6 } // T1 spawn
const GROUND_BALL: Vec2 = { x: 0.7, z: -5.6 } // respawns within pickup reach (1.2 m)
const RAD = 180 / Math.PI

const movingTarget = ref(false)
const assist = reactive(assistTuning) // edits the controller's live assist settings
const target = ref<Vec2>({ x: 0, z: 6 })
const ball = ref<{ pos: Vec2; vel: Vec2; born: number } | null>(null)
const trail = ref<string>('')
const hasBall = ref(false)
const ballOnGround = ref(true) // a ball waiting beside you to be tapped up
const hits = ref(0)
const thrown = ref(0)
const last = ref<{ result: 'hit' | 'miss' | 'short'; speed: number; strength: number; aim_deg: number; range: number } | null>(null)
const landedAt = ref<Vec2 | null>(null)
const problems = ref<string[]>([])
const latched = ref(false) // server-style Hold latch: set by press, cleared by release/cancel

const state = shallowRef<State>(makeState())
function makeState(): State {
  return {
    tick: 0, epoch: 1, round: 1, phase: 'active', remaining_ms: 60000, phase_remaining_ms: null,
    score: { t1: hits.value, t2: 0 },
    characters: [
      { team: 1, pos: ME, aim: { x: 0, z: 1 }, held_ball_id: hasBall.value ? 'b1' : null },
      { team: 2, pos: target.value, aim: { x: 0, z: -1 }, held_ball_id: null },
    ],
    balls: ballOnGround.value
      ? [{ ball_id: 'b1', mode: 'ground', pos: GROUND_BALL, velocity: { x: 0, z: 0 }, owner_team: null, shooter_team: null, respawn_in_ms: 0, height: BALL_R }]
      : [],
    assignments: [], assignment_version: 1, result: null, winner: null,
  }
}

// Like the server: a latched Hold picks up the ball as soon as one is in reach.
function tryAcquire(): void {
  if (latched.value && ballOnGround.value && !hasBall.value) {
    ballOnGround.value = false
    hasBall.value = true
    publish()
  }
}
function publish(): void {
  state.value = makeState()
}

const transport = createRecordingTransport(onSent)

function onSent({ message, problem }: SentMessage): void {
  if (problem) problems.value = [problem, ...problems.value].slice(0, 5)
  handle(message)
}

function handle(m: ClientMessage): void {
  if (m.type !== 'input.arms') return
  const { action, aim, strength } = m.payload
  if (action === 'press') {
    latched.value = true
    tryAcquire()
  }
  if (action === 'cancel') {
    latched.value = false
    if (hasBall.value) {
      hasBall.value = false // dropped beside you
      ballOnGround.value = true
      publish()
    }
  }
  if (action !== 'release') return
  latched.value = false
  if (!hasBall.value || strength === null) return
  const speed = throwSpeed(strength)
  landedAt.value = null
  const pos = { x: ME.x + aim.x * THROW_OFFSET, z: ME.z + aim.z * THROW_OFFSET }
  ball.value = { pos, vel: { x: aim.x * speed, z: aim.z * speed }, born: performance.now() }
  trail.value = `${pos.x.toFixed(2)},${(-pos.z).toFixed(2)}`
  hasBall.value = false
  thrown.value++
  last.value = { result: 'miss', speed, strength, aim_deg: Math.atan2(aim.x, aim.z) * RAD, range: speed * FALL_S }
  publish()
}

// Distance from point c to segment a→b.
function segDist(a: Vec2, b: Vec2, c: Vec2): number {
  const dx = b.x - a.x, dz = b.z - a.z
  const len2 = dx * dx + dz * dz
  const t = len2 ? Math.max(0, Math.min(1, ((c.x - a.x) * dx + (c.z - a.z) * dz) / len2)) : 0
  return Math.hypot(a.x + dx * t - c.x, a.z + dz * t - c.z)
}

function endFlight(result: 'hit' | 'miss' | 'short'): void {
  ball.value = null
  if (last.value) last.value = { ...last.value, result }
  if (result === 'hit') {
    hits.value++
    placeTarget()
  }
  later(RESPAWN_MS, () => {
    ballOnGround.value = true
    publish()
    tryAcquire()
  })
}

function placeTarget(): void {
  target.value = { x: (Math.random() * 2 - 1) * 4.5, z: 3 + Math.random() * 5 }
  publish() // the controller's aim assist reads the target from state
}

let raf = 0
let prev = performance.now()
let dir = 1
let lastPublish = 0
function frame(now: number): void {
  const dt = Math.min((now - prev) / 1000, 0.05)
  prev = now
  if (movingTarget.value) {
    let x = target.value.x + dir * LEGS_SPEED * dt
    if (Math.abs(x) > 4.5) {
      dir = -dir
      x = Math.sign(x) * 4.5
    }
    target.value = { ...target.value, x }
  }
  // Like the server's 20 Hz snapshots, so the controller sees the dummy move (aim-assist lead).
  if (movingTarget.value && now - lastPublish >= 50) {
    lastPublish = now
    publish()
  }
  const b = ball.value
  if (b) {
    const next = { x: b.pos.x + b.vel.x * dt, z: b.pos.z + b.vel.z * dt }
    trail.value += ` ${next.x.toFixed(2)},${(-next.z).toFixed(2)}`
    if (segDist(b.pos, next, target.value) <= COMBINED_RADIUS) endFlight('hit')
    else if (Math.abs(next.x) > COURT_X || Math.abs(next.z) > COURT_Z) endFlight('miss')
    else if (now - b.born >= FALL_S * 1000) {
      landedAt.value = next // touched down before reaching the dummy
      endFlight('short')
    } else ball.value = { ...b, pos: next }
  }
  raf = requestAnimationFrame(frame)
}
raf = requestAnimationFrame(frame)

const timers = new Set<ReturnType<typeof setTimeout>>()
function later(ms: number, fn: () => void): void {
  const id = setTimeout(() => {
    timers.delete(id)
    fn()
  }, ms)
  timers.add(id)
}

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  for (const id of timers) clearTimeout(id)
})

const accuracy = computed(() => (thrown.value ? Math.round((hits.value / thrown.value) * 100) : 0))
</script>

<template>
  <section class="practice">
    <div class="hud">
      <strong>{{ hits }} / {{ thrown }} hits</strong> <span>({{ accuracy }}%)</span>
      <label><input v-model="movingTarget" type="checkbox"> moving target</label>
      <button @click="placeTarget">New target</button>
    </div>
    <div class="hud">
      <label><input v-model="assist.enabled" type="checkbox"> aim assist</label>
      <label><input v-model="assist.lead" type="checkbox" :disabled="!assist.enabled"> lead moving targets</label>
      <label class="cone">pull within {{ assist.coneDeg }}°
        <input v-model.number="assist.coneDeg" type="range" min="5" max="30" step="1" :disabled="!assist.enabled">
      </label>
      <button @click="Object.assign(assist, DEFAULT_ASSIST)">Reset assist</button>
    </div>
    <p v-if="last" class="last" :class="last.result">
      {{ last.result === 'hit' ? 'HIT' : last.result === 'short' ? 'Landed short' : 'Miss' }} · {{ last.speed.toFixed(1) }} m/s
(strength {{ last.strength.toFixed(2) }}, range {{ last.range.toFixed(1) }} m) · aim {{ Math.round(last.aim_deg) }}°
    </p>
    <p v-for="(p, i) in problems" :key="i" class="miss">server would reject: {{ p }}</p>

    <svg :viewBox="`${-COURT_X - 0.3} ${-COURT_Z - 0.3} ${COURT_X * 2 + 0.6} ${COURT_Z * 2 + 0.6}`" class="court">
      <rect :x="-COURT_X" :y="-COURT_Z" :width="COURT_X * 2" :height="COURT_Z * 2" class="floor" />
      <rect :x="-COURT_X" y="-2" :width="COURT_X * 2" height="4" class="zone" />
      <line :x1="-COURT_X" y1="0" :x2="COURT_X" y2="0" class="mid" />
      <polyline :points="trail" class="trail" />
      <circle :cx="target.x" :cy="-target.z" r="0.45" class="target" />
      <circle :cx="target.x" :cy="-target.z" :r="COMBINED_RADIUS" class="hitzone" />
      <circle :cx="ME.x" :cy="-ME.z" r="0.45" class="me" />
      <circle v-if="hasBall" :cx="ME.x" :cy="-ME.z + 0.8" :r="BALL_R" class="ball" />
      <g v-if="landedAt" class="landed">
        <line :x1="landedAt.x - 0.3" :y1="-landedAt.z - 0.3" :x2="landedAt.x + 0.3" :y2="-landedAt.z + 0.3" />
        <line :x1="landedAt.x - 0.3" :y1="-landedAt.z + 0.3" :x2="landedAt.x + 0.3" :y2="-landedAt.z - 0.3" />
      </g>
      <circle v-if="ballOnGround" :cx="GROUND_BALL.x" :cy="-GROUND_BALL.z" :r="BALL_R" class="ball ground" />
      <circle v-if="ball" :cx="ball.pos.x" :cy="-ball.pos.z" :r="BALL_R" class="ball" />
    </svg>

    <ArmsController
      :transport="transport"
      :sensors="sensors"
      member_id="practice"
      :team="1"
      :epoch="1"
      :assignment_version="1"
      :state="state"
      :connected="true"
    />
  </section>
</template>

<style scoped>
.hud {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}
.hud button {
  margin-left: auto;
  padding: 0.4rem 0.75rem;
  border: 1px solid #444;
  border-radius: 8px;
  background: #222;
  color: #ccc;
  font: inherit;
}
.cone {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.cone input {
  width: 7rem;
}
.hud + .hud {
  margin-top: 0.4rem;
}
.last {
  margin: 0.4rem 0;
  font-weight: 700;
}
.hit {
  color: #3c6;
}
.short {
  color: #fb4;
}
.landed line {
  stroke: #fb4;
  stroke-width: 0.12;
}
.miss {
  color: #e55;
}
.court {
  display: block;
  width: 100%;
  max-height: 38vh;
  margin: 0.5rem 0;
}
.floor {
  fill: #0d1a0d;
  stroke: #555;
  stroke-width: 0.08;
}
.zone {
  fill: #e55;
  opacity: 0.12;
}
.mid {
  stroke: #555;
  stroke-width: 0.05;
}
.trail {
  fill: none;
  stroke: #fc3;
  stroke-width: 0.08;
  opacity: 0.7;
}
.target {
  fill: #ff8c26;
}
.hitzone {
  fill: none;
  stroke: #ff8c26;
  stroke-width: 0.04;
  stroke-dasharray: 0.15 0.15;
}
.me {
  fill: #338cff;
}
.ball {
  fill: #fff;
}
.ball.ground {
  fill: #bbb;
  stroke: #fff;
  stroke-width: 0.05;
}
</style>
