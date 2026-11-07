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
import { toScene } from './coords'
import type { Ball, Character, State, Team } from './state'

function material(diffuse: pc.Color, emissive = new pc.Color(0, 0, 0)): pc.StandardMaterial {
  const m = new pc.StandardMaterial()
  m.diffuse = diffuse
  m.emissive = emissive
  m.update()
  return m
}

interface CharacterView {
  root: pc.Entity
  aimPivot: pc.Entity
}

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

  return { root, aimPivot }
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
  private readonly characterRoot = new pc.Entity('Characters')
  private readonly ballRoot = new pc.Entity('Balls')

  constructor(parent: pc.Entity) {
    parent.addChild(this.characterRoot)
    parent.addChild(this.ballRoot)
  }

  render(state: State): void {
    for (const c of state.characters) this.renderCharacter(c)
    for (const b of state.balls) this.renderBall(b, state.characters)
  }

  private renderCharacter(c: Character): void {
    let view = this.characters.get(c.team)
    if (!view) {
      view = createCharacter(c.team)
      this.characters.set(c.team, view)
      this.characterRoot.addChild(view.root)
    }
    view.root.setPosition(toScene(c.pos.x, c.pos.z))
    view.aimPivot.lookAt(toScene(c.pos.x + c.aim.x, c.pos.z + c.aim.z))
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
      // Carried at the character's right side (right = aim rotated 90° clockwise,
      // matching 02's team-relative right) so the body doesn't hide it.
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

    // Glow in the owning/shooting team's colour so possession reads at a glance.
    const team = b.mode === 'held' ? b.owner_team : b.mode === 'flying' ? b.shooter_team : null
    const tint = team ? `t${team}` : ''
    if (tint !== view.tint) {
      view.material.emissive = team ? TEAM_COLORS[team] : new pc.Color(0, 0, 0)
      view.material.update()
      view.tint = tint
    }
  }
}
