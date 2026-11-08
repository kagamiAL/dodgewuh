import * as pc from 'playcanvas'
import { TEAM_COLORS } from './constants'
import type { Team } from './state'

// First-person view model: RedGuy's right hand gripping the dodgeball, built by
// assets/character/fphand_build.py. FPHand_Root sits at the ball centre and the camera
// looks down -Z at it, so as a camera child it needs no rotation. Cosmetic only.

export const FP_HAND_URL = `${import.meta.env.BASE_URL}models/fphand.glb`
/** RedGuy model units -> metres (3.55 units = 1.8 m); the ball comes out at BALL_RADIUS. */
const FP_HAND_SCALE = 0.507
/**
 * The modelled ball looks small next to the cartoon hand, so the ball (and its seam) are
 * scaled up about the ball centre (the root's origin). Visual only; the file is unchanged.
 */
const FP_BALL_SCALE = 1.2
const BALL_NODES = ['FP_Ball', 'FP_BallSeam']
/** The hand/arm material; recoloured per team like the character body. */
const SKIN_MATERIAL = 'RG_Red'

/** Loads the hand model once. Resolves null on failure so callers keep the plain held ball. */
export function loadFirstPersonHand(app: pc.Application): Promise<pc.Asset | null> {
  return new Promise((resolve) => {
    app.assets.loadFromUrl(FP_HAND_URL, 'container', (err, asset) => {
      if (err || !asset) {
        console.warn('[game] first-person hand failed to load; using the plain held ball', err)
        resolve(null)
      } else {
        resolve(asset)
      }
    })
  })
}

export interface FirstPersonHand {
  entity: pc.Entity
  /** Tint the hand and arm to the viewer's team colour. */
  setTeam(team: Team): void
  /** Show or hide the modelled ball (hidden during the follow-through after a throw). */
  setBallVisible(visible: boolean): void
}

export function instantiateFirstPersonHand(asset: pc.Asset): FirstPersonHand {
  const container = asset.resource as pc.ContainerResource
  const entity = container.instantiateRenderEntity()
  entity.setLocalScale(FP_HAND_SCALE, FP_HAND_SCALE, FP_HAND_SCALE)
  for (const name of BALL_NODES) {
    const node = entity.findByName(name)
    node?.setLocalScale(FP_BALL_SCALE, FP_BALL_SCALE, FP_BALL_SCALE)
  }

  // One cloned skin material shared by the palm, fingers, thumb and arm.
  let skin: pc.StandardMaterial | null = null
  for (const rc of entity.findComponents('render') as pc.RenderComponent[]) {
    for (const mi of rc.meshInstances) {
      if (mi.material?.name !== SKIN_MATERIAL) continue
      skin ??= mi.material.clone() as pc.StandardMaterial
      mi.material = skin
    }
  }

  const ballNodes = BALL_NODES.map((name) => entity.findByName(name)).filter((n): n is pc.GraphNode => !!n)
  let current: Team | null = null
  let ballVisible = true
  return {
    entity,
    setBallVisible(visible) {
      if (visible === ballVisible) return
      ballVisible = visible
      for (const node of ballNodes) if (node instanceof pc.Entity) node.enabled = visible
    },
    setTeam(team) {
      if (!skin || team === current) return
      current = team
      skin.diffuse = TEAM_COLORS[team].clone()
      skin.diffuseMap = null
      skin.update()
    },
  }
}
