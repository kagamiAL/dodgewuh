<script setup lang="ts">
// PhoneShell: mounts the role component for this phone's current assignment and owns
// controller.ready (plans/03 "Frontend module seams", src/phone/roleComponent.ts).
//
// Ready is an explicit tap that arms an intent for the current epoch/assignment_version.
// ready=true is sent once the role component reports calibrated + granted, so a Legs player
// starts calibration with the same tap. Losing either sends ready=false at once.
// The shell never sends gameplay input.
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import type { Permission, ServerMessage } from '@/contracts/pending'
import { createSensorService } from '@/sensors/sensorService'
import { session } from '@/stores/session'
import { connect, leave, transport } from '@/stores/connection'
import { TEAM_HEX, TEAM_LABEL, TEAM_NAME } from '@/theme'
import type { SetupStage } from '@/phone/roleComponent'
import LegsController from '@/controllers/legs/LegsController.vue'
import ArmsPending from './ArmsPending.vue'

// Morteza owns controllers/arms/**; mount it once it lands, without stubbing his directory.
const armsModules = import.meta.glob<{ default: Component }>('../controllers/arms/ArmsController.vue', { eager: true })
const ArmsController = armsModules['../controllers/arms/ArmsController.vue']?.default ?? ArmsPending

const sensors = createSensorService()

const state = computed(() => session.data.state)
const room = computed(() => session.data.room)
const assignment = session.myAssignment
const connected = computed(() => session.data.status === 'connected')
const me = computed(() => room.value?.members.find((m) => m.member_id === session.data.registration?.member_id) ?? null)
const router = useRouter()
const matchOver = computed(() => state.value?.phase === 'match_end')
function returnToMenu(): void {
  leave()
  void router.push('/')
}
const canReady = computed(() => !!state.value && (state.value.phase === 'lobby' || state.value.phase === 'role_switch'))

// Who is ready, shown while waiting to start (lobby) and between rounds (role_switch).
const seats = computed(() => {
  const r = room.value
  if (!r) return []
  return ([[1, 'arms'], [1, 'legs'], [2, 'arms'], [2, 'legs']] as const).map(([team, role]) => {
    const a = r.assignments.find((x) => x.team === team && x.role === role)
    const m = a ? r.members.find((x) => x.member_id === a.member_id) ?? null : null
    const status = !m ? 'Empty' : !m.connected ? 'Disconnected' : m.ready ? 'Ready' : m.calibrated ? 'Calibrated' : 'Setting up…'
    return { team, role, member: m, status, me: !!m && m.member_id === me.value?.member_id }
  })
})
const readyCount = computed(() => seats.value.filter((s) => s.member?.connected && s.member.ready).length)

// Team choice (lobby only; the server rejects it in any other phase).
const inLobby = computed(() => connected.value && state.value?.phase === 'lobby')
const teams = computed(() =>
  ([1, 2] as const).map((team) => {
    const roster = seats.value.filter((s) => s.team === team)
    return { team, roster, full: roster.every((s) => s.member && !s.me), mine: assignment.value?.team === team }
  }),
)
const otherTeam = computed(() => teams.value.find((t) => assignment.value && !t.mine) ?? null)
// The server answers team.choose with roles.changed or an error; until then the buttons hold.
const pendingTeam = ref<{ team: 1 | 2 | null } | null>(null)
let pendingTimer: ReturnType<typeof setTimeout> | null = null
function clearPending(): void {
  pendingTeam.value = null
  if (pendingTimer) clearTimeout(pendingTimer)
  pendingTimer = null
}
function chooseTeam(team: 1 | 2 | null): void {
  if (pendingTeam.value) return
  pendingTeam.value = { team }
  pendingTimer = setTimeout(clearPending, 5000)
  transport.send({ v: 1, type: 'team.choose', payload: { team } })
}
watch(() => assignment.value?.team ?? null, clearPending)
watch(() => session.data.lastError, (e) => e && clearPending())

