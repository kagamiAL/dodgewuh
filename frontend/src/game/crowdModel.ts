import * as pc from 'playcanvas'

// Reads the crowd model's raw geometry so the stadium can bake hundreds of fans into
// a few merged meshes (one draw call per section) instead of one entity per fan.
// Built by assets/character/crowdguy_build.py: two posed meshes, origin at the
// bottom-centre of the body, front on glTF +Z, CG_Body recoloured per fan.

export const CROWD_MODEL_URL = `${import.meta.env.BASE_URL}models/crowdguy.glb`

/** One material's triangles, with the node transform already applied. */
export interface CrowdPart {
  material: string
  positions: Float32Array
  normals: Float32Array
  indices: Uint32Array
}

export interface CrowdModel {
  idle: CrowdPart[]
  cheer: CrowdPart[]
  /** Linear base colour per material name, from the glTF. */
  colors: Record<string, [number, number, number]>
}

interface GltfAccessor { bufferView: number; byteOffset?: number; componentType: number; count: number; type: string }
interface GltfBufferView { byteOffset?: number; byteStride?: number }
interface GltfPrimitive { attributes: Record<string, number>; indices: number; material: number }
interface GltfNode { name: string; mesh?: number; translation?: number[]; rotation?: number[]; scale?: number[] }
interface Gltf {
  nodes: GltfNode[]
  meshes: { primitives: GltfPrimitive[] }[]
  materials: { name: string; pbrMetallicRoughness?: { baseColorFactor?: number[] } }[]
  accessors: GltfAccessor[]
  bufferViews: GltfBufferView[]
}

const COMPONENTS: Record<string, number> = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 }
const READERS: Record<number, { size: number; get: (v: DataView, o: number) => number }> = {
  5121: { size: 1, get: (v, o) => v.getUint8(o) },
  5123: { size: 2, get: (v, o) => v.getUint16(o, true) },
  5125: { size: 4, get: (v, o) => v.getUint32(o, true) },
  5126: { size: 4, get: (v, o) => v.getFloat32(o, true) },
}

function readAccessor(gltf: Gltf, bin: DataView, index: number): number[] {
  const acc = gltf.accessors[index]
  const view = gltf.bufferViews[acc.bufferView]
  const reader = READERS[acc.componentType]
  const n = COMPONENTS[acc.type]
  if (!reader || !n) throw new Error(`unsupported accessor ${index}`)
  const stride = view.byteStride ?? reader.size * n
  const start = (view.byteOffset ?? 0) + (acc.byteOffset ?? 0)
  const out: number[] = []
  for (let i = 0; i < acc.count; i++) {
    for (let c = 0; c < n; c++) out.push(reader.get(bin, start + i * stride + c * reader.size))
  }
  return out
}

function parseGlb(buffer: ArrayBuffer): { gltf: Gltf; bin: DataView } {
  const data = new DataView(buffer)
  if (data.getUint32(0, true) !== 0x46546c67) throw new Error('not a GLB')
  let offset = 12
  let gltf: Gltf | null = null
  let bin: DataView | null = null
  while (offset < buffer.byteLength) {
    const length = data.getUint32(offset, true)
    const type = data.getUint32(offset + 4, true)
    const body = offset + 8
    if (type === 0x4e4f534a) gltf = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, body, length)))
    else if (type === 0x004e4942) bin = new DataView(buffer, body, length)
    offset = body + length
  }
  if (!gltf || !bin) throw new Error('GLB missing JSON or BIN chunk')
  return { gltf, bin }
}

function nodeParts(gltf: Gltf, bin: DataView, name: string): CrowdPart[] {
  const node = gltf.nodes.find((n) => n.name === name)
  if (!node || node.mesh === undefined) throw new Error(`crowd model has no mesh node ${name}`)
  const t = node.translation ?? [0, 0, 0]
  const r = node.rotation ?? [0, 0, 0, 1]
  const s = node.scale ?? [1, 1, 1]
  const m = new pc.Mat4().setTRS(new pc.Vec3(t[0], t[1], t[2]), new pc.Quat(r[0], r[1], r[2], r[3]), new pc.Vec3(s[0], s[1], s[2]))
  const p = new pc.Vec3()

  return gltf.meshes[node.mesh].primitives.map((prim) => {
    const pos = readAccessor(gltf, bin, prim.attributes.POSITION)
    const nrm = readAccessor(gltf, bin, prim.attributes.NORMAL)
    const positions = new Float32Array(pos.length)
    const normals = new Float32Array(nrm.length)
    for (let i = 0; i < pos.length; i += 3) {
      m.transformPoint(p.set(pos[i], pos[i + 1], pos[i + 2]), p)
      positions.set([p.x, p.y, p.z], i)
      m.transformVector(p.set(nrm[i], nrm[i + 1], nrm[i + 2]), p).normalize()
      normals.set([p.x, p.y, p.z], i)
    }
    return {
      material: gltf.materials[prim.material].name,
      positions,
      normals,
      indices: Uint32Array.from(readAccessor(gltf, bin, prim.indices)),
    }
  })
}

/** Loads and parses the crowd model. Resolves null on failure so callers keep the box crowd. */
export async function loadCrowdModel(): Promise<CrowdModel | null> {
  try {
    const response = await fetch(CROWD_MODEL_URL)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const { gltf, bin } = parseGlb(await response.arrayBuffer())
    const colors: CrowdModel['colors'] = {}
    for (const mat of gltf.materials) {
      const f = mat.pbrMetallicRoughness?.baseColorFactor ?? [1, 1, 1, 1]
      colors[mat.name] = [f[0], f[1], f[2]]
    }
    return { idle: nodeParts(gltf, bin, 'CrowdGuy_Idle'), cheer: nodeParts(gltf, bin, 'CrowdGuy_Cheer'), colors }
  } catch (err) {
    console.warn('[game] crowd model failed to load; keeping box fans', err)
    return null
  }
}
