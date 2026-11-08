<script setup lang="ts">
// PhoneShell: mounts the role component for this phone's current assignment and owns
// controller.ready (plans/03 "Frontend module seams", src/phone/roleComponent.ts).
//
// Ready is an explicit tap that arms an intent for the current epoch/assignment_version.
// ready=true is sent once the role component reports calibrated + granted, so a Legs player
// starts calibration with the same tap. Losing either sends ready=false at once.
// The shell never sends gameplay input.
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import type { Permission, ServerMessage } from '@/contracts/pending'
import { createSensorService } from '@/sensors/sensorService'
import { session } from '@/stores/session'
import { connect, transport } from '@/stores/connection'
import { TEAM_HEX, TEAM_LABEL } from '@/theme'
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

// Remount the role component on welcome, lobby reset or role change so calibration and
// pointer state never carry over (roleComponent.ts lifecycle).
const generation = ref(0)
const calibrated = ref(false)
const setupStage = ref<SetupStage>('start')
const setupStatus = computed(() => {
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
}

function report(): void {
  const st = state.value
  if (!connected.value || !st || !assignment.value) return
  const healthy = calibrated.value && availability.value === 'granted'
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
  const next = { ready, permission: availability.value, calibrated: calibrated.value, epoch: st.epoch, version: st.assignment_version }
  if (reported && JSON.stringify(reported) === JSON.stringify(next)) return
  reported = next
  transport.send({
    v: 1,
    type: 'controller.ready',
    payload: { epoch: st.epoch, assignment_version: st.assignment_version, ready, permission: availability.value, calibrated: calibrated.value },
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

    <section v-if="connected && state?.phase === 'lobby'" class="ready-summary">
      <h2>Choose your team</h2>
      <p>Pick a team to join a free role. Changing teams resets player readiness.</p>
      <button v-for="team in ([1, 2] as const)" :key="team"
        :disabled="assignment?.team === team || seats.filter(s => s.team === team && s.member).length >= 2"
        @click="transport.send({ v: 1, type: 'team.choose', payload: { team } })">
        {{ TEAM_LABEL[team] }}{{ assignment?.team === team ? ' · Your team' : '' }}
      </button>
      <button v-if="assignment" @click="transport.send({ v: 1, type: 'team.choose', payload: { team: null } })">Leave team</button>
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
      </section>
    </template>

    <p v-else-if="state" class="hint">Choose a team with an open spot to play.</p>
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
