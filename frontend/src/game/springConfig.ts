// Ragdoll spring settings authored in Blender (assets/character/spring_props.py) as
// custom properties, exported as glTF node extras. PlayCanvas's loader drops node
// extras, so we read them from the .glb's JSON chunk ourselves.

/** Node name -> its `spring_*` properties. */
export type SpringExtras = Record<string, Record<string, number>>

/** Fetches the .glb (browser-cached alongside the model load) and returns node extras. */
export async function loadSpringExtras(url: string): Promise<SpringExtras> {
  try {
    const buf = await (await fetch(url)).arrayBuffer()
    const view = new DataView(buf)
    // GLB: 12-byte header, then chunk 0 = JSON (length, type 'JSON', bytes).
    if (view.getUint32(0, true) !== 0x46546c67) return {}
    const jsonLength = view.getUint32(12, true)
    const json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 20, jsonLength))) as {
      nodes?: { name?: string; extras?: Record<string, unknown> }[]
    }
    const out: SpringExtras = {}
    for (const node of json.nodes ?? []) {
      if (!node.name || !node.extras) continue
      const props: Record<string, number> = {}
      for (const [k, v] of Object.entries(node.extras)) {
        if (k.startsWith('spring_') && typeof v === 'number' && Number.isFinite(v)) props[k] = v
      }
      out[node.name] = props
    }
    return out
  } catch (e) {
    console.warn('[game] could not read spring settings from model; using defaults', e)
    return {}
  }
}
