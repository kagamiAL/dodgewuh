<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { createScene, type GameScene } from '@/game/scene'
import { session } from '@/stores/session'
import { connect, transport } from '@/stores/connection'
import { TEAM_HEX } from '@/theme'
import Lobby from './Lobby.vue'
import CameraLegs from '@/camera/CameraLegs.vue'

const route = useRoute()
// Dev-only mock routes (plans/04), compiled out of production builds:
//   /screen?mock=1         scripted 20 Hz feed through session.apply (same path as live)
//   /screen?mock=lobby     Richard's reset-lobby fixture
//   /screen?mock=movement  Richard's active-movement fixture
//   /screen?mock=held      03 example 11–12 (Team 1 holding b1)
const mock = import.meta.env.DEV ? (route.query.mock as string | undefined) : undefined

const canvas = ref<HTMLCanvasElement | null>(null)
const error = ref<string | null>(null)
// Engine objects stay out of Vue's deep reactivity (plans/01-architecture.md).
const scene = shallowRef<GameScene | null>(null)
let stopMock: (() => void) | null = null
const live = !mock

const state = computed(() => session.data.state)
const phase = computed(() => state.value?.phase ?? 'lobby')
const showLobby = computed(() => live && (phase.value === 'lobby' || phase.value === 'match_end'))
const PHASE_LABEL: Record<string, string> = {
  countdown: 'Get ready',
  round_end: 'Round over',
  role_switch: 'Swap roles — phones recalibrate and tap Ready',
  match_end: 'Match over',
}
const banner = computed(() => {
  const st = state.value
  if (!st) return null
  if (st.phase === 'countdown' && st.phase_remaining_ms !== null) return `${Math.ceil(st.phase_remaining_ms / 1000)}`
  if (st.phase === 'match_end' && st.winner) return `Team ${st.winner} wins!`
  return PHASE_LABEL[st.phase] ?? null
})
const clock = computed(() => {
  const ms = state.value?.remaining_ms ?? 0
  const s = Math.ceil(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
})
const connection = computed(() => {
  if (!live) return null
  if (session.data.closedReason) return 'Room ended. Create a new room from the home page.'
  if (!session.data.registration) return 'Not in a room.'
  switch (session.data.status) {
    case 'connected': return null
    case 'closed': return 'Disconnected. Rejoin from the home page.'
    default: return 'Connecting…'
  }
})

// The screen only ever draws what the session store holds.
watch(
  () => session.data.state,
  (state) => {
    if (state) scene.value?.renderState(state)
  },
)

onMounted(async () => {
  if (!canvas.value) return
  try {
    scene.value = createScene(canvas.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    return
  }
  if (session.data.state) scene.value.renderState(session.data.state)

  if (live) {
    if (session.data.registration) connect().catch(() => {}) // status/overlay report failures
  } else if (mock === '1') {
    const { startMockSource } = await import('@/game/mockSource')
    stopMock = startMockSource((msg) => session.apply(msg))
  } else if (mock) {
    const { FIXTURES } = await import('@/game/fixtures')
    const fixture = FIXTURES[mock]
    if (fixture) session.apply(fixture)
    else error.value = `Unknown mock "${mock}". Try: 1, ${Object.keys(FIXTURES).join(', ')}`
  }
})

onBeforeUnmount(() => {
  stopMock?.()
  if (live) transport.close()
  if (mock) session.reset() // never leak fake state into a real session
  scene.value?.destroy()
  scene.value = null
})
</script>

<template>
  <main class="screen">
    <canvas ref="canvas" class="game-canvas" />
    <p v-if="error" class="error">Could not start the 3D view: {{ error }}</p>
    <template v-if="live && state">
      <div class="hud">
        <span class="score" :style="{ color: TEAM_HEX[1] }">{{ state.score.t1 }}</span>
        <span class="clock">{{ clock }}<small v-if="state.round"> · round {{ state.round }}</small></span>
        <span class="score" :style="{ color: TEAM_HEX[2] }">{{ state.score.t2 }}</span>
      </div>
      <p v-if="banner" class="banner">{{ banner }}</p>
    </template>
    <div v-if="showLobby" class="overlay"><Lobby /></div>
    <CameraLegs v-if="live" />
    <p v-if="connection" class="connection">
      {{ connection }} <RouterLink v-if="session.data.status === 'closed'" to="/">Home</RouterLink>
    </p>
    <p v-if="mock && session.data.state" class="mock-label">
      MOCK · {{ session.data.state.phase }} · epoch {{ session.data.state.epoch }} · tick
      {{ session.data.state.tick }}
    </p>
  </main>
</template>

<style scoped>
.screen {
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}
.game-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
.mock-label {
  position: absolute;
  top: 8px;
  left: 12px;
  margin: 0;
  font: 12px ui-monospace, monospace;
  color: #fc6;
}
.hud {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 1.5rem;
  align-items: baseline;
  padding: 0.4rem 1.2rem;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.55);
  font-variant-numeric: tabular-nums;
}
.score {
  font: 700 2rem system-ui, sans-serif;
}
.clock {
  font-size: 1.4rem;
}
.clock small {
  color: #aaa;
  font-size: 0.8rem;
}
.banner {
  position: absolute;
  top: 22%;
  left: 0;
  right: 0;
  margin: 0;
  text-align: center;
  font: 800 clamp(1.5rem, 6vw, 4rem) system-ui, sans-serif;
  text-shadow: 0 2px 12px #000;
  pointer-events: none;
}
.overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.25);
}
.connection {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  background: #522;
}
.connection a {
  color: #8cf;
}
.error {
  position: absolute;
  inset: 0;
  margin: auto;
  height: fit-content;
  text-align: center;
}
</style>
