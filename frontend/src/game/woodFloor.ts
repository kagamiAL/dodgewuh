import * as pc from 'playcanvas'

// Procedural maple gym-floor texture: planks run along world z with staggered
// joints and slight per-board colour variation. Drawn once on a canvas and tiled.
// Cosmetic only.

/** World metres covered by one repeat of the texture. */
export const WOOD_TILE_M = 4
const SIZE = 1024
const PLANK_M = 0.2
const MIN_BOARD_M = 0.8
const MAX_BOARD_M = 2.4
const SEED = 7

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

function drawPlanks(ctx: CanvasRenderingContext2D): void {
  const rand = seeded(SEED)
  const pxPerM = SIZE / WOOD_TILE_M
  const columns = Math.round(WOOD_TILE_M / PLANK_M)
  const colW = SIZE / columns

  ctx.fillStyle = 'rgb(236, 208, 160)'
  ctx.fillRect(0, 0, SIZE, SIZE)

  for (let c = 0; c < columns; c++) {
    const x = c * colW
    // Boards wrap top-to-bottom so the tile repeats seamlessly along z.
    let y = rand() * SIZE
    let covered = 0
    while (covered < SIZE) {
      const len = Math.min((MIN_BOARD_M + rand() * (MAX_BOARD_M - MIN_BOARD_M)) * pxPerM, SIZE - covered)
      const shade = 0.9 + rand() * 0.14
      const color = `rgb(${Math.round(236 * shade)}, ${Math.round(206 * shade)}, ${Math.round(156 * shade)})`
      const segments = y + len > SIZE ? [[y, SIZE - y], [0, y + len - SIZE]] : [[y, len]]
      for (const [sy, sl] of segments) {
        ctx.fillStyle = color
        ctx.fillRect(x, sy, colW, sl)
        // Faint grain streaks along the board.
        for (let g = 0; g < 4; g++) {
          ctx.fillStyle = `rgba(150, 105, 60, ${0.04 + rand() * 0.05})`
          ctx.fillRect(x + rand() * colW, sy, 1 + rand() * 2, sl)
        }
      }
      // End joint between boards.
      ctx.fillStyle = 'rgba(120, 85, 50, 0.45)'
      ctx.fillRect(x, (y + len) % SIZE, colW, 2)
      y = (y + len) % SIZE
      covered += len
    }
    // Seam between plank columns.
    ctx.fillStyle = 'rgba(120, 85, 50, 0.35)'
    ctx.fillRect(x, 0, 2, SIZE)
  }
}

let canvas: HTMLCanvasElement | null = null
const textures = new WeakMap<pc.GraphicsDevice, pc.Texture>()

/** The shared repeating wood texture for `device`. Tile with diffuseMapTiling = size / WOOD_TILE_M. */
export function createWoodTexture(device: pc.GraphicsDevice): pc.Texture {
  const cached = textures.get(device)
  if (cached) return cached
  if (!canvas) {
    canvas = document.createElement('canvas')
    canvas.width = SIZE
    canvas.height = SIZE
    const ctx = canvas.getContext('2d')
    if (ctx) drawPlanks(ctx)
  }
  const texture = new pc.Texture(device, {
    name: 'WoodFloor',
    width: SIZE,
    height: SIZE,
    format: pc.PIXELFORMAT_SRGBA8,
    mipmaps: true,
    anisotropy: 8,
    addressU: pc.ADDRESS_REPEAT,
    addressV: pc.ADDRESS_REPEAT,
  })
  texture.setSource(canvas)
  textures.set(device, texture)
  return texture
}

/** Wood floor material tinted by `tint` (white = natural maple), tiled for a w×d metre plane. */
export function woodMaterial(texture: pc.Texture, tint: pc.Color, w: number, d: number): pc.StandardMaterial {
  const m = new pc.StandardMaterial()
  m.diffuseMap = texture
  m.diffuse = tint
  m.diffuseMapTiling = new pc.Vec2(w / WOOD_TILE_M, d / WOOD_TILE_M)
  m.gloss = 0.55
  m.update()
  return m
}
