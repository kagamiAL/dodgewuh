import * as pc from 'playcanvas'
import type { CharacterRig } from './characterModel'

// Procedural "ragdoll": every joint chases a target through a damped spring, so the
// body lags, overshoots and wobbles. Purely cosmetic and driven only by what the
// server already sends (position from the Legs player, aim from the Arms player,
// possession, throws). No physics engine (plans/01: rigid-body physics is off).
//
// Model space: +Z front, +Y up, +X is the model's LEFT. Pitch (about X) > 0 tips the
// top forward; roll (about Z) > 0 tips the top toward the model's right.

/** Damped spring on one angle (degrees). Semi-implicit Euler, sub-stepped by caller. */
class Spring {
  x = 0
  v = 0
  constructor(
    private readonly omega: number, // natural frequency, rad/s
    private readonly zeta: number, // damping ratio (<1 wobbles)
    private readonly limit: number, // clamp, degrees
  ) {}

  step(target: number, dt: number): void {
    const a = this.omega * this.omega * (target - this.x) - 2 * this.zeta * this.omega * this.v
    this.v += a * dt
    this.x += this.v * dt
    if (this.x > this.limit) { this.x = this.limit; this.v = Math.min(this.v, 0) }
    if (this.x < -this.limit) { this.x = -this.limit; this.v = Math.max(this.v, 0) }
  }
}

interface SpringSpec { frequency: number; damping: number; limit: number }

/**
 * Tuning, authored in Blender as custom properties (assets/character/spring_props.py)
 * and read from the .glb. Values below are the fallbacks used when a property is
 * missing; keep them equal to spring_props.DEFAULTS.
 */
export interface RagdollConfig {
  accelSmoothing: number // s, low-pass on velocity before differentiating
  throwTwist: number // deg/s kick to chest yaw on a throw
  throwTorso: number
  torso: SpringSpec & { gain: number; runLean: number }
  chest: SpringSpec & { gain: number; whip: number; twist: SpringSpec }
  head: SpringSpec & { whip: number }
  armL: SpringSpec & { gain: number; whip: number }
  armR: SpringSpec & { gain: number; whip: number; throwKick: number }
  legs: { swingDeg: number; strideM: number; twist: SpringSpec; twistMinSpeed: number }
}

/** Builds the config from glTF node extras (node name -> spring_* properties). */
export function ragdollConfig(extras: Record<string, Record<string, number>>): RagdollConfig {
  const get = (node: string, key: string, fallback: number) => extras[node]?.[`spring_${key}`] ?? fallback
  const spec = (node: string, f: number, d: number, l: number): SpringSpec => ({
    frequency: get(node, 'frequency', f),
    damping: get(node, 'damping', d),
    limit: get(node, 'limit_deg', l),
  })
  const twist = (node: string, f: number, d: number, l: number): SpringSpec => ({
    frequency: get(node, 'twist_frequency', f),
    damping: get(node, 'twist_damping', d),
    limit: get(node, 'twist_limit_deg', l),
  })
  return {
    accelSmoothing: get('RedGuy_Root', 'accel_smoothing_s', 0.1),
    throwTwist: get('RedGuy_Root', 'throw_twist', 520),
    throwTorso: get('RedGuy_Root', 'throw_torso', 220),
    torso: { ...spec('RG_TorsoRig', 9, 0.35, 30), gain: get('RG_TorsoRig', 'gain', 0.55), runLean: get('RG_TorsoRig', 'run_lean', 4) },
    chest: {
      ...spec('RG_ChestRig', 6, 0.22, 40),
      gain: get('RG_ChestRig', 'gain', 0.9),
      whip: get('RG_ChestRig', 'whip', 0.06),
      twist: twist('RG_ChestRig', 8, 0.4, 80),
    },
    head: { ...spec('RG_HeadRig', 7, 0.18, 30), whip: get('RG_HeadRig', 'whip', 0.08) },
    armL: { ...spec('RG_ArmRig_L', 5, 0.14, 75), gain: get('RG_ArmRig_L', 'gain', 2.2), whip: get('RG_ArmRig_L', 'whip', 0.12) },
    armR: {
      ...spec('RG_ArmRig_R', 5.5, 0.16, 75),
      gain: get('RG_ArmRig_R', 'gain', 2.2),
      whip: get('RG_ArmRig_R', 'whip', 0.1),
      throwKick: get('RG_ArmRig_R', 'throw_kick', -1100),
    },
    legs: {
      swingDeg: get('RG_LegRig_L', 'swing_deg', 30),
      strideM: get('RG_LegRig_L', 'stride_m', 1.1),
      twist: twist('RG_LegRig_L', 6, 0.7, 70),
      twistMinSpeed: get('RG_LegRig_L', 'twist_min_speed', 0.4),
    },
  }
}

