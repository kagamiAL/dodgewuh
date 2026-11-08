import * as pc from 'playcanvas'
import {
  AIM_ARROW_LENGTH,
  BALL_COLOR,
  BALL_RADIUS,
  CHARACTER_HEIGHT,
  CHARACTER_RADIUS,
  FLYING_BALL_HEIGHT,
  HELD_BALL_FORWARD,
  HELD_BALL_HEIGHT,
  HELD_BALL_SIDE,
  TEAM_COLORS,
} from './constants'
import { instantiateCharacterModel, RIGHT_HAND_LOCAL, type CharacterRig } from './characterModel'
import { toScene } from './coords'
import { headingDeg, Ragdoll, type RagdollConfig } from './ragdoll'
import type { Ball, Character, State, Team } from './state'

function material(diffuse: pc.Color, emissive = new pc.Color(0, 0, 0)): pc.StandardMaterial {
  const m = new pc.StandardMaterial()
  m.diffuse = diffuse
  m.emissive = emissive
  m.update()
  return m
}

interface CharacterView {
  team: Team
  root: pc.Entity
  body: pc.Entity
  aimPivot: pc.Entity
  /** Turned toward aim; holds the model once loaded. */
  facing: pc.Entity
  rig: CharacterRig | null
  ragdoll: Ragdoll | null
  // Cosmetic motion inputs, derived from consecutive snapshots.
  lastPos: pc.Vec3 | null
  lastSnapshotMs: number
  velX: number
  velZ: number
  aimHeading: number
  holding: boolean
  heldBallId: string | null
  epoch: number
  /**
   * Which way the character faces (scene space, unit), taken from its movement: Legs
   * players jog the way they face. Null until it moves after a reset; held when it stops.
   */
  heading: pc.Vec3 | null
}

// Snapshot-derived velocity is dropped if positions jump this far (reset/teleport)
// or no snapshot arrives for this long (stale stream).
const TELEPORT_M = 1.5
const VELOCITY_STALE_MS = 250
/** Slower than this (m/s) counts as standing still, so heading holds instead of jittering. */
const HEADING_MIN_SPEED = 0.6

function createCharacter(team: Team): CharacterView {
  const color = TEAM_COLORS[team]
  const root = new pc.Entity(`Character${team}`)

  // Capsule primitive is radius 0.5 / height 2 at unit scale.
  const body = new pc.Entity('Body')
  body.addComponent('render', { type: 'capsule', material: material(color) })
  body.setLocalScale(CHARACTER_RADIUS * 2, CHARACTER_HEIGHT / 2, CHARACTER_RADIUS * 2)
  body.setLocalPosition(0, CHARACTER_HEIGHT / 2, 0)
  root.addChild(body)

  // Aim arrow on the floor: the pivot's -Z axis is turned toward the aim direction.
  const aimPivot = new pc.Entity('AimPivot')
  const arrowMat = material(color, color)
  const shaftLength = AIM_ARROW_LENGTH - 0.3
  const shaft = new pc.Entity('Shaft')
  shaft.addComponent('render', { type: 'box', material: arrowMat })
  shaft.setLocalScale(0.1, 0.03, shaftLength)
  shaft.setLocalPosition(0, 0.03, -(CHARACTER_RADIUS + shaftLength / 2))
  const head = new pc.Entity('Head')
  head.addComponent('render', { type: 'cone', material: arrowMat })
  head.setLocalScale(0.3, 0.3, 0.3)
  head.setLocalEulerAngles(-90, 0, 0) // cone tip from +Y to -Z
  head.setLocalPosition(0, 0.03, -(CHARACTER_RADIUS + shaftLength + 0.15))
  aimPivot.addChild(shaft)
  aimPivot.addChild(head)
  root.addChild(aimPivot)

  const facing = new pc.Entity('Facing')
  root.addChild(facing)

  return {
    team, root, body, aimPivot, facing, rig: null, ragdoll: null,
    lastPos: null, lastSnapshotMs: 0, velX: 0, velZ: 0, aimHeading: 0,
    holding: false, heldBallId: null, epoch: -1, heading: null,
  }
}

/** Replaces the placeholder capsule with the character model. */
function attachModel(view: CharacterView, asset: pc.Asset, cfg: RagdollConfig): void {
  const model = instantiateCharacterModel(asset, view.team)
  view.facing.addChild(model.entity)
  view.rig = model.rig
  view.ragdoll = new Ragdoll(model.rig, cfg)
  view.body.enabled = false
}

interface BallView {
  entity: pc.Entity
  material: pc.StandardMaterial
  tint: string
  /** While flying: last server position/velocity (scene space) and when it arrived. */
  flight: { from: pc.Vec3; vel: pc.Vec3; at: number } | null
}

