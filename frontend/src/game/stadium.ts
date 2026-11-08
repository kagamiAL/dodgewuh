import * as pc from 'playcanvas'
import { COURT_HALF_DEPTH, COURT_HALF_WIDTH, TEAM_COLORS } from './constants'
import { toScene } from './coords'
import { loadCrowdModel, type CrowdModel, type CrowdPart } from './crowdModel'
import { buildCardCrowd, crowdCardMaterial, type CardFan } from './crowdCards'
import { createWoodTexture, woodMaterial } from './woodFloor'

// Cosmetic stadium around the court: apron, ad boards, stepped bleachers full of
// low-poly fans, and floodlight towers. Purely decoration; nothing here reads game
// state. Fans are merged into a few vertex-coloured meshes (one draw call per
// section) and seeded, so every screen shows the same crowd. Box fans draw at once
// and are swapped for the crowd model (crowdguy.glb) when it loads: 3D models in the front
// rows, flat cards further back (far cheaper, and hard to tell apart at that distance).
// Both are animated in the vertex shader (jumps, arm pumps), two draw calls per section.

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
/** crowdguy.glb units -> metres: body radius 0.62 -> ~0.2 m, filling one seat. */
const FAN_SCALE = 0.33
const FAN_SCALE_JITTER = 0.08
const FAN_YAW_JITTER = 0.3 // radians, either way
const ARM_PUMPER_CHANCE = 0.35 // seated fans who pump their arms when excited
/** Rows from the front drawn as 3D models; every row behind them is flat cards. */
const MODEL_ROWS = 2

/** How each fan's arms move: blend weight between the idle and cheer poses over time. */
const enum ArmStyle { Seated = 0, Pumps = 1, Up = 2 }

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
  /** World direction from the stand toward the court. */
  inward: { x: number; z: number }
}