// Remount the role component on welcome, lobby reset or role change so calibration and
// pointer state never carry over (roleComponent.ts lifecycle).
const generation = ref(0)
const calibrated = ref(false)
const setupStage = ref<SetupStage>('start')
// Lobby auto-start hold: the server sends phase_remaining_ms in lobby only while all four are ready.
const startingIn = computed(() => {
  const st = state.value
  return st?.phase === 'lobby' && st.phase_remaining_ms !== null ? Math.max(1, Math.ceil(st.phase_remaining_ms / 1000)) : null
})
const setupStatus = computed(() => {
  if (me.value?.ready && startingIn.value !== null) return `Everyone's ready — starting in ${startingIn.value}… Stay put.`
  if (me.value?.ready) return 'Ready — waiting for the other players.'
  if (setupStage.value === 'blocked') return 'Motion access needed. Follow the instructions below.'
  if (setupStage.value === 'pocketing') return 'Pocket your phone, then face the screen.'
  if (setupStage.value === 'calibrating') return 'Calibrating… Hold still.'
  if (setupStage.value === 'live') return availability.value === 'granted' ? 'Calibration complete. Getting ready…' : 'Waiting for motion sensors…'
  if (intent.value) return 'Setup incomplete. Follow the instructions below to try again.'
  return state.value?.phase === 'role_switch' ? 'Roles swapped. Set up your controller for the next round.' : 'Set up your controller to join the game.'
})
const availability = ref<Permission>('unknown')
const intent = ref<{ epoch: number; assignment_version: number } | null>(null)
let reported: { ready: boolean; permission: Permission; calibrated: boolean; epoch: number; version: number } | null = null

function onMessage(message: ServerMessage): void {
  const fresh =
    message.type === 'session.welcome' ||
    message.type === 'roles.changed' ||
    (message.type === 'phase.changed' && message.payload.state.phase === 'lobby')
  if (!fresh) return
  generation.value++
  setupStage.value = 'start'
  calibrated.value = false
  availability.value = 'unknown'
  intent.value = null
  reported = null
  clearGrace()
}

// Motion events can pause briefly (main-thread jank, speech/audio starting, the OS throttling a
// pocketed phone). availability then reads 'unknown' after only SENSOR_STALE_MS, and a ready=false
// during countdown/active aborts the round for everyone. Treat a sensor gap as healthy until it
// lasts SENSOR_GRACE_MS. Losing calibration is never debounced.
const SENSOR_GRACE_MS = 1500
let sensorLostAt: number | null = null
let graceTimer: ReturnType<typeof setTimeout> | null = null

function clearGrace(): void {
  sensorLostAt = null
  if (graceTimer) clearTimeout(graceTimer)
  graceTimer = null
}

function sensorsHealthy(): boolean {
  if (availability.value === 'granted') {
    clearGrace()
    return true
  }
  // Only a phone that was live (calibrated) gets the grace; setup still needs real sensor data.
  if (!calibrated.value) {
    clearGrace()
    return false
  }
  const now = performance.now()
  sensorLostAt ??= now
  if (now - sensorLostAt >= SENSOR_GRACE_MS) return false
  graceTimer ??= setTimeout(() => {
    graceTimer = null
    report()
  }, SENSOR_GRACE_MS - (now - sensorLostAt))
  return true
}

function report(): void {
  const st = state.value
  if (!connected.value || !st || !assignment.value) return
  const sensorsOk = sensorsHealthy() // always run: it also resets the grace window
  const healthy = calibrated.value && sensorsOk
  let ready: boolean
  if (canReady.value) {
    const intentValid =
      !!intent.value && intent.value.epoch === st.epoch && intent.value.assignment_version === st.assignment_version
    ready = intentValid && healthy
  } else {
    // Match underway: only losing calibration/sensors is reported, and it aborts the round (03).
    if (healthy || !me.value?.ready) return
    ready = false
  }
  // Inside the grace window the sensors still count as granted, so the report doesn't flap.
  const permission: Permission = healthy ? 'granted' : availability.value
  const next = { ready, permission, calibrated: calibrated.value, epoch: st.epoch, version: st.assignment_version }
  if (reported && JSON.stringify(reported) === JSON.stringify(next)) return
  reported = next
  transport.send({
    v: 1,
    type: 'controller.ready',
    payload: { epoch: st.epoch, assignment_version: st.assignment_version, ready, permission, calibrated: calibrated.value },
  })
}

watch([calibrated, availability, intent, connected, () => state.value?.epoch, () => state.value?.assignment_version, () => me.value?.ready], report)

function tapReady(): void {
  const st = state.value
  if (!st) return
  intent.value = { epoch: st.epoch, assignment_version: st.assignment_version }
}

const roleComponent = computed(() => (assignment.value?.role === 'arms' ? ArmsController : LegsController))
const errorText = computed(() => session.data.lastError?.message ?? null)
const connection = computed(() => {
  if (session.data.closedReason) return 'Room ended.'
  if (!session.data.registration) return 'Not in a room.'
  if (session.data.status === 'closed') return 'Disconnected.'
  if (session.data.status !== 'connected') return 'Connecting…'
  return null
})

