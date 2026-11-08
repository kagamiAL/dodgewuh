<script setup lang="ts">
// Lobby overlay shown on screens: room code, devices, seats, readiness and host controls.
// Everything here is display; the server decides whether a start is allowed.
import { computed } from 'vue'
import type { Member } from '@/contracts/pending'
import { session } from '@/stores/session'
import { transport } from '@/stores/connection'
import { TEAM_HEX } from '@/theme'

const room = computed(() => session.data.room)
const phase = computed(() => session.data.state?.phase ?? room.value?.phase ?? 'lobby')

const seats = computed(() => {
  const r = room.value
  if (!r) return []
  return ([[1, 'arms'], [1, 'legs'], [2, 'arms'], [2, 'legs']] as const).map(([team, role]) => {
    const a = r.assignments.find((x) => x.team === team && x.role === role)
    return { team, role, member: a ? r.members.find((m) => m.member_id === a.member_id) ?? null : null }
  })
})
const screens = computed(() => room.value?.members.filter((m) => m.device === 'screen') ?? [])
const readyCount = computed(() => seats.value.filter((s) => s.member?.connected && s.member.ready).length)

function status(m: Member | null): string {
  if (!m) return 'Waiting for a phone…'
  if (!m.connected) return 'Disconnected'
  if (m.ready) return 'Ready'
  if (m.permission === 'denied') return 'Motion access denied'
  if (m.permission === 'unsupported') return 'No motion sensors'
  return m.calibrated ? 'Calibrated' : 'Setting up…'
}

function command(type: 'match.start' | 'match.reset' | 'match.rematch'): void {
  transport.send({ v: 1, type, payload: {} })
}
</script>

<template>
  <section v-if="room" class="lobby">
    <header>
      <p class="label">Join at this site with code</p>
      <p class="code">{{ room.room_code }}</p>
    </header>

    <ol class="seats">
      <li v-for="s in seats" :key="`${s.team}${s.role}`" :style="{ '--team': TEAM_HEX[s.team] }">
        <span class="slot">T{{ s.team }} {{ s.role === 'arms' ? 'Arms' : 'Legs' }}</span>
        <span class="who">{{ s.member?.name ?? '—' }}</span>
        <span class="state" :class="{ ok: s.member?.ready, bad: s.member && !s.member.connected }">{{ status(s.member) }}</span>
      </li>
    </ol>

    <p class="screens">
      Screens:
      <span v-for="m in screens" :key="m.member_id" :class="{ off: !m.connected }">
        {{ m.name }}<template v-if="m.member_id === room.host_id"> (host)</template>
      </span>
    </p>

    <div v-if="session.isHost.value" class="host">
      <button v-if="phase === 'lobby'" :disabled="readyCount < 4" @click="command('match.start')">
        Start match ({{ readyCount }}/4 ready)
      </button>
      <button v-if="phase === 'match_end'" @click="command('match.rematch')">Rematch</button>
      <button class="secondary" @click="command('match.reset')">Reset to lobby</button>
    </div>
    <p v-if="session.data.lastError" class="error">{{ session.data.lastError.message }}</p>
  </section>
</template>

<style scoped>
.lobby {
  /* 100% so the overlay's own safe-area padding is respected; 100vw would
     ignore it and sit under a notch in landscape. */
  width: min(30rem, 100%);
  padding: 1.25rem;
  border-radius: 14px;
  background: rgba(10, 12, 16, 0.88);
  backdrop-filter: blur(6px);
}
header {
  text-align: center;
}
.label {
  margin: 0;
  color: #aaa;
  font-size: 0.85rem;
}
.code {
  margin: 0.25rem 0 1rem;
  font: 700 clamp(2rem, 13vw, 3rem) / 1.1 ui-monospace, monospace;
  letter-spacing: 0.2em;
  text-indent: 0.2em;
  overflow-wrap: anywhere;
}
.seats {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.4rem;
}
.seats li {
  display: grid;
  grid-template-columns: minmax(0, 5.5rem) minmax(0, 1fr) minmax(0, auto);
  gap: 0.5rem;
  align-items: center;
  padding: 0.55rem 0.75rem;
  border-left: 5px solid var(--team);
  border-radius: 6px;
  background: #1a1d22;
}
/* Below ~380px the three columns stop fitting side by side. */
@media (max-width: 24rem) {
  .seats li {
    grid-template-columns: minmax(0, 1fr) minmax(0, auto);
  }
  .state {
    grid-column: 1 / -1;
  }
}
.slot {
  font-weight: 700;
  white-space: nowrap;
}
.who {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.state {
  min-width: 0;
  font-size: 0.85rem;
  color: #aaa;
}
.state.ok {
  color: #6d6;
}
.state.bad {
  color: #f77;
}
.screens {
  font-size: 0.85rem;
  color: #aaa;
}
.screens span + span::before {
  content: ', ';
}
.screens .off {
  text-decoration: line-through;
}
.host {
  display: grid;
  gap: 0.5rem;
}
button {
  min-height: 2.75rem;
  padding: 0.5rem 0.75rem;
  font: inherit;
  font-weight: 700;
  border: 0;
  border-radius: 10px;
  background: #8cf;
  color: #000;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
button:disabled {
  opacity: 0.4;
}
button.secondary {
  background: #333;
  color: #ddd;
}
.error {
  color: #f77;
  margin-bottom: 0;
}
</style>
