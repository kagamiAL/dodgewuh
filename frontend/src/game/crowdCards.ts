import * as pc from 'playcanvas'

// Flat "card" fans for the back rows: a crowdguy body drawn once on a canvas (white body
// tinted per fan by vertex colour, dark core band, googly eyes) plus two arm quads. About
// 6 triangles a fan instead of ~610. The arm quads carry the same cheer-pose offset stream
// as the 3D model, so the crowd shader animates jumps and arms for both. Cosmetic only.

const ATLAS_W = 128
const ATLAS_H = 128
/** Atlas regions in pixels: [x0, y0, x1, y1]. */
const BODY_PX = [0, 0, 64, 128] as const
const ARM_PX = [64, 0, 96, 128] as const

/** Card size in metres at the crowd's base scale (matches the 3D fan's silhouette). */
const CARD_W = 0.42
const CARD_H = 0.78
const ARM_W = 0.1
const ARM_LEN = 0.34
/** Shoulder height up the card, and how far arms sit in front of the body (no z-fighting). */
const SHOULDER_Y = 0.5
const ARM_LIFT = 0.02
/** Arm angle from straight down: hanging (idle) and raised in a V (cheer). Radians. */
const ARM_IDLE = 0.18
const ARM_CHEER = 2.6

/** One card fan, already resolved to scene space by the stadium. */
export interface CardFan {
  /** Bottom-centre of the card (seat height). */
  pos: pc.Vec3
  /** Rotation about scene +Y; the card faces (sin, 0, cos). */
  yaw: number
  /** Size relative to the base crowd scale (1 = average fan). */
  size: number
  shirt: [number, number, number]
  /** Shader animation params: phase, tempo, energy, arm style (see CROWD_VS). */
  params: [number, number, number, number]
}

function drawAtlas(): { color: HTMLCanvasElement; glow: HTMLCanvasElement } {
  const make = () => {
    const c = document.createElement('canvas')
    c.width = ATLAS_W
    c.height = ATLAS_H
    return c
  }
  const color = make()
  const glow = make()
  const g = color.getContext('2d')
  const e = glow.getContext('2d')
  if (!g || !e) return { color, glow }

  // Body: barrel trunk + dome head, white so the vertex colour tints it to the shirt.
  g.fillStyle = '#fff'
  g.beginPath()
  g.roundRect(5, 44, 54, 84, 14)
  g.fill()
  g.beginPath()
  g.arc(32, 44, 26, Math.PI, 0)
  g.fill()
  // Dark core gaps between body segments.
  g.fillStyle = '#2a2a2a'
  g.fillRect(5, 80, 54, 4)
  g.fillRect(5, 104, 54, 4)
  // Googly eyes: black in colour (so the tint can't reach them), white from the glow map.
  g.fillStyle = '#000'
  e.fillStyle = '#fff'
  for (const x of [22, 42]) {
    g.beginPath()
    g.arc(x, 36, 9, 0, Math.PI * 2)
    g.fill()
    e.beginPath()
    e.arc(x, 36, 9, 0, Math.PI * 2)
    e.fill()
  }
  e.fillStyle = '#000'
  for (const x of [23, 41]) {
    e.beginPath()
    e.arc(x, 39, 4, 0, Math.PI * 2)
    e.fill()
  }

  // Arm: shoulder at the top of its region, ball hand at the bottom.
  g.fillStyle = '#fff'
  g.fillRect(73, 4, 14, 100)
  g.beginPath()
  g.arc(80, 110, 14, 0, Math.PI * 2)
  g.fill()
  return { color, glow }
}

function texture(device: pc.GraphicsDevice, source: HTMLCanvasElement, name: string): pc.Texture {
  const t = new pc.Texture(device, {
    name,
    width: ATLAS_W,
    height: ATLAS_H,
    format: pc.PIXELFORMAT_SRGBA8,
    mipmaps: true,
    addressU: pc.ADDRESS_CLAMP_TO_EDGE,
    addressV: pc.ADDRESS_CLAMP_TO_EDGE,
  })
  t.setSource(source)
  return t
}

/**
 * Material for card fans: atlas tinted by vertex colour, eyes lit by the glow map, cut
 * out by the atlas alpha. The caller adds the crowd animation shader.
 */
export function crowdCardMaterial(device: pc.GraphicsDevice): pc.StandardMaterial {
  const { color, glow } = drawAtlas()
  const atlas = texture(device, color, 'CrowdCardAtlas')
  const m = new pc.StandardMaterial()
  m.diffuseMap = atlas
  m.diffuseVertexColor = true
  m.emissiveMap = texture(device, glow, 'CrowdCardGlow')
  m.emissive = new pc.Color(1, 1, 1)
  m.opacityMap = atlas
  m.opacityMapChannel = 'a'
  m.alphaTest = 0.5
  m.cull = pc.CULLFACE_NONE
  m.update()
  return m
}

