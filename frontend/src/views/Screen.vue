<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { createScene, type GameScene, type PointOfView } from '@/game/scene'
import { session } from '@/stores/session'
import { connect, transport } from '@/stores/connection'
import type { Team } from '@/contracts/pending'
import { MAX_ROUNDS, NO_THROW_HALF_DEPTH } from '@/game/constants'
import { TEAM_HEX, TEAM_NAME } from '@/theme'
import Lobby from './Lobby.vue'
import CameraLegs from '@/camera/CameraLegs.vue'
import type { DodgePractice, PracticeTally } from '@/game/dodgePractice'

const route = useRoute()
// Dev-only mock routes (plans/04), compiled out of production builds:
//   /screen?mock=1         scripted 20 Hz feed through session.apply (same path as live)
//   /screen?mock=lobby     Richard's reset-lobby fixture
//   /screen?mock=movement  Richard's active-movement fixture
//   /screen?mock=held      03 example 11–12 (Team 1 holding b1)
//   add &spectate          preview the spectator camera switcher on any mock
// /dodge: camera dodge practice. A local feed throws at you (Team 2 Legs) and this screen's
// camera judges each dodge; no room or backend.
const practice = route.name === 'dodge'
const mock = import.meta.env.DEV && !practice ? (route.query.mock as string | undefined) : undefined
// View: first person from the team this screen's camera drives (Member.camera_team), else
// the elevated overview. ?view=fp1|fp2|overview|sideline overrides it, live or mock.
// Spectators pick a view with the switcher (or keys 1–4) instead; ?view= sets their first one.
const VIEW_QUERY: Record<string, PointOfView> = { fp1: 1, fp2: 2, overview: 'overview', sideline: 'sideline' }
const viewOverride = route.query.view as string | undefined
const SPECTATOR_VIEWS: { view: PointOfView; label: string }[] = [
  { view: 'overview', label: 'Overview' },
  { view: 'sideline', label: 'Bleachers' },
  { view: 1, label: TEAM_NAME[1] }, // + ' POV', dropped on narrow screens
  { view: 2, label: TEAM_NAME[2] },
]

const canvas = ref<HTMLCanvasElement | null>(null)
const error = ref<string | null>(null)
// Engine objects stay out of Vue's deep reactivity (plans/01-architecture.md).
const scene = shallowRef<GameScene | null>(null)
let stopMock: (() => void) | null = null
let practiceFeed: DodgePractice | null = null
const tally = ref<PracticeTally>({ dodged: 0, hit: 0 })
const live = !mock && !practice

