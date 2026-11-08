import * as pc from 'playcanvas'

// The arena is lit by overhead spotlights, which leave the sides of characters and the
// undersides of balls nearly black. Low "key" lights from both ends fill those in, but
// only for meshes opted in here, so the crowd and stands stay in the dark.

/** Light mask bit used only by the actor key lights (bits 1, 2, 4 are PlayCanvas's own). */
export const ACTOR_LIGHT_MASK = 8

/** Let every mesh under `entity` receive the actor key lights as well as normal lighting. */
export function litAsActor(entity: pc.Entity): void {
  for (const rc of entity.findComponents('render') as pc.RenderComponent[]) {
    for (const mi of rc.meshInstances) mi.mask = pc.MASK_AFFECT_DYNAMIC | ACTOR_LIGHT_MASK
  }
}