const uv = (px: number, py: number): [number, number] => [px / ATLAS_W, py / ATLAS_H]

/** Bakes card fans into one mesh with the same streams as the 3D crowd (+ UVs). */
export function buildCardCrowd(device: pc.GraphicsDevice, fans: CardFan[]): pc.Mesh | null {
  if (fans.length === 0) return null
  const positions: number[] = []
  const normals: number[] = []
  const colors: number[] = []
  const uvs: number[] = []
  const cheer: number[] = []
  const params: number[] = []
  const indices: number[] = []

  for (const fan of fans) {
    const fwd = { x: Math.sin(fan.yaw), z: Math.cos(fan.yaw) }
    // Viewer's right when looking at the card from the court.
    const right = { x: Math.cos(fan.yaw), z: -Math.sin(fan.yaw) }
    const s = fan.size
    // Card-plane point (r right, u up, lift toward the court) -> scene.
    const at = (r: number, u: number, lift = 0): [number, number, number] => [
      fan.pos.x + right.x * r + fwd.x * lift,
      fan.pos.y + u,
      fan.pos.z + right.z * r + fwd.z * lift,
    ]
    const quad = (corners: [number, number, number][], deltas: [number, number, number][], uvCorners: [number, number][]) => {
      const base = positions.length / 3
      corners.forEach((c, i) => {
        positions.push(...c)
        normals.push(fwd.x, 0, fwd.z)
        colors.push(fan.shirt[0], fan.shirt[1], fan.shirt[2], 1)
        uvs.push(...uvCorners[i])
        cheer.push(...deltas[i], 0)
        params.push(...fan.params)
      })
      indices.push(base, base + 1, base + 2, base, base + 2, base + 3)
    }

    // Body: bottom-left, bottom-right, top-right, top-left.
    const w = (CARD_W * s) / 2, h = CARD_H * s
    const [bx0, by0, bx1, by1] = BODY_PX
    const still: [number, number, number] = [0, 0, 0]
    quad(
      [at(-w, 0), at(w, 0), at(w, h), at(-w, h)],
      [still, still, still, still],
      [uv(bx0, by1), uv(bx1, by1), uv(bx1, by0), uv(bx0, by0)],
    )

    // Arms: a quad from the shoulder along an angle; cheer offsets move it to the raised pose.
    const [ax0, ay0, ax1, ay1] = ARM_PX
    for (const side of [-1, 1]) {
      const shoulder = { r: side * (w - 0.02 * s), u: h * SHOULDER_Y }
      const pose = (angle: number) => {
        // Direction in the card plane: angle 0 = straight down, increasing outward/up.
        const d = { r: side * Math.sin(angle), u: -Math.cos(angle) }
        const n = { r: -d.u, u: d.r }
        const aw = (ARM_W * s) / 2, len = ARM_LEN * s
        return [
          at(shoulder.r - n.r * aw, shoulder.u - n.u * aw, ARM_LIFT),
          at(shoulder.r + n.r * aw, shoulder.u + n.u * aw, ARM_LIFT),
          at(shoulder.r + n.r * aw + d.r * len, shoulder.u + n.u * aw + d.u * len, ARM_LIFT),
          at(shoulder.r - n.r * aw + d.r * len, shoulder.u - n.u * aw + d.u * len, ARM_LIFT),
        ]
      }
      const idle = pose(ARM_IDLE)
      const up = pose(ARM_CHEER)
      const deltas = idle.map((p, i) => [up[i][0] - p[0], up[i][1] - p[1], up[i][2] - p[2]] as [number, number, number])
      quad(idle, deltas, [uv(ax0, ay0), uv(ax1, ay0), uv(ax1, ay1), uv(ax0, ay1)])
    }
  }

  const mesh = new pc.Mesh(device)
  mesh.setPositions(positions)
  mesh.setNormals(normals)
  mesh.setColors(colors)
  mesh.setUvs(0, uvs)
  mesh.setVertexStream(pc.SEMANTIC_ATTR8, cheer, 4)
  mesh.setVertexStream(pc.SEMANTIC_ATTR9, params, 4)
  mesh.setIndices(indices)
  mesh.update()
  const { center, halfExtents: hx } = mesh.aabb
  mesh.aabb = new pc.BoundingBox(center.clone(), new pc.Vec3(hx.x + 0.3, hx.y + 0.6, hx.z + 0.3))
  return mesh
}
