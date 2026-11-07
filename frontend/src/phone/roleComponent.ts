// The contract between PhoneShell (Ryan) and the Arms/Legs controllers
// (Morteza: controllers/arms/ArmsController.vue, Tysen: controllers/legs/LegsController.vue).
// Source: plans/03-api-contracts.md, "Frontend module seams".

import type { ID, Permission, SensorService, State, Team, Transport } from '@/contracts/pending'

/** Props PhoneShell passes to whichever role component is mounted. */
export interface RoleComponentProps {
  transport: Transport
  sensors: SensorService
  member_id: ID
  team: Team
  /** Current input epoch; stamp it on every input.legs / input.arms. */
  epoch: number
  assignment_version: number
  /** Latest authoritative state (possession, zone feedback). Display only. */
  state: State
  /** True only while the transport status is 'connected'. Gate controls on it. */
  connected: boolean
}

/**
 * Events a role component emits to PhoneShell.
 * - calibrated: true once neutral calibration succeeds for this role; false the moment it is lost.
 * - availability: 'granted' only while this role's required sensor samples are fresh and finite.
 * PhoneShell turns these into controller.ready messages; role components never send ready themselves.
 */
export interface RoleComponentEmits {
  (e: 'calibrated', value: boolean): void
  (e: 'availability', value: Permission): void
}

/*
 * PhoneShell lifecycle the controllers can rely on:
 * - The component is unmounted and a fresh one mounted on welcome, lobby reset or role change,
 *   so calibration and pointer state never carry over. Clean up listeners on unmount.
 * - Countdown/active epoch changes arrive as a new `epoch` prop without remounting: clear input
 *   latches (Hold) but keep calibration.
 * - PhoneShell sends ready=true only after the player taps Ready with availability 'granted' and
 *   calibrated true, and sends ready=false immediately if either drops.
 * - PhoneShell never sends gameplay input; the role component owns input.legs / input.arms.
 */