function createBall(id: string): BallView {
  const m = material(BALL_COLOR)
  const entity = new pc.Entity(`Ball_${id}`)
  entity.addComponent('render', { type: 'sphere', material: m })
  entity.setLocalScale(BALL_RADIUS * 2, BALL_RADIUS * 2, BALL_RADIUS * 2)
  return { entity, material: m, tint: '', flight: null }
}

/**
 * Flying balls are drawn ahead of the last snapshot along their velocity so a 20 Hz feed
 * looks smooth up close. Capped so a ball that just hit or expired doesn't sail on.
 * Display only: the server's next position always replaces it.
 */
const FLIGHT_EXTRAPOLATE_MAX_MS = 120

/**
 * Draws server State. Holds no game logic: every position, possession and mode comes
 * straight from the snapshot. Entities are created once per team / ball_id and reused.
 */
export class StateRenderer {
  private readonly characters = new Map<Team, CharacterView>()
  private readonly balls = new Map<string, BallView>()
  private model: { asset: pc.Asset; cfg: RagdollConfig } | null = null
  private readonly characterRoot = new pc.Entity('Characters')
  private readonly ballRoot = new pc.Entity('Balls')
  /** ball_id -> owning team, for balls that must follow a hand every frame. */
  private readonly heldBy = new Map<string, Team>()
  /** The first-person viewer's own character is not drawn. */
  private hiddenTeam: Team | null = null
  /** The ball the first-person viewer holds; the scene draws it in front of the camera. */
  private ownHeld: pc.Entity | null = null

  constructor(parent: pc.Entity) {
    parent.addChild(this.characterRoot)
    parent.addChild(this.ballRoot)
  }

  /** Use the loaded character model for existing and future characters. */
  setCharacterModel(asset: pc.Asset, cfg: RagdollConfig): void {
    this.model = { asset, cfg }
    for (const view of this.characters.values()) attachModel(view, asset, cfg)
  }

  render(state: State): void {
    const now = performance.now()
    for (const c of state.characters) this.renderCharacter(c, state, now)
    this.heldBy.clear()
    this.ownHeld = null
    for (const b of state.balls) this.renderBall(b, state.characters, now)
  }

  /** Hide one team's character (the first-person viewer's own body); null shows both. */
  setHiddenTeam(team: Team | null): void {
    this.hiddenTeam = team
    for (const view of this.characters.values()) view.root.enabled = view.team !== team
  }

  /**
   * Where a team's character is and which way it faces (scene space), for a camera to
   * follow. Facing comes from movement; before the first move it is the team's forward.
   */
  pointOfView(team: Team): { pos: pc.Vec3; forward: pc.Vec3; aim: pc.Vec3; holding: boolean } | null {
    const view = this.characters.get(team)
    if (!view) return null
    const forward = view.heading ?? toScene(0, team === 1 ? 1 : -1)
    return { pos: view.root.getPosition(), forward, aim: view.aimPivot.forward, holding: view.holding }
  }

  /** The hidden (first-person) team's held ball, for the scene to place by the camera. */
  ownHeldBall(): pc.Entity | null {
    return this.ownHeld
  }

  /** Per-frame cosmetic animation. Never changes where anything is in the game. */
  update(dt: number): void {
    const now = performance.now()
    for (const view of this.characters.values()) {
      if (!view.ragdoll) continue
      const stale = now - view.lastSnapshotMs > VELOCITY_STALE_MS
      view.ragdoll.update(dt, {
        velX: stale ? 0 : view.velX,
        velZ: stale ? 0 : view.velZ,
        aimHeading: view.aimHeading,
        holding: view.holding,
      })
    }
    // Held balls follow the (animated) right hand.
    for (const [ballId, team] of this.heldBy) {
      const armR = this.characters.get(team)?.rig?.armR
      const ball = this.balls.get(ballId)
      if (armR && ball) ball.entity.setPosition(armR.getWorldTransform().transformPoint(RIGHT_HAND_LOCAL))
    }
    for (const ball of this.balls.values()) {
      const f = ball.flight
      if (!f) continue
      const s = Math.min(now - f.at, FLIGHT_EXTRAPOLATE_MAX_MS) / 1000
      ball.entity.setPosition(f.from.x + f.vel.x * s, f.from.y, f.from.z + f.vel.z * s)
    }
  }

