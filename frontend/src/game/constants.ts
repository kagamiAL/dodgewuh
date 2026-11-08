import * as pc from 'playcanvas'
import { TEAM_HEX } from '@/theme'

// Gameplay dimensions mirrored from plans/02-game-specification.md (metres).
// 02 is the authority; if a value changes there, change it here.
export const COURT_HALF_WIDTH = 6
export const COURT_HALF_DEPTH = 9
export const NO_THROW_HALF_DEPTH = 2
export const CHARACTER_RADIUS = 0.45
export const CHARACTER_HEIGHT = 1.8
export const BALL_RADIUS = 0.3
// Best of 3: first to MATCH_POINTS, otherwise the match ends after MAX_ROUNDS (higher score wins, equal = draw).
export const MATCH_POINTS = 2
export const MAX_ROUNDS = 3

// Visual-only values (not gameplay rules).
export const LINE_WIDTH = 0.08
export const HELD_BALL_HEIGHT = 1.1
export const HELD_BALL_SIDE = 0.8 // character radius + ball radius + a little gap
export const HELD_BALL_FORWARD = 0.15
export const FLYING_BALL_HEIGHT = 1.0
export const AIM_ARROW_LENGTH = 1.4
export const BALL_COLOR = new pc.Color(0.95, 0.85, 0.2)
export const TEAM_COLORS: Record<1 | 2, pc.Color> = {
  1: new pc.Color().fromString(TEAM_HEX[1]),
  2: new pc.Color().fromString(TEAM_HEX[2]),
}