const spring = (s: SpringSpec, limitScale = 1) => new Spring(s.frequency, s.damping, s.limit * limitScale)

const ARM_HANG_DEG = 68
// Running without a ball: arms trail behind the direction of travel (degrees at full speed)
// and flail with the stride, left and right out of step.
const ARM_TRAIL_DEG = 55
const ARM_FLAIL_DEG = 18
const RUN_SPEED = 3.5 // m/s, the server's move speed
const HANG_L = new pc.Quat().setFromEulerAngles(0, 0, -ARM_HANG_DEG)
const HANG_R = new pc.Quat().setFromEulerAngles(0, 0, ARM_HANG_DEG)
const HOLD_R = new pc.Quat().setFromEulerAngles(0, 90, -10)

const tmpQ = new pc.Quat()
const tmpBase = new pc.Quat()

function wrapDeg(a: number): number {
  return ((((a + 180) % 360) + 360) % 360) - 180
}

/** Heading in degrees of an x/z scene direction (rotation about +Y from +Z). */
export function headingDeg(x: number, z: number): number {
  return (Math.atan2(x, z) * 180) / Math.PI
}

export interface RagdollInput {
  /** Smoothed scene-space velocity of the character root (m/s). */
  velX: number
  velZ: number
  /** Heading the upper body should face (the Arms player's aim). */
  aimHeading: number
  holding: boolean
  /**
   * The Arms phone's throwing-arm angle while carrying (Character.arm_pitch, degrees: 90 up,
   * >90 back over the shoulder, 0 toward the opponent), or null. Drives the throw pose.
   */
  armPitch?: number | null
}

/**
 * Phone arm angle → extra right-arm pitch (degrees, chest space; + = back, − = forward, matching
 * throwKick's negative forward whip). Upright phone = the normal carry pose. Tilting back winds
 * the arm up over the shoulder; chopping forward brings it through. Exaggerated on purpose: a
 * small phone tilt should read as a full throwing arm on the TV.
 */
export function throwPoseOffset(armPitch: number): number {
  const off = armPitch >= 90 ? (armPitch - 90) * 2 : (armPitch - 90) * 0.8
  return Math.max(-72, Math.min(150, off))
}

export class Ragdoll {
  private readonly pelvis: pc.Entity
  private readonly torsoPitch: Spring
  private readonly torsoRoll: Spring
  private readonly chestPitch: Spring
  private readonly chestRoll: Spring
  private readonly chestYaw: Spring
  private readonly headPitch: Spring
  private readonly headRoll: Spring
  private readonly armLPitch: Spring
  private readonly armLRoll: Spring
  private readonly armRPitch: Spring
  private readonly armRRoll: Spring
  private readonly twist: Spring
  private readonly hold = new Spring(10, 0.8, 1)
  /** Throwing-arm pose from the phone; a separate spring so it can swing well past armR's limit. */
  private readonly armThrow = new Spring(16, 0.75, 160)

  private svx = 0
  private svz = 0
  private lastAimHeading: number | null = null
  private walkPhase = 0
  private walkAmount = 0

