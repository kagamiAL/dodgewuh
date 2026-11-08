// Local mirror of the State shape in plans/03-api-contracts.md, used only by the
// renderer. Alan owns the canonical types in src/generated/protocol.ts; when that
// lands, replace these with re-exports from '@/generated/protocol'. Do not add or
// rename fields here: 03 is the authority.

export type ID = string
export type Team = 1 | 2
export type Role = 'arms' | 'legs'
export type Phase = 'lobby' | 'countdown' | 'active' | 'round_end' | 'role_switch' | 'match_end'
export type Vec2 = { x: number; z: number }

export interface Assignment {
  member_id: ID
  team: Team
  role: Role
}

export interface Character {
  team: Team
  pos: Vec2
  aim: Vec2
  held_ball_id: ID | null
  /** Cosmetic throwing-arm angle in degrees from the Arms phone (90 up, >90 back, 0 forward). */
  arm_pitch?: number | null
}

export interface Ball {
  ball_id: ID
  mode: 'ground' | 'held' | 'flying' | 'respawning'
  pos: Vec2
  velocity: Vec2
  owner_team: Team | null
  shooter_team: Team | null
  respawn_in_ms: number
  /** Ball centre height in metres. Rendering only; never a gameplay input. */
  height: number
}

export interface Result {
  reason: 'hit' | 'timeout' | 'simultaneous'
  winner: Team | null
  hit_ball_id: ID | null
  victim_team: Team | null
}

export interface State {
  tick: number
  epoch: number
  round: number
  phase: Phase
  remaining_ms: number
  phase_remaining_ms: number | null
  score: { t1: number; t2: number }
  characters: Character[]
  balls: Ball[]
  assignments: Assignment[]
  assignment_version: number
  result: Result | null
  winner: Team | null
}
