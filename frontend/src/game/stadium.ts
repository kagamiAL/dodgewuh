import * as pc from 'playcanvas'
import { COURT_HALF_DEPTH, COURT_HALF_WIDTH, TEAM_COLORS } from './constants'
import { toScene } from './coords'
import { createWoodTexture, woodMaterial } from './woodFloor'

// Cosmetic stadium around the court: apron, ad boards, stepped bleachers full of
// low-poly fans, and floodlight towers. Purely decoration; nothing here reads game
// state. Fans are merged into a few vertex-coloured meshes (one draw call per
// section) and seeded, so every screen shows the same crowd.

const RUNOFF = 2.5 // court line -> ad boards
const BOARD_HEIGHT = 1
const BOARD_THICKNESS = 0.2
const STAND_GAP = 1 // ad boards -> first row
const ROWS = 8
const ROW_DEPTH = 0.85
const ROW_RISE = 0.45
const SEAT_SPACING = 0.65
const EMPTY_SEAT_CHANCE = 0.15
const STANDING_CHANCE = 0.12
const SECTIONS_PER_STAND = 4
const CROWD_SEED = 20261107

const BOARD_X = COURT_HALF_WIDTH + RUNOFF
const BOARD_Z = COURT_HALF_DEPTH + RUNOFF
const STAND_X = BOARD_X + STAND_GAP
const STAND_Z = BOARD_Z + STAND_GAP
const STAND_DEPTH = ROWS * ROW_DEPTH

