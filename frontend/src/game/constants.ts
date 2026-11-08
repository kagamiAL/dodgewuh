import * as pc from 'playcanvas'
import { TEAM_HEX } from '@/theme'

// Gameplay dimensions mirrored from plans/02-game-specification.md (metres).
// 02 is the authority; if a value changes there, change it here.
export const COURT_HALF_WIDTH = 7.8
export const COURT_HALF_DEPTH = 9
export const NO_THROW_HALF_DEPTH = 2
export const CHARACTER_RADIUS = 0.45
export const CHARACTER_HEIGHT = 1.8
export const BALL_RADIUS = 0.3
// Best of 3: first to MATCH_POINTS, otherwise the match ends after MAX_ROUNDS (higher score wins, equal = draw).
export const MATCH_POINTS = 2
export const MAX_ROUNDS = 3
// Camera dodge, mirrored from backend/simulation/constants.py: while State.dodge is set the
// server steps 1 tick per SLOWMO_FACTOR, and the victim's screen judges after DODGE_WINDOW_MS.
export const SLOWMO_FACTOR = 8
export const DODGE_WINDOW_MS = 1100

// Visual-only values (not gameplay rules).
export const LINE_WIDTH = 0.08
export const HELD_BALL_HEIGHT = 1.1
export const HELD_BALL_SIDE = 0.8 // character radius + ball radius + a little gap
export const HELD_BALL_FORWARD = 0.15
export const FLYING_BALL_HEIGHT = 1.0
export const AIM_ARROW_LENGTH = 1.4
export const BALL_COLOR = new pc.Color(0.85, 0.07, 0.09) // red (was yellow 0.95, 0.85, 0.2)
/** How much of the team colour glows on a held/flying ball: a hint, so the ball still reads red. */
export const BALL_TEAM_GLOW = 0.35
// Ball flight, mirrored from backend/simulation/constants.py for smooth display between snapshots.
export const BALL_GRAVITY = 1.9
export const THROW_HEIGHT = 1.5
// Trail behind flying balls: ghost balls in the thrower's team colour, spaced by distance travelled
// (not per frame), so it's the same streak at any frame rate and during dodge slow motion.
export const TRAIL_LENGTH = 14
export const TRAIL_SPACING = 0.25 // metres between ghosts along the ball's path -> ~3.5 m streak
export const TEAM_COLORS: Record<1 | 2, pc.Color> = {
  1: new pc.Color().fromString(TEAM_HEX[1]),
  2: new pc.Color().fromString(TEAM_HEX[2]),
}