  constructor(
    private readonly rig: CharacterRig,
    private readonly cfg: RagdollConfig,
  ) {
    this.torsoPitch = spring(cfg.torso)
    this.torsoRoll = spring(cfg.torso, 0.85)
    this.chestPitch = spring(cfg.chest)
    this.chestRoll = spring(cfg.chest, 0.85)
    this.chestYaw = spring(cfg.chest.twist)
    this.headPitch = spring(cfg.head)
    this.headRoll = spring(cfg.head)
    this.armLPitch = spring(cfg.armL)
    this.armLRoll = spring(cfg.armL, 0.67)
    this.armRPitch = spring(cfg.armR)
    this.armRRoll = spring(cfg.armR, 0.67)
    this.twist = spring(cfg.legs.twist)

    // Legs and hips share one yaw pivot so the lower body can face where the Legs
    // player is going while the chest keeps facing the Arms player's aim.
    this.pelvis = new pc.Entity('RG_Pelvis')
    const parent = (rig.torso?.parent ?? rig.legL?.parent) as pc.Entity | null
    parent?.addChild(this.pelvis)
    for (const part of [rig.legL, rig.legR, rig.torso]) part?.reparent(this.pelvis)
  }

  /** A throw just happened: whip the arm and twist the chest. */
  kickThrow(): void {
    this.chestYaw.v += this.cfg.throwTwist
    this.armRPitch.v += this.cfg.armR.throwKick
    this.torsoPitch.v += this.cfg.throwTorso
  }

  update(dt: number, input: RagdollInput): void {
    // Upper body keeps its world heading for a moment when the aim swings.
    if (this.lastAimHeading !== null) {
      this.chestYaw.x -= wrapDeg(input.aimHeading - this.lastAimHeading)
    }
    this.lastAimHeading = input.aimHeading

    const steps = Math.min(8, Math.max(1, Math.ceil(dt / (1 / 120))))
    const h = Math.min(dt, 0.1) / steps
    for (let i = 0; i < steps; i++) this.substep(h, input)
    this.apply()
  }

