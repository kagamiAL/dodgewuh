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
}

// Snapshot-derived velocity is dropped if positions jump this far (reset/teleport)
// or no snapshot arrives for this long (stale stream).
const TELEPORT_M = 1.5
const VELOCITY_STALE_MS = 250

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
    holding: false, heldBallId: null, epoch: -1,
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
}

function createBall(id: string): BallView {
  const m = material(BALL_COLOR)
  const entity = new pc.Entity(`Ball_${id}`)
  entity.addComponent('render', { type: 'sphere', material: m })
  entity.setLocalScale(BALL_RADIUS * 2, BALL_RADIUS * 2, BALL_RADIUS * 2)
  return { entity, material: m, tint: '' }
}

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
    for (const b of state.balls) this.renderBall(b, state.characters)
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
  }

  private renderCharacter(c: Character, state: State, now: number): void {
    let view = this.characters.get(c.team)
    if (!view) {
      view = createCharacter(c.team)
      this.characters.set(c.team, view)
      this.characterRoot.addChild(view.root)
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
    } else {
      view.velX = 0
      view.velZ = 0
    }
    view.lastPos = pos.clone()
    view.lastSnapshotMs = now
    view.epoch = epoch
  }

  private renderBall(b: Ball, characters: Character[]): void {
    let view = this.balls.get(b.ball_id)
    if (!view) {
      view = createBall(b.ball_id)
      this.balls.set(b.ball_id, view)
      this.ballRoot.addChild(view.entity)
    }

    view.entity.enabled = b.mode !== 'respawning'

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
      view.entity.setPosition(toScene(b.pos.x, b.pos.z, y))
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
