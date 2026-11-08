<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { createScene, type GameScene } from '@/game/scene'
import { session } from '@/stores/session'
import { connect, transport } from '@/stores/connection'
import type { Team } from '@/contracts/pending'
import { MAX_ROUNDS, NO_THROW_HALF_DEPTH } from '@/game/constants'
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
// View: first person from the team this screen's camera drives (Member.camera_team), else
// the elevated overview. ?view=fp1|fp2|overview overrides it, live or mock.
const VIEW_QUERY: Record<string, Team | null> = { fp1: 1, fp2: 2, overview: null }
const viewOverride = route.query.view as string | undefined

const canvas = ref<HTMLCanvasElement | null>(null)
const error = ref<string | null>(null)
// Engine objects stay out of Vue's deep reactivity (plans/01-architecture.md).
const scene = shallowRef<GameScene | null>(null)
let stopMock: (() => void) | null = null
const live = !mock

const state = computed(() => session.data.state)
const pointOfView = computed<Team | null>(() => {
  if (viewOverride !== undefined && viewOverride in VIEW_QUERY) return VIEW_QUERY[viewOverride]
  const me = session.data.room?.members.find((m) => m.member_id === session.data.registration?.member_id)
  return me?.camera_team ?? null
})
const phase = computed(() => state.value?.phase ?? 'lobby')
// Between rounds (role_switch) the lobby overlay doubles as the ready view.
const showLobby = computed(() => live && (phase.value === 'lobby' || phase.value === 'role_switch' || phase.value === 'match_end'))
const PHASE_LABEL: Record<string, string> = {
  countdown: 'Get ready',
  round_end: 'Round over',
  role_switch: 'Swap roles — phones recalibrate and tap Ready',
  match_end: 'Match over',
}
// First person: warn while you hold a ball inside the no-throw zone (02: |z| ≤ 2). The
// server's NO_THROW_ZONE rejection only reaches the Arms phone, so the screen warns up front.
const inNoThrowZone = computed(() => {
  const team = pointOfView.value
  const st = state.value
  if (!team || st?.phase !== 'active') return false
  const me = st.characters.find((c) => c.team === team)
  return !!me && me.held_ball_id !== null && Math.abs(me.pos.z) <= NO_THROW_HALF_DEPTH
})
const banner = computed(() => {
  const st = state.value
  if (!st) return null
  if (showLobby.value) return null // the overlay shows the ready view / result itself
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
    if (!state) return
    scene.value?.renderState(state)
    // The scripted mock backpedals, which would turn a movement-driven view around; in the
    // mock, face where each character aims instead so throws stay in view.
    if (mock) for (const c of state.characters) scene.value?.setFacing(c.team, c.aim)
  },
)
watch([pointOfView, scene], ([team]) => scene.value?.setPointOfView(team))

// The camera-controlled team's facing comes straight from this screen's pose tracker.
let facingTeam: Team | null = null
function onFacing(value: { team: Team; dir: { x: number; z: number } } | null): void {
  if (facingTeam !== null && facingTeam !== value?.team) scene.value?.setFacing(facingTeam, null)
  facingTeam = value?.team ?? null
  if (value) scene.value?.setFacing(value.team, value.dir)
}

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
        <span class="clock">{{ clock }}<small v-if="state.round"> · round {{ state.round }}/{{ MAX_ROUNDS }}</small></span>
        <span class="score" :style="{ color: TEAM_HEX[2] }">{{ state.score.t2 }}</span>
      </div>
      <p v-if="banner" class="banner">{{ banner }}</p>
    </template>
    <p v-if="inNoThrowZone" class="zone-warning">No-throw zone: move back to throw</p>
    <div v-if="showLobby" class="overlay"><Lobby /></div>
    <CameraLegs v-if="live" @facing="onFacing" />
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
  /* 100vw includes the scrollbar gutter and overflows; 100% matches #app. */
  width: 100%;
  height: 100vh;
  /* Mobile browsers size 100vh to the *expanded* toolbar, so the bottom is
     cut off until the user scrolls. dvh tracks the visible viewport. */
  height: 100dvh;
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
  top: calc(12px + env(safe-area-inset-top));
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: clamp(0.75rem, 4vw, 1.5rem);
  align-items: baseline;
  max-width: calc(100% - 1.5rem);
  padding: 0.4rem clamp(0.6rem, 3vw, 1.2rem);
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.55);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.score {
  font: 700 clamp(1.4rem, 7vw, 2rem) system-ui, sans-serif;
}
.clock {
  font-size: clamp(1rem, 5vw, 1.4rem);
}
.clock small {
  color: #aaa;
  font-size: 0.8rem;
}
.zone-warning {
  position: absolute;
  top: 5.5rem;
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
  padding: 0.5rem 1.1rem;
  border-radius: 10px;
  background: rgba(200, 40, 50, 0.85);
  font: 700 clamp(1rem, 2.6vw, 1.6rem) system-ui, sans-serif;
  pointer-events: none;
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
  /* start, not center: on a phone the lobby is taller than the viewport, and
     .screen clips it. Scroll instead of hiding the host buttons. */
  align-content: center;
  align-content: safe center;
  justify-items: center;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  padding: calc(1rem + env(safe-area-inset-top)) env(safe-area-inset-right)
    calc(1rem + env(safe-area-inset-bottom)) env(safe-area-inset-left);
  background: rgba(0, 0, 0, 0.25);
}
.connection {
  position: absolute;
  bottom: calc(12px + env(safe-area-inset-bottom));
  left: 50%;
  transform: translateX(-50%);
  max-width: calc(100% - 1.5rem);
  margin: 0;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  background: #522;
  text-align: center;
}
.connection a {
  color: #8cf;
}
.error {
  position: absolute;
  inset: 0;
  margin: auto;
  height: fit-content;
  padding: 0 1rem;
  text-align: center;
  overflow-wrap: break-word;
}
</style>
