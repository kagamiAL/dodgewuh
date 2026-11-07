import * as pc from 'playcanvas'
import {
  COURT_HALF_DEPTH,
  COURT_HALF_WIDTH,
  LINE_WIDTH,
  NO_THROW_HALF_DEPTH,
  TEAM_COLORS,
} from './constants'
import { toScene } from './coords'
import { createWoodTexture, woodMaterial } from './woodFloor'

function solidMaterial(color: pc.Color): pc.StandardMaterial {
  const m = new pc.StandardMaterial()
  m.diffuse = color
  m.update()
  return m
}

function translucentMaterial(color: pc.Color, opacity: number): pc.StandardMaterial {
  const m = new pc.StandardMaterial()
  m.diffuse = color
  m.emissive = color
  m.opacity = opacity
  m.blendType = pc.BLEND_NORMAL
  m.depthWrite = false
  m.update()
  return m
}

/** Flat rectangle on the floor covering world x∈[x0,x1], z∈[z0,z1], raised by `lift` to avoid z-fighting. */
function floorRect(
  name: string,
  material: pc.Material,
  x0: number,
  x1: number,
  z0: number,
  z1: number,
  lift: number,
): pc.Entity {
  const e = new pc.Entity(name)
  e.addComponent('render', { type: 'plane', material })
  e.setPosition(toScene((x0 + x1) / 2, (z0 + z1) / 2, lift))
  e.setLocalScale(x1 - x0, 1, z1 - z0)
  return e
}

/**
 * Static court geometry derived from 02: team halves (Team 1 negative z), boundary
 * lines, centre line and the no-throw strip |z| ≤ 2. Never changes after creation.
 */
export function createCourt(device: pc.GraphicsDevice): pc.Entity {
  const court = new pc.Entity('Arena')
  const W = COURT_HALF_WIDTH
  const D = COURT_HALF_DEPTH
  const L = LINE_WIDTH / 2

  // Maple gym floor; a translucent team-colour wash over each half so sides read at a glance
  // (multiplying the colour into the wood turns blue muddy). Blue needs more to show on maple.
  const maple = woodMaterial(createWoodTexture(device), pc.Color.WHITE, 2 * W, D)
  court.addChild(floorRect('Team1Half', maple, -W, W, -D, 0, 0))
  court.addChild(floorRect('Team2Half', maple, -W, W, 0, D, 0))
  court.addChild(floorRect('Team1Wash', translucentMaterial(TEAM_COLORS[1], 0.34), -W, W, -D, 0, 0.002))
  court.addChild(floorRect('Team2Wash', translucentMaterial(TEAM_COLORS[2], 0.2), -W, W, 0, D, 0.002))

  // No-throw strip: you can stand, pick up and be hit here, but not throw.
  const noThrow = translucentMaterial(new pc.Color(0.95, 0.2, 0.25), 0.28)
  court.addChild(floorRect('NoThrowZone', noThrow, -W, W, -NO_THROW_HALF_DEPTH, NO_THROW_HALF_DEPTH, 0.005))

  const white = solidMaterial(new pc.Color(0.92, 0.92, 0.92))
  const lineLift = 0.01
  // Boundary (lines sit inside the court edge so the playable area is unchanged).
  court.addChild(floorRect('LineNear', white, -W, W, -D, -D + LINE_WIDTH, lineLift))
  court.addChild(floorRect('LineFar', white, -W, W, D - LINE_WIDTH, D, lineLift))
  court.addChild(floorRect('LineLeft', white, -W, -W + LINE_WIDTH, -D, D, lineLift))
  court.addChild(floorRect('LineRight', white, W - LINE_WIDTH, W, -D, D, lineLift))
  // Centre line (nobody may cross it).
  court.addChild(floorRect('CentreLine', white, -W, W, -L * 2, L * 2, lineLift))
  // No-throw zone edges.
  const zoneEdge = solidMaterial(new pc.Color(0.95, 0.3, 0.3))
  for (const z of [-NO_THROW_HALF_DEPTH, NO_THROW_HALF_DEPTH]) {
    court.addChild(floorRect(`NoThrowEdge${z}`, zoneEdge, -W, W, z - L, z + L, lineLift))
  }

  return court
}
