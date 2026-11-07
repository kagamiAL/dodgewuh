import * as pc from 'playcanvas'
import { COURT_HALF_DEPTH } from './constants'
import { toScene } from './coords'
import { loadCharacterModel, MODEL_URL } from './characterModel'
import { ragdollConfig } from './ragdoll'
import { loadSpringExtras } from './springConfig'
import { createCourt } from './court'
import { createStadium } from './stadium'
import { StateRenderer } from './entities'
import type { State, Team } from './state'

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
/** Eye height for a first-person camera (character is 1.8 m tall). */
const EYE_HEIGHT = 1.6
const FIRST_PERSON_FOV = 75
/** Higher = camera catches up to the 20 Hz snapshots faster (1/s). */
const FIRST_PERSON_FOLLOW = 12

export interface SceneOptions {
  /** Ride along with this team's character instead of the shared elevated camera. */
  firstPerson?: Team
}

export function createScene(canvas: HTMLCanvasElement, options: SceneOptions = {}): GameScene {
  const app = new pc.Application(canvas, {})

  // Render at device resolution (capped at 2x) and size from the canvas's CSS box.
  app.graphicsDevice.maxPixelRatio = Math.min(window.devicePixelRatio, 2)
  app.setCanvasResolution(pc.RESOLUTION_AUTO)

  const resizeObserver = new ResizeObserver(() => app.updateCanvasSize())
  resizeObserver.observe(canvas)

  app.scene.ambientLight = new pc.Color(0.35, 0.35, 0.4)
  // Night sky; distant stands fade into it.
  const sky = new pc.Color(0.03, 0.04, 0.08)
  app.scene.fog.type = pc.FOG_LINEAR
  app.scene.fog.color = sky
  app.scene.fog.start = 35
  app.scene.fog.end = 90

  const camera = new pc.Entity('Camera')
  camera.addComponent('camera', {
    clearColor: sky,
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

  app.root.addChild(createCourt(app.graphicsDevice))
  const stadium = createStadium(app)
  app.root.addChild(stadium.root)
  const stateRenderer = new StateRenderer(app.root)
  // Capsules render immediately; the model replaces them when it arrives.
  let destroyed = false
  // Spring tuning is authored in Blender and read from the same .glb.
  void Promise.all([loadCharacterModel(app), loadSpringExtras(MODEL_URL)]).then(([asset, extras]) => {
    if (asset && !destroyed) stateRenderer.setCharacterModel(asset, ragdollConfig(extras))
  })

  // First person: follow the character smoothly so 20 Hz snapshots don't judder.
  const eye = new pc.Vec3()
  const look = new pc.Vec3()
  let haveEye = false
  if (options.firstPerson) camera.camera!.fov = FIRST_PERSON_FOV

  app.on('update', (dt: number) => {
    stateRenderer.update(dt)
    stadium.update(dt)
    if (!options.firstPerson) return
    const pov = stateRenderer.pointOfView(options.firstPerson)
    if (!pov) return
    const targetEye = new pc.Vec3(pov.pos.x, EYE_HEIGHT, pov.pos.z)
    const k = haveEye ? 1 - Math.exp(-dt * FIRST_PERSON_FOLLOW) : 1
    eye.lerp(eye, targetEye, k)
    look.lerp(look, pov.forward, k).normalize()
    haveEye = true
    camera.setPosition(eye)
    camera.lookAt(eye.x + look.x, EYE_HEIGHT - 0.1, eye.z + look.z)
  })
  app.start()

  return {
    app,
    renderState: (state) => stateRenderer.render(state),
    destroy() {
      destroyed = true
      stadium.destroy()
      resizeObserver.disconnect()
      app.destroy()
    },
  }
}