  private substep(dt: number, input: RagdollInput): void {
    // Acceleration from a low-passed velocity, so 20 Hz snapshot steps don't spike.
    const k = 1 - Math.exp(-dt / this.cfg.accelSmoothing)
    const nvx = this.svx + (input.velX - this.svx) * k
    const nvz = this.svz + (input.velZ - this.svz) * k
    const ax = (nvx - this.svx) / dt
    const az = (nvz - this.svz) / dt
    this.svx = nvx
    this.svz = nvz

    // Express motion in the upper body's frame (it faces the aim).
    const a = (input.aimHeading * Math.PI) / 180
    const fwdX = Math.sin(a)
    const fwdZ = Math.cos(a)
    const leftX = fwdZ
    const leftZ = -fwdX
    const aFwd = ax * fwdX + az * fwdZ
    const aLeft = ax * leftX + az * leftZ
    const vFwd = nvx * fwdX + nvz * fwdZ
    const vLeft = nvx * leftX + nvz * leftZ
    const speed = Math.hypot(nvx, nvz)

    // Lower body turns toward travel (backpedals instead of turning fully around).
    let twistTarget = 0
    if (speed > this.cfg.legs.twistMinSpeed) {
      let d = wrapDeg(headingDeg(nvx, nvz) - input.aimHeading)
      if (d > 110) d -= 180
      if (d < -110) d += 180
      twistTarget = Math.max(-this.cfg.legs.twist.limit, Math.min(this.cfg.legs.twist.limit, d))
    }
    this.twist.step(twistTarget, dt)

    // Inertia: accelerating forward throws the top backward, and so on.
    const c = this.cfg
    this.torsoPitch.step(-c.torso.gain * aFwd + c.torso.runLean * vFwd * 0.5, dt)
    this.torsoRoll.step(c.torso.gain * aLeft, dt)
    this.chestPitch.v -= c.chest.whip * this.torsoPitch.v * dt * 60
    this.chestRoll.v -= c.chest.whip * this.torsoRoll.v * dt * 60
    this.chestPitch.step(-c.chest.gain * aFwd + c.torso.runLean * vFwd * 0.5, dt)
    this.chestRoll.step(c.chest.gain * aLeft, dt)
    this.chestYaw.step(0, dt)

    this.headPitch.v -= c.head.whip * this.chestPitch.v * dt * 60
    this.headRoll.v -= c.head.whip * this.chestRoll.v * dt * 60
    this.headPitch.step(0, dt)
    this.headRoll.step(0, dt)

    // Empty-handed arms trail behind the run and flail with the stride; a held ball keeps the
    // carry pose. Pitch + swings an arm back, so trailing is + when moving toward the aim.
    const free = 1 - Math.max(0, Math.min(1, this.hold.x))
    const clampRun = (v: number) => Math.max(-1, Math.min(1, v / RUN_SPEED))
    const trailPitch = free * ARM_TRAIL_DEG * clampRun(vFwd)
    const trailRoll = -free * ARM_TRAIL_DEG * 0.6 * clampRun(vLeft)
    const flail = free * ARM_FLAIL_DEG * this.walkAmount * Math.sin(this.walkPhase * 2)

    // Arms swing opposite the acceleration and get flung by the chest.
    const chestP = this.chestPitch.v * dt * 60
    const chestR = (this.chestRoll.v + this.chestYaw.v * 0.5) * dt * 60
    this.armLPitch.v += c.armL.whip * chestP
    this.armLRoll.v -= c.armL.whip * chestR
    this.armRPitch.v += c.armR.whip * chestP
    this.armRRoll.v -= c.armR.whip * chestR
    this.armLPitch.step(c.armL.gain * aFwd + trailPitch + flail, dt)
    this.armLRoll.step(-c.armL.gain * 0.7 * aLeft + trailRoll, dt)
    const holdDamp = input.holding ? 0.3 : 1 // a held ball steadies the throwing arm
    this.armRPitch.step(c.armR.gain * aFwd * holdDamp + trailPitch - flail, dt)
    this.armRRoll.step(-c.armR.gain * 0.7 * aLeft * holdDamp + trailRoll, dt)

    this.hold.step(input.holding ? 1 : 0, dt)
    const armPitch = input.armPitch
    this.armThrow.step(input.holding && armPitch !== null && armPitch !== undefined ? throwPoseOffset(armPitch) : 0, dt)
    this.walkPhase += ((speed * dt) / c.legs.strideM) * Math.PI * 2
    this.walkAmount = Math.min(1, speed / 3.5)
  }

  private apply(): void {
    const r = this.rig
    this.pelvis.setLocalEulerAngles(0, this.twist.x, 0)
    r.torso?.setLocalEulerAngles(this.torsoPitch.x, 0, this.torsoRoll.x)
    // Chest counter-rotates the twist so it keeps facing the aim.
    r.chest?.setLocalEulerAngles(this.chestPitch.x, this.chestYaw.x - this.twist.x, this.chestRoll.x)
    r.head?.setLocalEulerAngles(this.headPitch.x, 0, this.headRoll.x)

    const swing = Math.sin(this.walkPhase) * this.cfg.legs.swingDeg * this.walkAmount
    r.legL?.setLocalEulerAngles(swing, 0, 0)
    r.legR?.setLocalEulerAngles(-swing, 0, 0)

    // Offsets apply in the chest's space on top of the base pose.
    if (r.armL) {
      tmpQ.setFromEulerAngles(this.armLPitch.x, 0, this.armLRoll.x)
      r.armL.setLocalRotation(tmpQ.mul(HANG_L))
    }
    if (r.armR) {
      tmpBase.slerp(HANG_R, HOLD_R, Math.max(0, Math.min(1, this.hold.x)))
      tmpQ.setFromEulerAngles(this.armRPitch.x + this.armThrow.x, 0, this.armRRoll.x)
      r.armR.setLocalRotation(tmpQ.mul(tmpBase))
    }
  }
}