let unsubscribe: (() => void) | null = null
onMounted(() => {
  unsubscribe = transport.subscribe(onMessage)
  if (session.data.registration) connect().catch(() => {})
})
onBeforeUnmount(() => {
  unsubscribe?.()
  clearGrace()
  clearPending()
  transport.close()
  sensors.stop()
})
</script>

<template>
  <main class="phone" :style="{ '--team': assignment ? TEAM_HEX[assignment.team] : '#666' }">
    <header>
      <span>{{ room?.room_code ?? '······' }}</span>
      <strong v-if="assignment">{{ TEAM_LABEL[assignment.team] }} · {{ assignment.role === 'arms' ? 'Arms' : 'Legs' }}</strong>
      <span v-else>Waiting for a seat…</span>
    </header>

    <p v-if="connection" class="connection">
      {{ connection }} <RouterLink v-if="session.data.status === 'closed'" to="/">Rejoin</RouterLink>
    </p>

    <section v-if="inLobby && !assignment" class="pick" aria-labelledby="pick-title">
      <h2 id="pick-title">Pick a side</h2>
      <p class="pick-lede">Each team is two phones: Arms throws, Legs runs. You take whichever spot is open.</p>
      <div class="teams">
        <button
          v-for="t in teams"
          :key="t.team"
          type="button"
          class="team-card"
          :class="{ full: t.full, busy: pendingTeam?.team === t.team }"
          :style="{ '--seat': TEAM_HEX[t.team] }"
          :disabled="t.full || !!pendingTeam"
          :aria-busy="pendingTeam?.team === t.team"
          :aria-label="`Join ${TEAM_LABEL[t.team]}${t.full ? ', full' : ''}`"
          @click="chooseTeam(t.team)"
        >
          <span class="team-head">
            <span class="team-name">{{ TEAM_NAME[t.team] }}</span>
            <span class="team-num">Team {{ t.team }}</span>
          </span>
          <span class="team-roster">
            <span v-for="s in t.roster" :key="s.role" class="spot" :class="{ open: !s.member }">
              <span class="spot-role">{{ s.role === 'arms' ? 'Arms' : 'Legs' }}</span>
              <span class="spot-who">{{ s.member ? s.member.name || 'Player' : 'Open' }}</span>
            </span>
          </span>
          <span class="team-cta">{{ pendingTeam?.team === t.team ? 'Joining…' : t.full ? 'Full' : 'Join' }}</span>
        </button>
      </div>
      <p v-if="errorText" class="error" role="alert">{{ errorText }}</p>
    </section>
    <template v-if="!connection && assignment && state">
      <section v-if="canReady" class="ready-summary" aria-live="polite" aria-atomic="true">
        <p class="setup-status">{{ setupStatus }}</p>
        <p class="count">{{ readyCount }}/4 ready</p>
      </section>
      <p v-else class="phase">{{ state.phase === 'active' ? 'Playing' : state.phase.replace('_', ' ') }}</p>
      <p v-if="errorText" class="error">{{ errorText }}</p>

      <component
        :is="roleComponent"
        :key="`${generation}:${assignment.role}:${state.assignment_version}`"
        :transport="transport"
        :sensors="sensors"
        :member_id="assignment.member_id"
        :team="assignment.team"
        :epoch="state.epoch"
        :assignment_version="state.assignment_version"
        :state="state"
        :connected="connected"
        :ready="!!me?.ready"
        @setup-stage="setupStage = $event"
        @ready="tapReady"
        @calibrated="calibrated = $event"
        @availability="availability = $event"
      />
      <section v-if="canReady" class="ready" aria-label="Player readiness">
        <ul class="seats" :aria-label="`${readyCount} of 4 ready`">
          <li v-for="s in seats" :key="`${s.team}${s.role}`" :class="{ ok: s.member?.ready, me: s.me }" :style="{ '--seat': TEAM_HEX[s.team] }">
            <span class="dot" />
            <span class="slot">T{{ s.team }} {{ s.role === 'arms' ? 'Arms' : 'Legs' }}</span>
            <span class="who">{{ s.member?.name ?? '—' }}{{ s.me ? ' (you)' : '' }}</span>
            <span class="status">{{ s.status }}</span>
          </li>
        </ul>
        <p v-if="state.phase === 'role_switch'" class="round-hint">Round {{ state.round + 1 }} starts when all 4 players are ready.</p>

        <div v-if="inLobby" class="team-bar">
          <button
            v-if="otherTeam"
            type="button"
            class="team-switch"
            :style="{ '--seat': TEAM_HEX[otherTeam.team] }"
            :disabled="otherTeam.full || !!pendingTeam"
            :aria-busy="pendingTeam?.team === otherTeam.team"
            @click="chooseTeam(otherTeam.team)"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7" /></svg>
            {{ pendingTeam?.team === otherTeam.team ? 'Switching…' : otherTeam.full ? `${TEAM_NAME[otherTeam.team]} is full` : `Switch to ${TEAM_NAME[otherTeam.team]}` }}
          </button>
          <button type="button" class="team-leave" :disabled="!!pendingTeam" :aria-busy="pendingTeam?.team === null" @click="chooseTeam(null)">
            {{ pendingTeam?.team === null ? 'Leaving…' : 'Leave team' }}
          </button>
          <p class="team-note">Switching or leaving clears everyone's Ready.</p>
        </div>
      </section>
    </template>

    <p v-else-if="state && !connection && !inLobby && !matchOver" class="hint">This match is underway. You can pick a team when it's back in the lobby.</p>

    <div v-if="matchOver" class="menu-bar">
      <button type="button" class="to-menu" @click="returnToMenu">Return to main menu</button>
    </div>
  </main>