  private renderCharacter(c: Character, state: State, now: number): void {
    let view = this.characters.get(c.team)
    if (!view) {
      view = createCharacter(c.team)
      this.characters.set(c.team, view)
      this.characterRoot.addChild(view.root)
      view.root.enabled = view.team !== this.hiddenTeam
      if (this.model) attachModel(view, this.model.asset, this.model.cfg)
    }
    const pos = toScene(c.pos.x, c.pos.z)
    this.trackMotion(view, pos, state.epoch, now)
    view.root.setPosition(pos)
    const aimTarget = toScene(c.pos.x + c.aim.x, c.pos.z + c.aim.z)
    view.aimPivot.lookAt(aimTarget)
    view.facing.lookAt(aimTarget)
    view.aimHeading = headingDeg(aimTarget.x - pos.x, aimTarget.z - pos.z)

    // A throw: this team's held ball is now flying with them as shooter.
    if (view.heldBallId && c.held_ball_id === null) {
      const thrown = state.balls.find((b) => b.ball_id === view.heldBallId)
      if (thrown?.mode === 'flying' && thrown.shooter_team === c.team) view.ragdoll?.kickThrow()
    }
    view.heldBallId = c.held_ball_id
    view.holding = c.held_ball_id !== null
  }

  /** Velocity from consecutive snapshots; zeroed across resets and jumps. */
  private trackMotion(view: CharacterView, pos: pc.Vec3, epoch: number, now: number): void {
    const last = view.lastPos
    const dtMs = now - view.lastSnapshotMs
    const jumped = last !== null && last.distance(pos) > TELEPORT_M
    if (last && dtMs > 0 && dtMs < VELOCITY_STALE_MS && !jumped && epoch === view.epoch) {
      view.velX = ((pos.x - last.x) * 1000) / dtMs
      view.velZ = ((pos.z - last.z) * 1000) / dtMs
      const speed = Math.hypot(view.velX, view.velZ)
      if (speed > HEADING_MIN_SPEED) view.heading = new pc.Vec3(view.velX / speed, 0, view.velZ / speed)
    } else {
      view.velX = 0
      view.velZ = 0
      // Reset or teleport (new round, abort): face the opponent again until the next move.
      if (jumped || epoch !== view.epoch) view.heading = null
    }
    view.lastPos = pos.clone()
    view.lastSnapshotMs = now
    view.epoch = epoch
  }

  private renderBall(b: Ball, characters: Character[], now: number): void {
    let view = this.balls.get(b.ball_id)
    if (!view) {
      view = createBall(b.ball_id)
      this.balls.set(b.ball_id, view)
      this.ballRoot.addChild(view.entity)
    }

    view.entity.enabled = b.mode !== 'respawning'
    view.flight = null

    if (b.mode === 'held' && b.owner_team !== null && b.owner_team === this.hiddenTeam) {
      this.ownHeld = view.entity // positioned by the scene, in front of the camera
      this.tintBall(view, b)
      return
    }

    if (b.mode === 'held') {
      // Held pose comes from the owner in state, never from proximity.
      // In the model's right hand when the rig is loaded.
      const ownerView = b.owner_team ? this.characters.get(b.owner_team) : undefined
      if (ownerView?.rig?.armR && b.owner_team) {
        this.heldBy.set(b.ball_id, b.owner_team) // positioned per frame in update()
        this.tintBall(view, b)
        return
      }
      // Capsule fallback: carried at the character's right side (right = aim rotated
      // 90° clockwise, matching 02's team-relative right) so the body doesn't hide it.
      const owner = characters.find((c) => c.team === b.owner_team)
      const pos = owner?.pos ?? b.pos
      const aim = owner?.aim ?? { x: 0, z: 0 }
      const right = { x: aim.z, z: -aim.x }
      view.entity.setPosition(
        toScene(
          pos.x + right.x * HELD_BALL_SIDE + aim.x * HELD_BALL_FORWARD,
          pos.z + right.z * HELD_BALL_SIDE + aim.z * HELD_BALL_FORWARD,
          HELD_BALL_HEIGHT,
        ),
      )
    } else {
      const y = b.mode === 'flying' ? FLYING_BALL_HEIGHT : BALL_RADIUS
      const pos = toScene(b.pos.x, b.pos.z, y)
      view.entity.setPosition(pos)
      if (b.mode === 'flying') view.flight = { from: pos, vel: toScene(b.velocity.x, b.velocity.z), at: now }
    }

    this.tintBall(view, b)
  }

  /** Glow in the owning/shooting team's colour so possession reads at a glance. */
  private tintBall(view: BallView, b: Ball): void {
    const team = b.mode === 'held' ? b.owner_team : b.mode === 'flying' ? b.shooter_team : null
    const tint = team ? `t${team}` : ''
    if (tint !== view.tint) {
      view.material.emissive = team ? TEAM_COLORS[team] : new pc.Color(0, 0, 0)
      view.material.update()
      view.tint = tint
    }
  }
}
