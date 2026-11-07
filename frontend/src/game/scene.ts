import * as pc from 'playcanvas'

// Court extents from plans/02-game-specification.md (metres).
const COURT_HALF_WIDTH = 6
const COURT_HALF_DEPTH = 9

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

export interface GameScene {
  readonly app: pc.Application
  destroy(): void
}

/**
 * Creates the PlayCanvas application on `canvas`. The canvas's CSS box decides its
 * size; the drawing buffer follows it via ResizeObserver. Call destroy() on unmount.
 */
export function createScene(canvas: HTMLCanvasElement): GameScene {
  const app = new pc.Application(canvas, {})

  // Render at device resolution (capped at 2x) and size from the canvas's CSS box.
  app.graphicsDevice.maxPixelRatio = Math.min(window.devicePixelRatio, 2)
  app.setCanvasResolution(pc.RESOLUTION_AUTO)

  const resizeObserver = new ResizeObserver(() => app.updateCanvasSize())
  resizeObserver.observe(canvas)

  app.scene.ambientLight = new pc.Color(0.35, 0.35, 0.4)

  const camera = new pc.Entity('Camera')
  camera.addComponent('camera', {
    clearColor: new pc.Color(0.07, 0.08, 0.1),
    fov: 50,
  })
  camera.setPosition(toScene(0, -COURT_HALF_DEPTH - 6, 13))
  camera.lookAt(toScene(0, 1))
  app.root.addChild(camera)

  const sun = new pc.Entity('Sun')
  sun.addComponent('light', { type: 'directional', intensity: 1 })
  sun.setEulerAngles(50, 30, 0)
  app.root.addChild(sun)

  // Placeholder floor so the mount is visibly working; the court markings come next.
  const floorMaterial = new pc.StandardMaterial()
  floorMaterial.diffuse = new pc.Color(0.18, 0.32, 0.22)
  floorMaterial.update()
  const floor = new pc.Entity('Floor')
  floor.addComponent('render', { type: 'plane', material: floorMaterial })
  floor.setLocalScale(COURT_HALF_WIDTH * 2, 1, COURT_HALF_DEPTH * 2)
  app.root.addChild(floor)

  app.start()

  return {
    app,
    destroy() {
      resizeObserver.disconnect()
      app.destroy()
    },
  }
}
