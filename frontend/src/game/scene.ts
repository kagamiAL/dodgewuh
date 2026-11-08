import * as pc from 'playcanvas'
import { COURT_HALF_DEPTH, TEAM_COLORS } from './constants'
import { toScene } from './coords'
import { loadCharacterModel, MODEL_URL } from './characterModel'
import { ragdollConfig } from './ragdoll'
import { loadSpringExtras } from './springConfig'
import { createCourt } from './court'
import { createStadium } from './stadium'
import { ACTOR_LIGHT_MASK } from './lighting'
import { instantiateFirstPersonHand, loadFirstPersonHand, type FirstPersonHand } from './firstPersonHand'
import { StateRenderer } from './entities'
import type { State, Team } from './state'

export { toScene } from './coords'

export interface GameScene {
  readonly app: pc.Application
  /** Draw one authoritative server State. The only way game data reaches the scene. */
  renderState(state: State): void
  /** Ride along with this team's character (first person), or null for the elevated overview. */
  setPointOfView(team: Team | null): void
  /**
   * Where a team's player is facing (world x/z, unit), measured locally (e.g. this screen's
   * camera). The first-person view follows it instead of movement; null clears it.
   */
  setFacing(team: Team, dir: { x: number; z: number } | null): void
  destroy(): void
}

/** Eye height for a first-person camera (character is 1.8 m tall). */
const EYE_HEIGHT = 1.6
const FIRST_PERSON_FOV = 75
const OVERVIEW_FOV = 45
/** Higher = camera catches up to the 20 Hz snapshots faster (1/s). */
const FIRST_PERSON_FOLLOW = 12
/**
 * Overhead spotlights, one above each half (metres / degrees from straight down). Tuned so
 * the cone covers the court and fades out around the ad boards, before the stands.
 */
const SPOT_HEIGHT = 14
const SPOT_INNER_DEG = 22
const SPOT_OUTER_DEG = 30
const SPOT_INTENSITY = 2.6
const SPOT_RANGE = 30
/** Actor key lights: degrees from straight down (60 = 30° above the horizon), brightness. */
const ACTOR_KEY_TILT_DEG = 60
const ACTOR_KEY_INTENSITY = 0.7
/** Your held ball in first person: metres ahead of, right of and below the eye. */
const HELD_VIEW_OFFSET = { forward: 0.7, right: 0.26, down: 0.27 }
/** Floor aim guide in first person: where it starts and ends ahead of you (metres). */
const AIM_GUIDE_START = 0.8
const AIM_GUIDE_END = 5.5

/**
 * First-person aim guide: a translucent arrow on the floor pointing where a throw would go
 * (the Arms player's aim, which can differ from where Legs faces). Brighter while holding.
 */
