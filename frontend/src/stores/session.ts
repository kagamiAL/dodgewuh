// Session store: the single place the frontend applies server messages.
// Screens and PhoneShell read from it; Transport (Alan) feeds it via apply().
// Small reactive object, no state library (plans/04-repository-structure.md).

import { computed, shallowReactive, shallowReadonly } from 'vue'
import type {
  Assignment,
  Registration,
  Room,
  ServerMessage,
  State,
  TransportStatus,
} from '@/contracts/pending'

const REGISTRATION_KEY = 'dodgewuh.registration'

interface SessionState {
  registration: Registration | null
  status: TransportStatus
  room: Room | null
  state: State | null
  lastError: { code: string; message: string } | null
  closedReason: 'host_left' | 'expired' | 'server_shutdown' | null
}

// Shallow: room/state are replaced wholesale on each message, never mutated, so
// deep proxies would only add cost at 20 snapshots/s.
const s = shallowReactive<SessionState>({
  registration: loadRegistration(),
  status: 'closed',
  room: null,
  state: null,
  lastError: null,
  closedReason: null,
})

function loadRegistration(): Registration | null {
  try {
    const raw = sessionStorage.getItem(REGISTRATION_KEY)
    return raw ? (JSON.parse(raw) as Registration) : null
  } catch {
    return null
  }
}

/** Never apply older epoch/assignment_version (03, "WebSocket lifecycle"), nor older ticks. */
function isNewer(next: State, current: State | null): boolean {
  if (!current) return true
  if (next.epoch !== current.epoch) return next.epoch > current.epoch
  if (next.assignment_version !== current.assignment_version) return next.assignment_version > current.assignment_version
  return next.tick >= current.tick
}

export const session = {
  /** Read-only view for components. */
  data: shallowReadonly(s),

  /** This device's assignment, or null for screens / unassigned phones. */
  myAssignment: computed<Assignment | null>(() => {
    const id = s.registration?.member_id
    const list = s.state?.assignments ?? s.room?.assignments ?? []
    return list.find((a) => a.member_id === id) ?? null
  }),

  isHost: computed(() => !!s.room && s.room.host_id === s.registration?.member_id),

  setRegistration(reg: Registration | null): void {
    s.registration = reg
    try {
      if (reg) sessionStorage.setItem(REGISTRATION_KEY, JSON.stringify(reg))
      else sessionStorage.removeItem(REGISTRATION_KEY)
    } catch {
      // Storage unavailable (private mode): keep the in-memory copy only.
    }
  },

  setStatus(status: TransportStatus): void {
    s.status = status
  },

  /** Apply one validated server message. Same entry point for live and mock sources. */
  apply(msg: ServerMessage): void {
    switch (msg.type) {
      case 'session.welcome':
        // Full baseline: replaces everything regardless of epoch.
        s.room = msg.payload.room
        s.state = msg.payload.state
        s.lastError = null
        s.closedReason = null
        break
      case 'room.updated':
        if (!s.room || msg.payload.room.revision >= s.room.revision) s.room = msg.payload.room
        break
      case 'state.snapshot':
        if (isNewer(msg.payload.state, s.state)) s.state = msg.payload.state
        break
      case 'phase.changed':
        if (isNewer(msg.payload.state, s.state)) {
          s.state = msg.payload.state
          // Errors from the previous phase no longer apply.
          s.lastError = null
        }
        break
      case 'roles.changed': {
        // Apply the new mapping now. PhoneShell reacts to this message by re-reporting readiness,
        // and that report must carry the new assignment_version, not wait for the follow-up
        // snapshot (which the server may supersede and never deliver in lobby).
        const st = s.state
        const p = msg.payload
        if (st && p.epoch === st.epoch && p.assignment_version > st.assignment_version) {
          s.state = { ...st, assignments: p.assignments, assignment_version: p.assignment_version }
        }
        // Errors about the previous mapping (e.g. STALE_ASSIGNMENT) no longer apply.
        s.lastError = null
        break
      }
      case 'error':
        // Gameplay input already in flight when the phase changes (e.g. a mid-match abort to
        // lobby) is rejected as stale. That race is expected and not something the player can act on.
        if (msg.payload.ref_seq !== null && (msg.payload.code === 'INVALID_PHASE' || msg.payload.code === 'STALE_EPOCH')) break
        s.lastError = { code: msg.payload.code, message: msg.payload.message }
        break
      case 'room.closed':
        s.closedReason = msg.payload.reason
        break
      case 'session.pong':
        break
    }
  },

  reset(): void {
    s.room = null
    s.state = null
    s.lastError = null
    s.closedReason = null
    s.status = 'closed'
    this.setRegistration(null)
  },
}
