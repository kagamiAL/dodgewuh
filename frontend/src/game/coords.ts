import * as pc from 'playcanvas'

/**
 * World (x, z) from the server -> PlayCanvas position.
 *
 * The camera sits behind Team 1 (negative z) looking toward +z. In PlayCanvas's
 * right-handed, y-up space that puts world +x on the LEFT of the screen, which
 * would mirror Team 1's controls (02 defines Team 1 "right" as +x). Negating x
 * here keeps Team 1's right on screen-right. This is the only place the flip lives.
 */
export function toScene(x: number, z: number, y = 0): pc.Vec3 {
  return new pc.Vec3(-x, y, z)
}