const state = computed(() => session.data.state)
const me = computed(() => session.data.room?.members.find((m) => m.member_id === session.data.registration?.member_id))
// Watch-only member: no camera, no host controls, free choice of view.
const spectating = computed(
  () => (live && me.value?.device === 'spectator') || (!!mock && route.query.spectate !== undefined),
)
const spectatorView = ref<PointOfView>(
  viewOverride !== undefined && viewOverride in VIEW_QUERY ? VIEW_QUERY[viewOverride] : 'overview',
)
const pointOfView = computed<PointOfView | null>(() => {
  if (spectating.value) return spectatorView.value
  if (viewOverride !== undefined && viewOverride in VIEW_QUERY) return VIEW_QUERY[viewOverride]
  if (practice) return 2
  return me.value?.camera_team ?? null
})
function onKey(e: KeyboardEvent): void {
  if (!spectating.value || e.metaKey || e.ctrlKey || e.altKey) return
  const choice = SPECTATOR_VIEWS[Number(e.key) - 1]
  if (choice) spectatorView.value = choice.view
}
const phase = computed(() => state.value?.phase ?? 'lobby')
// Between rounds (role_switch) the lobby overlay doubles as the ready view.
const showLobby = computed(() => live && (phase.value === 'lobby' || phase.value === 'role_switch' || phase.value === 'match_end'))
// Spectators can dismiss the overlay to look around the arena between games.
const hideLobby = ref(false)
watch(phase, () => (hideLobby.value = false))
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
  if (spectating.value || (team !== 1 && team !== 2) || st?.phase !== 'active') return false
  const me = st.characters.find((c) => c.team === team)
  return !!me && me.held_ball_id !== null && Math.abs(me.pos.z) <= NO_THROW_HALF_DEPTH
})
const banner = computed(() => {
  const st = state.value
  if (!st) return null
  if (showLobby.value) return null // the overlay shows the ready view / result itself
  // Camera dodge: the server runs the room in slow motion until it is decided and played out.
  if (st.dodge) return st.dodge.outcome === 'dodged' ? 'DODGED!' : st.dodge.outcome === 'hit' ? 'HIT!' : `Team ${st.dodge.team}: DODGE!`
  if (st.phase === 'countdown' && st.phase_remaining_ms !== null) return `${Math.ceil(st.phase_remaining_ms / 1000)}`
  if (st.phase === 'match_end' && st.winner) return `Team ${st.winner} wins!`
  return PHASE_LABEL[st.phase] ?? null
})
const slowMotion = computed(() => !!state.value?.dodge)
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
  practiceFeed?.setFacing(value?.dir ?? null)
}

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  if (!canvas.value) return
  try {
    scene.value = createScene(canvas.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
  // Room connection and host controls must work even when WebGL is unavailable.
  if (session.data.state) scene.value?.renderState(session.data.state)

  if (live) {
    if (session.data.registration) connect().catch(() => {}) // status/overlay report failures
  } else if (practice) {
    const { startDodgePractice } = await import('@/game/dodgePractice')
    practiceFeed = startDodgePractice((msg) => session.apply(msg), (t) => (tally.value = t))
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
  window.removeEventListener('keydown', onKey)
  stopMock?.()
  practiceFeed?.stop()
  if (live) transport.close()
  if (mock || practice) session.reset() // never leak fake state into a real session
  scene.value?.destroy()
  scene.value = null
})
</script>

<template>
  <main class="screen" :class="{ slowmo: slowMotion }">
    <canvas ref="canvas" class="game-canvas" />
    <p v-if="error" class="error">Could not start the 3D view: {{ error }}</p>
    <template v-if="(live || practice) && state">
      <div v-if="practice" class="hud">
        <span class="score" :style="{ color: '#3c6' }">{{ tally.dodged }}</span>
        <span class="clock">dodged · hit</span>
        <span class="score" :style="{ color: '#f44' }">{{ tally.hit }}</span>
      </div>
      <div v-else class="hud">
        <span class="score" :style="{ color: TEAM_HEX[1] }">{{ state.score.t1 }}</span>
        <span class="clock">{{ clock }}<small v-if="state.round"> · round {{ state.round }}/{{ MAX_ROUNDS }}</small></span>
        <span class="score" :style="{ color: TEAM_HEX[2] }">{{ state.score.t2 }}</span>
      </div>
      <p v-if="banner" class="banner">{{ banner }}</p>
    </template>
    <p v-if="inNoThrowZone" class="zone-warning">No-throw zone: move back to throw</p>
    <div v-if="showLobby && !(spectating && hideLobby)" class="overlay">
      <Lobby />
      <button v-if="spectating" class="hide-lobby" @click="hideLobby = true">Hide lobby</button>
    </div>
    <nav v-if="spectating && !connection" class="views" aria-label="Spectator camera">
      <span class="watching">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></svg>
        Spectating
      </span>
      <div class="segments">
        <button
          v-for="(v, i) in SPECTATOR_VIEWS"
          :key="String(v.view)"
          :class="{ on: spectatorView === v.view }"
          :aria-pressed="spectatorView === v.view"
          @click="spectatorView = v.view"
        >
          <span v-if="v.view === 1 || v.view === 2" class="swatch" :style="{ background: TEAM_HEX[v.view] }" />
          <span>{{ v.label }}<span v-if="v.view === 1 || v.view === 2" class="pov"> POV</span></span>
          <kbd aria-hidden="true">{{ i + 1 }}</kbd>
        </button>
      </div>
      <button v-if="showLobby && hideLobby" class="show-lobby" @click="hideLobby = false">Show lobby</button>
    </nav>
    <CameraLegs v-if="live && !spectating" @facing="onFacing" />
    <CameraLegs
      v-else-if="practice"
      :practice-team="2"
      @facing="onFacing"
      @dodge-result="(r) => practiceFeed?.verdict(r.ball_id, r.dodged)"
    />
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
  transition: filter 0.3s;
}
/* Camera dodge slow motion: desaturate and vignette the 3D view. */
.screen.slowmo .game-canvas {
  filter: saturate(0.45) contrast(1.15);
}
.screen.slowmo::after {
  content: '';
  position: absolute;
  inset: 0;
  box-shadow: inset 0 0 18vmin rgba(0, 0, 0, 0.85);
  pointer-events: none;
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
.hide-lobby {
  min-height: 2.75rem;
  margin-top: 0.75rem;
  padding: 0.5rem 1.25rem;
  border: 0;
  border-radius: 10px;
  background: var(--surface);
  color: var(--text);
  font: 600 0.9rem system-ui, sans-serif;
  cursor: pointer;
}
.hide-lobby:hover {
  filter: brightness(1.15);
}
/* Spectator camera switcher: one bar along the bottom, out of the court's way. */
.views {
  position: absolute;
  bottom: calc(16px + env(safe-area-inset-bottom));
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  max-width: calc(100% - 2rem);
  padding: 0.375rem;
  border-radius: 12px;
  background: rgba(16, 24, 32, 0.82);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
  font: 600 0.875rem system-ui, sans-serif;
}
.watching {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0 0.5rem 0 0.4rem;
  color: var(--muted);
  white-space: nowrap;
}
.watching svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linejoin: round;
}
.segments {
  display: flex;
  gap: 0.25rem;
}
.views button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  min-height: 2.75rem;
  padding: 0.4rem 0.8rem;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  white-space: nowrap;
  cursor: pointer;
  transition: background 160ms ease-out, color 160ms ease-out;
  -webkit-tap-highlight-color: transparent;
}
.views button:hover {
  color: var(--text);
  background: rgba(255, 245, 220, 0.06);
}
.views button:focus-visible {
  outline-offset: 2px;
}
.views button.on {
  background: #1e3046;
  box-shadow: inset 0 0 0 1px var(--blue);
  color: var(--text);
}
.views .show-lobby {
  color: var(--blue);
}
.swatch {
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  flex: none;
}
kbd {
  min-width: 1.1rem;
  padding: 0 0.25rem;
  border: 1px solid var(--line);
  border-radius: 4px;
  color: var(--muted);
  font: 600 0.7rem / 1.4 system-ui, sans-serif;
  font-variant-numeric: tabular-nums;
  text-align: center;
}
/* Touch screens have no number keys to hint at, and narrow windows have no room for them. */
@media (pointer: coarse), (max-width: 40rem) {
  kbd {
    display: none;
  }
}
/* Phones: drop the label and let the four cameras share the full width. */
@media (max-width: 40rem) {
  .views {
    left: 1rem;
    right: 1rem;
    transform: none;
    max-width: none;
    flex-wrap: wrap;
  }
  .watching {
    display: none;
  }
  .segments {
    flex: 1;
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .views button {
    min-width: 0;
    padding: 0.4rem 0.25rem;
    font-size: 0.8rem;
    gap: 0.3rem;
  }
  .views .show-lobby {
    flex: 1 0 100%;
  }
  .pov {
    display: none;
  }
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
