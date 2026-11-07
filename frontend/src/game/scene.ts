import * as pc from 'playcanvas'
import { COURT_HALF_DEPTH } from './constants'
import { toScene } from './coords'
import { createCourt } from './court'
import { StateRenderer } from './entities'
import type { State } from './state'

export { toScene } from './coords'

export interface GameScene {
  readonly app: pc.Application
  /** Draw one authoritative server State. The only way game data reaches the scene. */
  renderState(state: State): void
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
    fov: 45,
  })
  // Raised behind Team 1's baseline and tilted so both baselines stay in frame.
  camera.setPosition(toScene(0, -COURT_HALF_DEPTH - 7, 16))
  camera.lookAt(toScene(0, -1.5))
  app.root.addChild(camera)

  const lights = new pc.Entity('Lights')
  lights.addComponent('light', { type: 'directional', intensity: 1 })
  lights.setEulerAngles(50, 30, 0)
  app.root.addChild(lights)

  app.root.addChild(createCourt())
  const stateRenderer = new StateRenderer(app.root)

  app.start()

  return {
    app,
    renderState: (state) => stateRenderer.render(state),
    destroy() {
      resizeObserver.disconnect()
      app.destroy()
    },
  }
}