function createAimGuide(): { root: pc.Entity; setStyle(team: Team, holding: boolean): void } {
  const mat = new pc.StandardMaterial()
  mat.blendType = pc.BLEND_NORMAL
  mat.depthWrite = false
  mat.useLighting = false
  const root = new pc.Entity('AimGuide')
  const length = AIM_GUIDE_END - AIM_GUIDE_START - 0.4
  const shaft = new pc.Entity('Shaft')
  shaft.addComponent('render', { type: 'box', material: mat })
  shaft.setLocalScale(0.12, 0.01, length)
  shaft.setLocalPosition(0, 0, -(AIM_GUIDE_START + length / 2))
  const head = new pc.Entity('Head')
  head.addComponent('render', { type: 'cone', material: mat })
  head.setLocalScale(0.45, 0.4, 0.45)
  head.setLocalEulerAngles(-90, 0, 0) // tip from +Y to -Z
  head.setLocalPosition(0, 0, -(AIM_GUIDE_END - 0.2))
  root.addChild(shaft)
  root.addChild(head)
  let style = ''
  return {
    root,
    setStyle(team, holding) {
      const key = `${team}${holding}`
      if (key === style) return
      style = key
      mat.emissive = TEAM_COLORS[team]
      mat.opacity = holding ? 0.8 : 0.3
      mat.update()
    },
  }
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

  // Dark arena: only the overhead spotlights (below) properly light anything.
  app.scene.ambientLight = new pc.Color(0.09, 0.09, 0.12)
  // Night sky; distant stands fade into it.
  const sky = new pc.Color(0.03, 0.04, 0.08)
  app.scene.fog.type = pc.FOG_LINEAR
  app.scene.fog.color = sky
  app.scene.fog.start = 35
  app.scene.fog.end = 90

  const camera = new pc.Entity('Camera')
  camera.addComponent('camera', {
    clearColor: sky,
    fov: OVERVIEW_FOV,
  })
  // Overview: raised behind Team 1's baseline and tilted so both baselines stay in frame.
  const useOverview = () => {
    camera.camera!.fov = OVERVIEW_FOV
    camera.setPosition(toScene(0, -COURT_HALF_DEPTH - 7, 16))
    camera.lookAt(toScene(0, -1.5))
  }
  useOverview()
  app.root.addChild(camera)

  // Arena lighting: two spotlights hung above the court, out of shot, pool warm light on
  // each half. The stands sit outside their cones, so the crowd stays in near darkness,
  // lifted only by the ambient and a faint cool fill so it still reads.
  const lights = new pc.Entity('Lights')
  const fill = new pc.Entity('Fill')
  fill.addComponent('light', { type: 'directional', color: new pc.Color(0.6, 0.65, 0.9), intensity: 0.2 })
  fill.setEulerAngles(50, 30, 0)
  lights.addChild(fill)
  for (const z of [-COURT_HALF_DEPTH / 2, COURT_HALF_DEPTH / 2]) {
    const spot = new pc.Entity('Spotlight')
    // A spot light shines down its entity's -Y, so straight down needs no rotation.
    spot.addComponent('light', {
      type: 'spot',
      color: new pc.Color(1, 0.95, 0.85),
      intensity: SPOT_INTENSITY,
      range: SPOT_RANGE,
      innerConeAngle: SPOT_INNER_DEG,
      outerConeAngle: SPOT_OUTER_DEG,
    })
    spot.setPosition(toScene(0, z, SPOT_HEIGHT))
    lights.addChild(spot)
  }
  // Key lights for characters and balls only (lighting.ts): low and warm from behind each
  // baseline, so whichever end you watch from, the opponent's front and the ball are lit.
  for (const tilt of [-ACTOR_KEY_TILT_DEG, ACTOR_KEY_TILT_DEG]) {
    const key = new pc.Entity('ActorKey')
    key.addComponent('light', {
      type: 'directional',
      color: new pc.Color(1, 0.95, 0.88),
      intensity: ACTOR_KEY_INTENSITY,
      mask: ACTOR_LIGHT_MASK,
    })
    // A directional light shines down its -Y; tilting about X swings it toward ±z.
    key.setEulerAngles(tilt, 0, 0)
    lights.addChild(key)
  }
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
  let povTeam: Team | null = null
  const eye = new pc.Vec3()
  let yaw = 0 // radians; forward = (sin, 0, cos) in scene space
  const facing = new Map<Team, pc.Vec3>()
  let haveEye = false
  const aimGuide = createAimGuide()
  aimGuide.root.enabled = false
  app.root.addChild(aimGuide.root)

  // First-person hand gripping the ball, fixed in view as a camera child. Until it loads
  // (or if it fails) the plain held ball is placed at the same spot instead.
  let hand: FirstPersonHand | null = null
  const o = HELD_VIEW_OFFSET
  void loadFirstPersonHand(app).then((asset) => {
    if (!asset || destroyed) return
    hand = instantiateFirstPersonHand(asset)
    hand.entity.setLocalPosition(o.right, -o.down, -o.forward)
    hand.entity.enabled = false
    camera.addChild(hand.entity)
  })

  app.on('update', (dt: number) => {
    stateRenderer.update(dt)
    stadium.update(dt)
    aimGuide.root.enabled = false
    if (hand) hand.entity.enabled = false
    if (!povTeam) return
    const pov = stateRenderer.pointOfView(povTeam)
    if (!pov) return
    const targetEye = new pc.Vec3(pov.pos.x, EYE_HEIGHT, pov.pos.z)
    const k = haveEye ? 1 - Math.exp(-dt * FIRST_PERSON_FOLLOW) : 1
    eye.lerp(eye, targetEye, k)
    // Turn by the shorter way round so a 180° reversal swings instead of glitching.
    const forward = facing.get(povTeam) ?? pov.forward
    const targetYaw = Math.atan2(forward.x, forward.z)
    const turn = Math.atan2(Math.sin(targetYaw - yaw), Math.cos(targetYaw - yaw))
    yaw += turn * k
    haveEye = true
    camera.setPosition(eye)
    camera.lookAt(eye.x + Math.sin(yaw), EYE_HEIGHT - 0.1, eye.z + Math.cos(yaw))

    // Aim guide on the floor under you, pointing along the Arms player's aim.
    aimGuide.root.enabled = true
    aimGuide.setStyle(povTeam, pov.holding)
    aimGuide.root.setPosition(eye.x, 0.02, eye.z)
    aimGuide.root.lookAt(eye.x + pov.aim.x, 0.02, eye.z + pov.aim.z)

    // Your own held ball sits in view, bottom right, like a held item in a shooter: the
    // hand model (it has its own ball) or, as a fallback, the plain ball at the same spot.
    const held = stateRenderer.ownHeldBall()
    if (held && hand) {
      hand.setTeam(povTeam)
      hand.entity.enabled = true
      held.enabled = false
    } else if (held) {
      const p = eye.clone()
        .add(camera.forward.clone().mulScalar(o.forward))
        .add(camera.right.clone().mulScalar(o.right))
        .add(camera.up.clone().mulScalar(-o.down))
      held.setPosition(p)
    }
  })
  app.start()

  return {
    app,
    renderState: (state) => stateRenderer.render(state),
    setFacing(team, dir) {
      if (dir) facing.set(team, toScene(dir.x, dir.z))
      else facing.delete(team)
    },
    setPointOfView(team) {
      if (team === povTeam) return
      povTeam = team
      haveEye = false // snap to the new viewpoint instead of gliding across the court
      stateRenderer.setHiddenTeam(team)
      if (team) camera.camera!.fov = FIRST_PERSON_FOV
      else useOverview()
    },
    destroy() {
      destroyed = true
      resizeObserver.disconnect()
      app.destroy()
    },
  }
}
