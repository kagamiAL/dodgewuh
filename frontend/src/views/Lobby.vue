<script setup lang="ts">
// Lobby overlay shown on screens: room code, devices, seats, readiness and host controls.
// Also the between-rounds ready view (role_switch) and the match result (match_end).
// Everything here is display; the server decides whether a start is allowed.
import { computed } from 'vue'
import type { Member } from '@/contracts/pending'
import { session } from '@/stores/session'
import { transport } from '@/stores/connection'
import { TEAM_HEX } from '@/theme'
import { MAX_ROUNDS } from '@/game/constants'

const room = computed(() => session.data.room)
const state = computed(() => session.data.state)
const phase = computed(() => state.value?.phase ?? room.value?.phase ?? 'lobby')
const scoreText = computed(() => (state.value ? `${state.value.score.t1}–${state.value.score.t2}` : ''))

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
    <header v-if="phase === 'role_switch' && state" class="between">
      <p class="label">Round {{ state.round }} of {{ MAX_ROUNDS }} done · score {{ scoreText }}</p>
      <h2 class="title">Swap roles</h2>
      <p class="label">
        Every phone: set up your new role, then tap <strong>Ready</strong>.<br>
        Round {{ state.round + 1 }} starts when all 4 are ready.
      </p>
      <div class="progress" :aria-label="`${readyCount} of 4 ready`">
        <span v-for="s in seats" :key="`p${s.team}${s.role}`" :class="{ on: s.member?.connected && s.member.ready }" />
      </div>
      <p class="label count">{{ readyCount }}/4 ready</p>
    </header>
    <header v-else-if="phase === 'match_end' && state" class="between">
      <p class="label">Match over after round {{ state.round }}</p>
      <h2 class="title" :style="{ color: state.winner ? TEAM_HEX[state.winner] : undefined }">
        {{ state.winner ? `Team ${state.winner} wins` : 'Draw' }} {{ scoreText }}
      </h2>
    </header>
    <header v-else>
      <h2 class="title">Join the room</h2>
      <p class="code">{{ room.room_code }}</p>
      <p class="label join-hint">Join at this site with code</p>
    </header>

    <ol class="seats">
      <li v-for="s in seats" :key="`${s.team}${s.role}`" :style="{ '--team': TEAM_HEX[s.team] }">
        <span class="slot">T{{ s.team }} {{ s.role === 'arms' ? 'Arms' : 'Legs' }}</span>
        <span class="who">{{ s.member?.name ?? '—' }}</span>
        <span class="state" :class="{ ok: s.member?.ready, bad: s.member && !s.member.connected }">{{ status(s.member) }}</span>
      </li>
    </ol>

    <p v-if="phase === 'role_switch' || phase === 'match_end'" class="screens">Room code {{ room.room_code }}</p>
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
  <section v-else class="lobby pending" aria-live="polite">
    <h2 class="title">{{ session.data.registration ? 'Connecting to your room' : 'Join a room to play' }}</h2>
    <p v-if="session.data.registration" class="code">{{ session.data.registration.room_code }}</p>
    <p v-if="session.data.closedReason">This room has ended. Create a new room to play again.</p>
    <p v-else-if="session.data.status === 'reconnecting'">The connection was interrupted. Retrying automatically…</p>
    <p v-else-if="session.data.status === 'closed' && session.data.registration">Could not connect to the room. Return home to rejoin or create a new room.</p>
    <p v-else-if="session.data.registration">Waiting for the game server. Player seats and host controls will appear once connected.</p>
    <RouterLink to="/">Back to home</RouterLink>
  </section>
</template>

<style scoped>
.pending { text-align: center; }
.pending p { color: var(--muted); }
.pending a { display: inline-block; color: var(--blue); padding: 0.75rem; }
.join-hint { padding-bottom: 1.25rem; }
button:hover:not(:disabled) { filter: brightness(1.12); }
.code { color: var(--blue); }
.lobby {
  /* 100% so the overlay's own safe-area padding is respected; 100vw would
     ignore it and sit under a notch in landscape. */
  width: min(35rem, 100%);
  padding: clamp(1.25rem, 4vw, 2rem);
  border-radius: 16px;
  background: var(--bg);
  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.4);
}
header {
  text-align: center;
}
.between {
  margin-bottom: 1rem;
}
.title {
  margin: 0.35rem 0;
  font: italic 900 clamp(2rem, 7vw, 3rem) / 1 'Barlow Condensed', sans-serif;
  text-transform: uppercase;
}
.progress {
  display: flex;
  justify-content: center;
  gap: 0.4rem;
  margin: 0.75rem 0 0.25rem;
}
.progress span {
  width: 2.5rem;
  height: 0.5rem;
  border-radius: 4px;
  background: #333;
}
.progress span.on {
  background: #6d6;
}
.count {
  font-weight: 700;
  color: #ddd;
}
.label {
  margin: 0;
  color: var(--muted);
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
  padding: 1rem 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  background: transparent;
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
  color: var(--team);
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
  color: var(--muted);
}
.state.ok {
  color: #6d6;
}
.state.bad {
  color: var(--danger);
}
.screens {
  font-size: 0.85rem;
  color: var(--muted);
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
  background: var(--blue);
  color: #000;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
button:disabled {
  background: #2c394a;
  color: #a3b0c2;
  cursor: not-allowed;
}
button.secondary {
  background: var(--surface);
  color: var(--text);
}
.error {
  color: var(--danger);
  margin-bottom: 0;
}
</style>