/** Small deterministic PRNG (mulberry32) so the crowd is identical on every screen. */
function seeded(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

type RGB = [number, number, number]

const hex = (c: pc.Color): RGB => [c.r, c.g, c.b]
const SHIRTS: RGB[] = [
  hex(TEAM_COLORS[1]), hex(TEAM_COLORS[1]), hex(TEAM_COLORS[2]), hex(TEAM_COLORS[2]),
  [0.9, 0.9, 0.9], [0.15, 0.15, 0.17], [0.85, 0.2, 0.2], [0.2, 0.65, 0.3],
  [0.95, 0.85, 0.2], [0.55, 0.3, 0.7], [0.45, 0.45, 0.5],
]
const SKIN: RGB[] = [
  [0.96, 0.8, 0.69], [0.87, 0.67, 0.53], [0.72, 0.52, 0.38], [0.55, 0.37, 0.25], [0.36, 0.24, 0.16],
]

/** Accumulates axis-aligned boxes (world metres, y up) into one vertex-coloured mesh. */
class BoxBuilder {
  private readonly positions: number[] = []
  private readonly normals: number[] = []
  private readonly colors: number[] = []
  private readonly indices: number[] = []

  /** Box centred at world (x, z) with its base at y; bottom face omitted (never seen). */
  add(x: number, y: number, z: number, sx: number, sy: number, sz: number, color: RGB): void {
    const c = toScene(x, z, y + sy / 2)
    const hx = sx / 2, hy = sy / 2, hz = sz / 2
    // [normal, four corners counter-clockwise seen from outside]
    const faces: [number[], number[][]][] = [
      [[0, 1, 0], [[-hx, hy, -hz], [-hx, hy, hz], [hx, hy, hz], [hx, hy, -hz]]],
      [[1, 0, 0], [[hx, -hy, -hz], [hx, hy, -hz], [hx, hy, hz], [hx, -hy, hz]]],
      [[-1, 0, 0], [[-hx, -hy, hz], [-hx, hy, hz], [-hx, hy, -hz], [-hx, -hy, -hz]]],
      [[0, 0, 1], [[hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz], [-hx, -hy, hz]]],
      [[0, 0, -1], [[-hx, -hy, -hz], [-hx, hy, -hz], [hx, hy, -hz], [hx, -hy, -hz]]],
    ]
    for (const [n, corners] of faces) {
      const base = this.positions.length / 3
      for (const [px, py, pz] of corners) {
        this.positions.push(c.x + px, c.y + py, c.z + pz)
        this.normals.push(n[0], n[1], n[2])
        this.colors.push(color[0], color[1], color[2], 1)
      }
      this.indices.push(base, base + 1, base + 2, base, base + 2, base + 3)
    }
  }

  build(device: pc.GraphicsDevice, material: pc.Material, name: string): pc.Entity {
    const mesh = new pc.Mesh(device)
    mesh.setPositions(this.positions)
    mesh.setNormals(this.normals)
    mesh.setColors(this.colors)
    mesh.setIndices(this.indices)
    mesh.update()
    const entity = new pc.Entity(name)
    entity.addComponent('render', { meshInstances: [new pc.MeshInstance(mesh, material)] })
    return entity
  }
}

function vertexColorMaterial(emissive = false): pc.StandardMaterial {
  const m = new pc.StandardMaterial()
  m.diffuseVertexColor = true
  if (emissive) {
    m.emissive = new pc.Color(1, 1, 1) // tint multiplies the vertex colour
    m.emissiveVertexColor = true
    m.emissiveIntensity = 0.35
  }
  m.update()
  return m
}

function solidMaterial(color: pc.Color, emissive?: pc.Color): pc.StandardMaterial {
  const m = new pc.StandardMaterial()
  m.diffuse = color
  if (emissive) m.emissive = emissive
  m.update()
  return m
}

/**
 * One stand: rows run along `length` and step back and up away from the court.
 * `place(along, back)` maps stand-local coordinates (metres along the stand, metres
 * back from its front edge) to world (x, z) plus box footprint axes.
 */
interface StandFrame {
  length: number
  place(along: number, back: number): { x: number; z: number }
  /** True when the stand runs along world z (side stands), so box sizes swap axes. */
  alongZ: boolean
}

function standFrames(): StandFrame[] {
  const sideLen = 2 * BOARD_Z
  const endLen = 2 * BOARD_X
  return [
    { length: sideLen, alongZ: true, place: (a, b) => ({ x: STAND_X + b, z: a - sideLen / 2 }) },
    { length: sideLen, alongZ: true, place: (a, b) => ({ x: -(STAND_X + b), z: sideLen / 2 - a }) },
    { length: endLen, alongZ: false, place: (a, b) => ({ x: endLen / 2 - a, z: STAND_Z + b }) },
    { length: endLen, alongZ: false, place: (a, b) => ({ x: a - endLen / 2, z: -(STAND_Z + b) }) },
  ]
}

/** Box with `along`/`back` footprint expressed in world axes for this stand. */
function addStandBox(
  out: BoxBuilder, f: StandFrame, along: number, back: number, y: number,
  sAlong: number, sy: number, sBack: number, color: RGB,
): void {
  const p = f.place(along, back)
  if (f.alongZ) out.add(p.x, y, p.z, sBack, sy, sAlong, color)
  else out.add(p.x, y, p.z, sAlong, sy, sBack, color)
}

function buildStands(device: pc.GraphicsDevice): { root: pc.Entity; sections: pc.Entity[] } {
  const root = new pc.Entity('Stands')
  const sections: pc.Entity[] = []
  const rand = seeded(CROWD_SEED)
  const pick = <T,>(list: T[]): T => list[Math.floor(rand() * list.length)]
  const concrete = vertexColorMaterial()
  const crowdMat = vertexColorMaterial()

  const frames = standFrames()
  frames.forEach((f, standIndex) => {
    // Stepped concrete: each row is a solid block up to its seat height.
    const steps = new BoxBuilder()
    for (let row = 0; row < ROWS; row++) {
      const shade = 0.42 + (row % 2) * 0.05
      addStandBox(steps, f, f.length / 2, (row + 0.5) * ROW_DEPTH, 0, f.length, (row + 1) * ROW_RISE, ROW_DEPTH, [shade, shade, shade + 0.02])
    }
    // Back wall above the top row.
    addStandBox(steps, f, f.length / 2, STAND_DEPTH + 0.15, 0, f.length, ROWS * ROW_RISE + 1.2, 0.3, [0.25, 0.26, 0.3])
    root.addChild(steps.build(device, concrete, `Steps${standIndex}`))

    // Fans, split into sections along the stand so they can bob out of phase.
    const sectionLen = f.length / SECTIONS_PER_STAND
    for (let s = 0; s < SECTIONS_PER_STAND; s++) {
      const crowd = new BoxBuilder()
      for (let row = 0; row < ROWS; row++) {
        const seatY = (row + 1) * ROW_RISE
        const back = (row + 0.55) * ROW_DEPTH
        for (let a = s * sectionLen + SEAT_SPACING / 2; a < (s + 1) * sectionLen; a += SEAT_SPACING) {
          if (rand() < EMPTY_SEAT_CHANCE) continue
          const along = a + (rand() - 0.5) * 0.1
          const standing = rand() < STANDING_CHANCE
          const bodyH = standing ? 0.8 : 0.5 + rand() * 0.08
          const bodyW = 0.38 + rand() * 0.08
          addStandBox(crowd, f, along, back, seatY, bodyW, bodyH, 0.28, pick(SHIRTS))
          addStandBox(crowd, f, along, back, seatY + bodyH, 0.22, 0.24, 0.22, pick(SKIN))
          if (standing && rand() < 0.6) {
            // Arms up, cheering.
            addStandBox(crowd, f, along - bodyW / 2 - 0.04, back, seatY + bodyH - 0.1, 0.08, 0.45, 0.08, pick(SKIN))
            addStandBox(crowd, f, along + bodyW / 2 + 0.04, back, seatY + bodyH - 0.1, 0.08, 0.45, 0.08, pick(SKIN))
          }
        }
      }
      const section = crowd.build(device, crowdMat, `Crowd${standIndex}_${s}`)
      sections.push(section)
      root.addChild(section)
    }
  })
  return { root, sections }
}

/** Ring of glowing ad boards just outside the run-off, alternating team colours. */
function buildBoards(device: pc.GraphicsDevice): pc.Entity {
  const boards = new BoxBuilder()
  const palette: RGB[] = [hex(TEAM_COLORS[1]), [0.9, 0.9, 0.9], hex(TEAM_COLORS[2]), [0.95, 0.85, 0.2]]
  const panel = 3
  let i = 0
  const run = (fromX: number, fromZ: number, toX: number, toZ: number) => {
    const len = Math.hypot(toX - fromX, toZ - fromZ)
    const n = Math.max(1, Math.round(len / panel))
    for (let k = 0; k < n; k++) {
      const t = (k + 0.5) / n
      const x = fromX + (toX - fromX) * t
      const z = fromZ + (toZ - fromZ) * t
      const alongX = Math.abs(toX - fromX) > Math.abs(toZ - fromZ)
      const w = len / n - 0.05
      if (alongX) boards.add(x, 0, z, w, BOARD_HEIGHT, BOARD_THICKNESS, palette[i++ % palette.length])
      else boards.add(x, 0, z, BOARD_THICKNESS, BOARD_HEIGHT, w, palette[i++ % palette.length])
    }
  }
  run(-BOARD_X, -BOARD_Z, BOARD_X, -BOARD_Z)
  run(BOARD_X, -BOARD_Z, BOARD_X, BOARD_Z)
  run(BOARD_X, BOARD_Z, -BOARD_X, BOARD_Z)
  run(-BOARD_X, BOARD_Z, -BOARD_X, -BOARD_Z)
  return boards.build(device, vertexColorMaterial(true), 'AdBoards')
}

/** Darker-stained wood border around the court, out to the stands. */
function buildApron(device: pc.GraphicsDevice): pc.Entity {
  const w = 2 * (STAND_X + STAND_DEPTH)
  const d = 2 * (STAND_Z + STAND_DEPTH)
  const e = new pc.Entity('Apron')
  const material = woodMaterial(createWoodTexture(device), new pc.Color(0.62, 0.48, 0.34), w, d)
  e.addComponent('render', { type: 'plane', material })
  e.setPosition(toScene(0, 0, -0.01))
  e.setLocalScale(w, 1, d)
  return e
}

/** Floodlight towers in the four corners, light panels turned toward the court. */
function buildFloodlights(): pc.Entity {
  const root = new pc.Entity('Floodlights')
  const poleMat = solidMaterial(new pc.Color(0.3, 0.31, 0.34))
  const lampMat = solidMaterial(new pc.Color(1, 1, 0.95), new pc.Color(1, 0.98, 0.9))
  const height = 16
  for (const sx of [-1, 1]) {
    for (const sz of [-1, 1]) {
      const x = sx * (STAND_X + STAND_DEPTH + 1)
      const z = sz * (STAND_Z + STAND_DEPTH + 1)
      const pole = new pc.Entity('Pole')
      pole.addComponent('render', { type: 'box', material: poleMat })
      pole.setPosition(toScene(x, z, height / 2))
      pole.setLocalScale(0.5, height, 0.5)
      root.addChild(pole)

      const lamp = new pc.Entity('Lamp')
      lamp.addComponent('render', { type: 'box', material: lampMat })
      lamp.setPosition(toScene(x, z, height + 0.8))
      lamp.lookAt(toScene(0, 0))
      lamp.setLocalScale(3.2, 1.8, 0.3)
      root.addChild(lamp)
    }
  }
  return root
}

export interface Stadium {
  root: pc.Entity
  /** Per-frame crowd animation (cosmetic). */
  update(dt: number): void
}

export function createStadium(app: pc.Application): Stadium {
  const device = app.graphicsDevice
  const root = new pc.Entity('Stadium')
  root.addChild(buildApron(device))
  root.addChild(buildBoards(device))
  root.addChild(buildFloodlights())
  const { root: stands, sections } = buildStands(device)
  root.addChild(stands)

  // A slow wave travels around the stadium; each section hops a few centimetres.
  let t = 0
  return {
    root,
    update(dt) {
      t += dt
      sections.forEach((section, i) => {
        const hop = Math.max(0, Math.sin(t * 1.6 - i * 0.55))
        section.setLocalPosition(0, hop * hop * 0.12, 0)
      })
    },
  }
}
