<script setup lang="ts">
// PhoneShell: mounts the role component for this phone's current assignment and owns
// controller.ready (plans/03 "Frontend module seams", src/phone/roleComponent.ts).
//
// Ready is an explicit tap that arms an intent for the current epoch/assignment_version.
// ready=true is sent once the role component reports calibrated + granted, so a Legs player
// can tap Ready, then Start and pocket the phone. Losing either sends ready=false at once.
// The shell never sends gameplay input.
import { computed, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import type { Permission, ServerMessage } from '@/contracts/pending'
import { createSensorService } from '@/sensors/sensorService'
import { session } from '@/stores/session'
import { connect, transport } from '@/stores/connection'
import { TEAM_HEX, TEAM_LABEL } from '@/theme'
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

// Remount the role component on welcome, lobby reset or role change so calibration and
// pointer state never carry over (roleComponent.ts lifecycle).
const generation = ref(0)
const calibrated = ref(false)
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
  intent.value = intent.value ? null : { epoch: st.epoch, assignment_version: st.assignment_version }
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

    <template v-else-if="assignment && state">
      <section v-if="canReady" class="ready">
        <button :class="{ on: intent }" @click="tapReady">{{ intent ? (me?.ready ? 'Ready ✓' : 'Ready — finish setup below') : 'Tap when ready' }}</button>
        <p class="hint">{{ state.phase === 'role_switch' ? 'Roles swapped. Recalibrate, then tap Ready.' : 'Tap Ready, then set up your controller below.' }}</p>
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
        @calibrated="calibrated = $event"
        @availability="availability = $event"
      />
    </template>

    <p v-else-if="state" class="hint">All four phone seats are taken. Join as a screen instead.</p>
  </main>
</template>

<style scoped>
.phone {
  min-height: 100%;
  box-sizing: border-box;
  border-top: 6px solid var(--team);
}
header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1rem;
  font-size: 0.9rem;
  background: #181818;
}
header span:first-child {
  font-family: ui-monospace, monospace;
  letter-spacing: 0.15em;
}
.ready {
  padding: 1rem 1rem 0;
}
.ready button {
  width: 100%;
  min-height: 3.5rem;
  font: inherit;
  font-weight: 700;
  border: 2px solid var(--team);
  border-radius: 12px;
  background: transparent;
  color: inherit;
}
.ready button.on {
  background: var(--team);
  color: #000;
}
.hint,
.phase {
  margin: 0.5rem 1rem;
  color: #aaa;
  font-size: 0.85rem;
}
.phase {
  text-transform: capitalize;
}
.connection,
.error {
  margin: 1rem;
  color: #f77;
}
.connection a {
  color: #8cf;
}
</style>