function standFrames(): StandFrame[] {
  const sideLen = 2 * BOARD_Z
  const endLen = 2 * BOARD_X
  return [
    { length: sideLen, alongZ: true, inward: { x: -1, z: 0 }, place: (a, b) => ({ x: STAND_X + b, z: a - sideLen / 2 }) },
    { length: sideLen, alongZ: true, inward: { x: 1, z: 0 }, place: (a, b) => ({ x: -(STAND_X + b), z: sideLen / 2 - a }) },
    { length: endLen, alongZ: false, inward: { x: 0, z: -1 }, place: (a, b) => ({ x: endLen / 2 - a, z: STAND_Z + b }) },
    { length: endLen, alongZ: false, inward: { x: 0, z: 1 }, place: (a, b) => ({ x: a - endLen / 2, z: -(STAND_Z + b) }) },
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

/** One seated fan, in scene space; the same record drives the box and model crowds. */
interface Fan {
  /** 0 = front row. */
  row: number
  pos: pc.Vec3
  /** Rotation about scene +Y that turns the model's front (+Z) toward the court. */
  yaw: number
  scale: number
  cheer: boolean
  shirt: RGB
  /** Animation: start phase (rad), tempo multiplier, energy 0..1 (how often and high they jump). */
  phase: number
  tempo: number
  energy: number
  arms: ArmStyle
}

// Per-fan animation, evaluated per vertex. Every fan is baked in the idle pose with a
// per-vertex offset to the cheer pose (the two meshes share topology), so arms blend
// between down and up. Excitement swells and fades on two slow, incommensurate waves
// per fan, so jumps come in irregular bursts rather than a uniform bounce.
const CROWD_VS = `
attribute vec4 crowd_cheer;  // xyz: cheer pose minus idle pose (scene metres)
attribute vec4 crowd_params; // x: phase, y: tempo, z: energy, w: arm style
uniform float crowd_time;

vec3 crowdOffset(vec3 p) {
  float phase = crowd_params.x;
  float tempo = crowd_params.y;
  float energy = crowd_params.z;
  float t = crowd_time * tempo + phase;
  float swell = 0.5 + 0.3 * sin(crowd_time * 0.37 + phase * 1.7) + 0.2 * sin(crowd_time * 0.11 + phase * 2.9);
  float excited = smoothstep(0.75 - 0.45 * energy, 0.95 - 0.35 * energy, swell);
  float jump = abs(sin(t * 4.2)) * excited * (0.12 + 0.22 * energy);
  float arms;
  if (crowd_params.w > 1.5) arms = 0.75 + 0.25 * sin(t * 3.1);                         // arms up, waving
  else if (crowd_params.w > 0.5) arms = excited * (0.5 + 0.5 * sin(t * 6.0));          // pumping
  else arms = smoothstep(0.85, 1.0, swell) * (0.7 + 0.3 * sin(t * 2.0));               // up at big moments
  return crowd_cheer.xyz * arms + vec3(0.0, jump, 0.0);
}
`


/** Bakes every fan in a section into one vertex-coloured, shader-animated mesh. */
function buildModelCrowd(device: pc.GraphicsDevice, model: CrowdModel, fans: Fan[]): pc.Mesh {
  const positions: number[] = []
  const normals: number[] = []
  const colors: number[] = []
  const cheerDelta: number[] = []
  const params: number[] = []
  const indices: number[] = []
  for (const fan of fans) {
    const cos = Math.cos(fan.yaw), sin = Math.sin(fan.yaw)
    const arms = fan.cheer ? ArmStyle.Up : fan.arms
    model.idle.forEach((part, k) => {
      const cheer: CrowdPart | undefined = model.cheer[k]
      const posed = cheer && cheer.positions.length === part.positions.length ? cheer.positions : part.positions
      const [r, g, b] = part.material === 'CG_Body' ? fan.shirt : model.colors[part.material] ?? [1, 1, 1]
      const base = positions.length / 3
      for (let i = 0; i < part.positions.length; i += 3) {
        const x = part.positions[i] * fan.scale, y = part.positions[i + 1] * fan.scale, z = part.positions[i + 2] * fan.scale
        positions.push(fan.pos.x + cos * x + sin * z, fan.pos.y + y, fan.pos.z - sin * x + cos * z)
        const dx = (posed[i] - part.positions[i]) * fan.scale
        const dy = (posed[i + 1] - part.positions[i + 1]) * fan.scale
        const dz = (posed[i + 2] - part.positions[i + 2]) * fan.scale
        cheerDelta.push(cos * dx + sin * dz, dy, -sin * dx + cos * dz, 0)
        const nx = part.normals[i], ny = part.normals[i + 1], nz = part.normals[i + 2]
        normals.push(cos * nx + sin * nz, ny, -sin * nx + cos * nz)
        colors.push(r, g, b, 1)
        params.push(fan.phase, fan.tempo, fan.energy, arms)
      }
      for (const index of part.indices) indices.push(base + index)
    })
  }
  const mesh = new pc.Mesh(device)
  mesh.setPositions(positions)
  mesh.setNormals(normals)
  mesh.setColors(colors)
  mesh.setVertexStream(pc.SEMANTIC_ATTR8, cheerDelta, 4)
  mesh.setVertexStream(pc.SEMANTIC_ATTR9, params, 4)
  mesh.setIndices(indices)
  mesh.update()
  // Leave room for jumps and raised arms so sections aren't culled mid-air.
  const { center, halfExtents: h } = mesh.aabb
  mesh.aabb = new pc.BoundingBox(center.clone(), new pc.Vec3(h.x + 0.3, h.y + 0.6, h.z + 0.3))
  return mesh
}

/** Adds the CROWD_VS animation to a crowd material; `crowd_time` drives it. */
function animateCrowd(m: pc.StandardMaterial, device: pc.GraphicsDevice): pc.StandardMaterial {
  m.setAttribute('crowd_cheer', pc.SEMANTIC_ATTR8)
  m.setAttribute('crowd_params', pc.SEMANTIC_ATTR9)
  const core = pc.ShaderChunks.get(device, pc.SHADERLANGUAGE_GLSL).get('transformCoreVS') ?? ''
  const anchor = 'vec3 localPos = vertexPosition;'
  if (core.includes(anchor)) {
    m.getShaderChunks(pc.SHADERLANGUAGE_GLSL).set(
      'transformCoreVS',
      CROWD_VS + core.replace(anchor, 'vec3 localPos = vertexPosition + crowdOffset(vertexPosition);'),
    )
  } else {
    console.warn('[game] transformCoreVS changed; crowd animation disabled')
  }
  m.setParameter('crowd_time', 0)
  m.update()
  return m
}

function toCardFan(fan: Fan): CardFan {
  return {
    pos: fan.pos,
    yaw: fan.yaw,
    size: fan.scale / FAN_SCALE,
    shirt: fan.shirt,
    params: [fan.phase, fan.tempo, fan.energy, fan.cheer ? ArmStyle.Up : fan.arms],
  }
}

interface Stands {
  root: pc.Entity
  /** Crowd sections in wave order, each with the fans it draws. */
  sections: { entity: pc.Entity; fans: Fan[] }[]
}

function buildStands(device: pc.GraphicsDevice): Stands {
  const root = new pc.Entity('Stands')
  const sections: Stands['sections'] = []
  const rand = seeded(CROWD_SEED)
  const pick = <T,>(list: T[]): T => list[Math.floor(rand() * list.length)]
  const concrete = vertexColorMaterial()
  const crowdMaterial = vertexColorMaterial()

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

    // Model front (+Z) rotated by yaw is (sin, 0, cos) in scene space; aim it at the court.
    const inward = toScene(f.inward.x, f.inward.z)
    const faceCourt = Math.atan2(inward.x, inward.z)

    // Fans, split into sections along the stand so they can bob out of phase.
    const sectionLen = f.length / SECTIONS_PER_STAND
    for (let s = 0; s < SECTIONS_PER_STAND; s++) {
      const crowd = new BoxBuilder()
      const fans: Fan[] = []
      for (let row = 0; row < ROWS; row++) {
        const seatY = (row + 1) * ROW_RISE
        const back = (row + 0.55) * ROW_DEPTH
        for (let a = s * sectionLen + SEAT_SPACING / 2; a < (s + 1) * sectionLen; a += SEAT_SPACING) {
          if (rand() < EMPTY_SEAT_CHANCE) continue
          const along = a + (rand() - 0.5) * 0.1
          const cheer = rand() < STANDING_CHANCE
          const shirt = pick(SHIRTS)
          const energy = rand()
          const arms = rand() < ARM_PUMPER_CHANCE ? ArmStyle.Pumps : ArmStyle.Seated
          const p = f.place(along, back)
          fans.push({
            row,
            pos: toScene(p.x, p.z, seatY),
            yaw: faceCourt + (rand() * 2 - 1) * FAN_YAW_JITTER,
            scale: FAN_SCALE * (1 + (rand() * 2 - 1) * FAN_SCALE_JITTER),
            cheer,
            shirt,
            phase: rand() * Math.PI * 2,
            tempo: 0.8 + rand() * 0.5,
            energy,
            arms,
          })

          // Box stand-in until the model loads (or if it never does).
          const bodyH = cheer ? 0.8 : 0.5 + rand() * 0.08
          const bodyW = 0.38 + rand() * 0.08
          addStandBox(crowd, f, along, back, seatY, bodyW, bodyH, 0.28, shirt)
          addStandBox(crowd, f, along, back, seatY + bodyH, 0.22, 0.24, 0.22, shirt)
          if (cheer) {
            addStandBox(crowd, f, along - bodyW / 2 - 0.04, back, seatY + bodyH - 0.1, 0.08, 0.45, 0.08, shirt)
            addStandBox(crowd, f, along + bodyW / 2 + 0.04, back, seatY + bodyH - 0.1, 0.08, 0.45, 0.08, shirt)
          }
        }
      }
      const entity = crowd.build(device, crowdMaterial, `Crowd${standIndex}_${s}`)
      sections.push({ entity, fans })
      root.addChild(entity)
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
  /** Stops a pending crowd-model swap; call before the app is destroyed. */
  destroy(): void
}

export function createStadium(app: pc.Application): Stadium {
  const device = app.graphicsDevice
  const root = new pc.Entity('Stadium')
  root.addChild(buildApron(device))
  root.addChild(buildBoards(device))
  root.addChild(buildFloodlights())
  const stands = buildStands(device)
  root.addChild(stands.root)

  // Swap each section's boxes for the baked, animated crowd model once it arrives.
  let destroyed = false
  let crowdMaterials: pc.StandardMaterial[] = []
  void loadCrowdModel().then((model) => {
    if (!model || destroyed) return
    const modelMat = animateCrowd(vertexColorMaterial(), device)
    const cardMat = animateCrowd(crowdCardMaterial(device), device)
    for (const { entity, fans } of stands.sections) {
      if (!entity.render) continue
      const near = fans.filter((fan) => fan.row < MODEL_ROWS)
      const cards = buildCardCrowd(device, fans.filter((fan) => fan.row >= MODEL_ROWS).map(toCardFan))
      const instances = [new pc.MeshInstance(buildModelCrowd(device, model, near), modelMat)]
      if (cards) instances.push(new pc.MeshInstance(cards, cardMat))
      // The setter destroys the box mesh instances it replaces.
      entity.render.meshInstances = instances
    }
    crowdMaterials = [modelMat, cardMat]
  })

  // A slow wave travels around the stadium; each section hops a few centimetres.
  let t = 0
  return {
    root,
    update(dt) {
      t += dt
      for (const m of crowdMaterials) m.setParameter('crowd_time', t)
      stands.sections.forEach(({ entity }, i) => {
        const hop = Math.max(0, Math.sin(t * 1.6 - i * 0.55))
        entity.setLocalPosition(0, hop * hop * 0.12, 0)
      })
    },
    destroy() {
      destroyed = true
    },
  }
}
