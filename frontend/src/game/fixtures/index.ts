import type { ServerMessage } from '@/contracts/pending'
import resetLobby from './reset-lobby.json'
import activeMovement from './active-movement.json'
import { activeSnapshotState } from './activeSnapshot'

// Dev-only snapshot fixtures for /screen?mock=<name>.
//
// reset-lobby / active-movement: produced by Richard's real Simulation
// (backend/simulation/fixtures/, commit 44b43fe), copied verbatim. Canonical home is
// Alan's contracts/fixtures/valid/; switch to those (and his validator) when they land.
// held: the 03 example 11–12 state, kept because Richard's M1 fixtures have no held ball yet.
//
// JSON imports widen literal types (e.g. "state.snapshot" -> string), hence the casts.
export const FIXTURES: Record<string, ServerMessage> = {
  lobby: resetLobby as ServerMessage,
  movement: activeMovement as ServerMessage,
  held: { v: 1, type: 'state.snapshot', server_ms: 0, payload: { state: activeSnapshotState } },
}
