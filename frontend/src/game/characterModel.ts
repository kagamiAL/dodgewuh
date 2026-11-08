import * as pc from 'playcanvas'
import { CHARACTER_HEIGHT, TEAM_COLORS } from './constants'
import type { Team } from './state'

// Exported from assets/character/redguy.blend (collection "RedGuy") to glTF binary.
export const MODEL_URL = `${import.meta.env.BASE_URL}models/redguy.glb`
// The red body material in the .blend; recoloured per team so screens match phones.
const BODY_MATERIAL = 'RG_Red'
/** The body glows in its team colour so characters pop against the dark arena (0 = off). */
export const CHARACTER_GLOW = 0.6
/** Eye whites glow a soft, calm green; pupils stay black. */
const EYE_MATERIAL = 'RG_EyeWhite'
const EYE_COLOR = new pc.Color(0.55, 0.9, 0.6)
const EYE_GLOW = 0.8

/** Loads the character model once. Resolves null on failure so callers keep the capsule. */
export function loadCharacterModel(app: pc.Application): Promise<pc.Asset | null> {
  return new Promise((resolve) => {
    app.assets.loadFromUrl(MODEL_URL, 'container', (err, asset) => {
      if (err || !asset) {
        console.warn('[game] character model failed to load; using capsules', err)
        resolve(null)
      } else {
        resolve(asset)
      }
    })
  })
}

function renderComponents(entity: pc.Entity): pc.RenderComponent[] {
  return entity.findComponents('render') as pc.RenderComponent[]
}

/** Rig pieces named by assets/character/export_glb.py; each pivots at its joint. */
export interface CharacterRig {
  torso: pc.Entity | null
  chest: pc.Entity | null
  head: pc.Entity | null
  armL: pc.Entity | null
  armR: pc.Entity | null
  legL: pc.Entity | null
  legR: pc.Entity | null
}

export interface CharacterModel {
  entity: pc.Entity
  rig: CharacterRig
}

/** Palm centre relative to the right shoulder pivot, in model units (redguy_build.py). */
export const RIGHT_HAND_LOCAL = new pc.Vec3(-1.25, -0.42, 0.12)

function find(model: pc.Entity, name: string): pc.Entity | null {
  return (model.findByName(name) as pc.Entity | null) ?? null
}

/**
 * One team's model instance: scaled to CHARACTER_HEIGHT with feet at y=0, body
 * recoloured to the team colour, and turned so it faces the parent's -Z (the
 * direction the facing pivot is pointed at). glTF export puts Blender's front
 * (-Y) on +Z, hence the 180° turn.
 */
export function instantiateCharacterModel(asset: pc.Asset, team: Team): CharacterModel {
  const container = asset.resource as pc.ContainerResource
  const model = container.instantiateRenderEntity()

  const bounds = new pc.BoundingBox()
  let first = true
  for (const rc of renderComponents(model)) {
    for (const mi of rc.meshInstances) {
      if (first) bounds.copy(mi.aabb)
      else bounds.add(mi.aabb)
      first = false

      if (mi.material?.name === BODY_MATERIAL) {
        const m = mi.material.clone() as pc.StandardMaterial
        m.diffuse = TEAM_COLORS[team].clone()
        m.diffuseMap = null
        m.emissive = TEAM_COLORS[team].clone()
        m.emissiveIntensity = CHARACTER_GLOW
        m.update()
        mi.material = m
      } else if (mi.material?.name === EYE_MATERIAL) {
        const m = mi.material.clone() as pc.StandardMaterial
        m.diffuse = EYE_COLOR.clone()
        m.emissive = EYE_COLOR.clone()
        m.emissiveIntensity = EYE_GLOW
        m.update()
        mi.material = m
      }
    }
  }

  const height = bounds.getMax().y - bounds.getMin().y
  const scale = height > 0 ? CHARACTER_HEIGHT / height : 1
  model.setLocalScale(scale, scale, scale)
  model.setLocalPosition(0, -bounds.getMin().y * scale, 0)
  model.setLocalEulerAngles(0, 180, 0)
  return {
    entity: model,
    rig: {
      torso: find(model, 'RG_TorsoRig'),
      chest: find(model, 'RG_ChestRig'),
      head: find(model, 'RG_HeadRig'),
      armL: find(model, 'RG_ArmRig_L'),
      armR: find(model, 'RG_ArmRig_R'),
      legL: find(model, 'RG_LegRig_L'),
      legR: find(model, 'RG_LegRig_R'),
    },
  }
}