</template>

<style scoped>
@media (max-width: 380px) {
  .seats li { grid-template-columns: auto auto minmax(0, 1fr); }
  .seats .status { grid-column: 2 / -1; }
}
.seats .slot { color: var(--seat); }

.phone {
  min-height: 100%;
  box-sizing: border-box;
  border-top: 3px solid var(--team);
  max-width: 42rem;
  margin-inline: auto;
  padding-bottom: env(safe-area-inset-bottom);
  overflow-x: hidden;
}
header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  padding: 0.75rem max(1rem, env(safe-area-inset-right)) 0.75rem max(1rem, env(safe-area-inset-left));
  font-size: 0.9rem;
  background: var(--surface);
}
header > * {
  min-width: 0;
  overflow-wrap: anywhere;
}
header span:first-child {
  font-family: ui-monospace, monospace;
  letter-spacing: 0.15em;
}
.ready { padding: 0 1rem 1rem; }
.ready-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  padding: 0.75rem 1rem 0;
}
.setup-status, .count, .round-hint { margin: 0; font-size: 0.9rem; }
.setup-status { flex: 1 1 14rem; }
.count { font-weight: 700; white-space: nowrap; }
.round-hint { margin-top: 0.75rem; color: var(--muted); }
.seats {
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
  display: grid;
  gap: 0.3rem;
}
.seats li {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.5rem;
  padding: 0.7rem 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  background: transparent;
  font-size: 0.85rem;
}
.seats li.me {
  background: var(--surface);
  border-radius: 6px;
  padding-inline: 0.5rem;
}
.seats .dot {
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  background: #555;
}
.seats li.ok .dot {
  background: #6d6;
}
.seats .slot {
  font-weight: 700;
  white-space: nowrap;
}
.seats .who {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.seats .status {
  color: var(--muted);
}
.seats li.ok .status {
  color: #6d6;
}
/* Team picker: two big cards, one per side. */
.pick {
  padding: 1.75rem max(1rem, env(safe-area-inset-right)) 1.25rem max(1rem, env(safe-area-inset-left));
}
.pick h2 {
  margin: 0 0 0.5rem;
  font: italic 900 clamp(2.5rem, 12vw, 3.25rem)/0.92 'Barlow Condensed', sans-serif;
  text-transform: uppercase;
  letter-spacing: -0.01em;
  text-wrap: balance;
}
.pick-lede {
  margin: 0 0 1.5rem;
  max-width: 38ch;
  color: var(--muted);
  font-size: 0.95rem;
  text-wrap: pretty;
}
.teams {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}
.team-card {
  --ink: color-mix(in oklab, var(--seat) 70%, white);
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
  padding: 1rem 0.85rem 0.85rem;
  font: inherit;
  text-align: left;
  color: var(--text);
  background: color-mix(in oklab, var(--seat) 13%, var(--bg));
  border: 1px solid color-mix(in oklab, var(--seat) 45%, transparent);
  border-radius: 14px;
  cursor: pointer;
  transition: transform 220ms cubic-bezier(0.16, 1, 0.3, 1), border-color 160ms ease-out, box-shadow 220ms ease-out, opacity 160ms ease-out;
}
@media (hover: hover) {
  .team-card:hover:not(:disabled) {
    border-color: var(--seat);
    box-shadow: 0 12px 28px -14px color-mix(in oklab, var(--seat) 70%, transparent);
    transform: translateY(-2px);
  }
}
.team-card:active:not(:disabled) { transform: scale(0.97); }
.team-card:focus-visible { outline: 3px solid var(--ink); outline-offset: 3px; }
.team-card:disabled { cursor: not-allowed; }
.team-card:disabled:not(.full):not(.busy) { opacity: 0.5; }
.team-card.busy { cursor: progress; border-color: var(--seat); }
.team-head { display: grid; gap: 0.15rem; }
.team-name {
  font: italic 900 clamp(2rem, 10vw, 2.75rem)/0.9 'Barlow Condensed', sans-serif;
  text-transform: uppercase;
  letter-spacing: -0.01em;
  color: var(--ink);
  overflow-wrap: anywhere;
}
.team-num { font-size: 0.75rem; font-weight: 600; color: var(--muted); }
.team-roster { display: grid; gap: 0.35rem; }
.spot {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  min-width: 0;
  padding: 0.5rem 0.6rem;
  border-radius: 8px;
  background: color-mix(in oklab, var(--bg) 75%, transparent);
  font-size: 0.85rem;
}
.spot-role {
  flex: none;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.spot-who {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}
.spot.open .spot-who { color: var(--ink); font-weight: 500; }
.team-cta {
  margin-top: auto;
  padding: 0.65rem 0.5rem;
  border-radius: 10px;
  background: var(--seat);
  color: #0b1118;
  font: italic 900 1.4rem/1 'Barlow Condensed', sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  text-align: center;
}
.team-card.busy .team-cta { animation: team-pending 900ms ease-in-out infinite alternate; }
@keyframes team-pending { to { opacity: 0.6; } }
.team-card.full { background: var(--surface); border-color: var(--line); }
.team-card.full .team-name { color: var(--muted); }
.team-card.full .team-cta { background: #2c394a; color: #a3b0c2; }
@media (max-width: 330px) {
  .teams { grid-template-columns: minmax(0, 1fr); }
}

/* Switch / leave, once seated: secondary to Ready, so it sits under the roster. */
.team-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--line);
}
.team-switch,
.team-leave {
  min-height: 3rem;
  padding: 0.7rem 1rem;
  border-radius: 10px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: border-color 160ms ease-out, background 160ms ease-out, color 160ms ease-out;
}
.team-switch {
  flex: 1 1 12rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  color: var(--text);
  background: color-mix(in oklab, var(--seat) 14%, var(--bg));
  border: 1px solid color-mix(in oklab, var(--seat) 55%, transparent);
}
.team-switch svg {
  width: 20px;
  height: 20px;
  flex: none;
  fill: none;
  stroke: var(--seat);
  stroke-width: 2.25;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.team-leave {
  flex: 0 1 auto;
  color: var(--muted);
  background: transparent;
  border: 1px solid var(--line);
}
@media (hover: hover) {
  .team-switch:hover:not(:disabled) { border-color: var(--seat); background: color-mix(in oklab, var(--seat) 22%, var(--bg)); }
  .team-leave:hover:not(:disabled) { color: var(--danger); border-color: color-mix(in oklab, var(--danger) 60%, transparent); }
}
.team-switch:active:not(:disabled),
.team-leave:active:not(:disabled) { transform: scale(0.98); }
.team-switch:disabled,
.team-leave:disabled { cursor: not-allowed; opacity: 0.55; }
.team-switch[aria-busy='true'],
.team-leave[aria-busy='true'] { cursor: progress; opacity: 1; }
.menu-bar { padding: 1rem; }
.to-menu {
  width: 100%;
  min-height: 3rem;
  padding: 0.7rem 1rem;
  border-radius: 10px;
  font: inherit;
  font-weight: 700;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--line);
  cursor: pointer;
}
.to-menu:active { transform: scale(0.98); }
.team-note { flex-basis: 100%; margin: 0.25rem 0 0; font-size: 0.8rem; color: var(--muted); }

.hint,
.phase {
  margin: 0.5rem 1rem;
  color: var(--muted);
  font-size: 0.85rem;
}
.phase {
  text-transform: capitalize;
}
.connection,
.error {
  margin: 1rem;
  color: var(--danger);
}
.connection a {
  color: #8cf;
}
</style>
