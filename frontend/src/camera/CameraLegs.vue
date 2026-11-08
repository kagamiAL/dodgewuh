<script setup lang="ts">
// Screen camera → which way a team's Legs player faces. The frame is split down the middle:
// whoever stands in the RIGHT half of the (mirrored) preview is Legs; the left half (Arms) is
// ignored. Their pocketed phone detects jogging; while it does, the character moves the way this
// camera sees them face. Players swap halves each round; during role_switch/countdown a large
// preview shows where to stand and whether Legs is in position.
//
// The screen claims a team with camera.claim and sends input.legs at 20 Hz while active, carrying
// the facing as a unit vector (zero when nobody is tracked). The server uses it as the direction
// for that team's Legs phone input (backend/app/services/game.py).

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Team, Vec2 } from '@/contracts/pending'
import { session } from '@/stores/session'
import { transport } from '@/stores/connection'
import { TEAM_HEX } from '@/theme'
import { createPoseTracker, pickLegsPerson, type Landmark, type PoseState } from './poseTracker'

const MP = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.2.2'
const MODEL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task'
const STORE_KEY = 'dodgewuh.cameraTeam'
const SEND_MS = 50 // 20 Hz (03)

// The player's facing in world x/z while tracked, so this screen's first-person view can
// turn with them even when they are standing still (facing is not part of input.legs).
const emit = defineEmits<{ facing: [value: { team: Team; dir: Vec2 } | null] }>()

const team = ref<Team | null>(loadTeam())
const status = ref('')
const live = ref<PoseState>({ present: false, facing: null, yaw_deg: null, dir: null })
const video = ref<HTMLVideoElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)

const state = computed(() => session.data.state)
const phase = computed(() => state.value?.phase ?? 'lobby')
const big = computed(() => team.value !== null && (phase.value === 'role_switch' || phase.value === 'countdown'))
const inPosition = computed(() => live.value.present && live.value.facing === 'screen')

// MediaPipe is loaded from the CDN at runtime, so it is untyped here.
let landmarker: any = null
let connections: { start: number; end: number }[] = []
let stream: MediaStream | null = null
let raf = 0
let sendTimer: ReturnType<typeof setInterval> | null = null
let lastVideoT = -1
let poses: Landmark[][] = []
let legsIndex = -1
const tracker = createPoseTracker()

function loadTeam(): Team | null {
  try {
    const v = sessionStorage.getItem(STORE_KEY)
    return v === '1' ? 1 : v === '2' ? 2 : null
  } catch {
    return null
  }
}

function claim(): void {
  transport.send({ v: 1, type: 'camera.claim', payload: { team: team.value } })
}

// 02: Team 1 forward is +z and right is +x; Team 2 is mirrored (same mapping as phone Legs).
function toWorld(dir: { r: number; f: number }, t: Team): Vec2 {
  const s = t === 1 ? 1 : -1
  return { x: dir.r * s, z: dir.f * s }
}

async function startCamera(): Promise<void> {
  if (landmarker && stream) return
  status.value = 'Loading pose model…'
  try {
    const vision = await import(/* @vite-ignore */ `${MP}/vision_bundle.mjs`)
    const files = await vision.FilesetResolver.forVisionTasks(`${MP}/wasm`)
    const options = (delegate: 'GPU' | 'CPU') => ({ baseOptions: { modelAssetPath: MODEL, delegate }, runningMode: 'VIDEO', numPoses: 2 })
    try {
      landmarker = await vision.PoseLandmarker.createFromOptions(files, options('GPU'))
    } catch {
      landmarker = await vision.PoseLandmarker.createFromOptions(files, options('CPU'))
    }
    connections = vision.PoseLandmarker.POSE_CONNECTIONS ?? []
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }, audio: false })
    if (!video.value) return
    video.value.srcObject = stream
    await video.value.play()
    status.value = ''
    raf = requestAnimationFrame(loop)
  } catch (e) {
    status.value = `Camera failed: ${e instanceof Error ? e.message : String(e)}`
  }
}

function stopCamera(): void {
  cancelAnimationFrame(raf)
  stream?.getTracks().forEach((t) => t.stop())
  stream = null
  landmarker?.close?.()
  landmarker = null
  poses = []
  legsIndex = -1
  live.value = tracker.push(performance.now(), null)
}

function loop(): void {
  const v = video.value
  if (landmarker && v && v.readyState >= 2 && v.currentTime !== lastVideoT) {
    lastVideoT = v.currentTime
    const t = performance.now()
    // The result is only valid inside the callback, so copy what we need there.
    landmarker.detectForVideo(v, t, (res: { landmarks: Landmark[][]; worldLandmarks: Landmark[][] }) => {
      poses = res.landmarks.map((lm) => lm.map((p) => ({ x: p.x, y: p.y, z: p.z, visibility: p.visibility })))
      legsIndex = pickLegsPerson(poses)
      const world = legsIndex >= 0 ? res.worldLandmarks[legsIndex].map((p) => ({ x: p.x, y: p.y, z: p.z })) : null
      live.value = tracker.push(t, world)
    })
  }
  draw()
  raf = requestAnimationFrame(loop)
}

function draw(): void {
  const v = video.value
  const c = canvas.value
  if (!v || !c || !v.videoWidth) return
  if (c.width !== v.videoWidth) {
    c.width = v.videoWidth
    c.height = v.videoHeight
  }
  const g = c.getContext('2d')!
  const w = c.width
  const h = c.height
  // Mirrored like a selfie so "right half" on screen is the players' right.
  g.save()
  g.translate(w, 0)
  g.scale(-1, 1)
  g.drawImage(v, 0, 0, w, h)
  poses.forEach((lm, i) => {
    const legs = i === legsIndex
    g.lineWidth = legs ? 6 : 3
    g.strokeStyle = legs ? TEAM_HEX[team.value ?? 1] : 'rgba(255,255,255,0.35)'
    for (const { start, end } of connections) {
      const a = lm[start]
      const b = lm[end]
      if ((a.visibility ?? 1) < 0.3 || (b.visibility ?? 1) < 0.3) continue
      g.beginPath()
      g.moveTo(a.x * w, a.y * h)
      g.lineTo(b.x * w, b.y * h)
      g.stroke()
    }
  })
  g.restore()
  // Legs half (right on screen) tinted, Arms half dimmed, divider in the middle.
  g.fillStyle = 'rgba(0,0,0,0.45)'
  g.fillRect(0, 0, w / 2, h)
  g.fillStyle = 'rgba(255,255,255,0.9)'
  g.fillRect(w / 2 - 3, 0, 6, h)
  g.font = `bold ${Math.round(h / 14)}px system-ui, sans-serif`
  g.textAlign = 'center'
  g.fillText('ARMS', w / 4, h / 10)
  g.fillStyle = inPosition.value ? '#3c6' : '#fc6'
  g.fillText('LEGS', (3 * w) / 4, h / 10)
}

function tick(): void {
  const st = state.value
  if (team.value === null || !st || st.phase !== 'active' || session.data.status !== 'connected') return
  const dir = live.value.present ? live.value.dir : null
  const facing = dir ? toWorld(dir, team.value) : { x: 0, z: 0 }
  transport.send({ v: 1, type: 'input.legs', payload: { seq: transport.nextInputSeq(), epoch: st.epoch, move: facing } })
}

function onPick(e: Event): void {
  const v = (e.target as HTMLSelectElement).value
  setTeam(v === '1' ? 1 : v === '2' ? 2 : null)
}

function setTeam(next: Team | null): void {
  team.value = next
  try {
    if (next === null) sessionStorage.removeItem(STORE_KEY)
    else sessionStorage.setItem(STORE_KEY, String(next))
  } catch {
    // per-tab convenience only
  }
}

watch(team, (t) => {
  claim()
  if (t === null) stopCamera()
  else void startCamera()
})
// Re-claim after every (re)connect; the server forgets a screen's claim when it disconnects.
watch(() => session.data.status, (s) => {
  if (s === 'connected' && team.value !== null) claim()
})

watch(
  () => [team.value, live.value.present ? live.value.dir : null] as const,
  ([t, dir]) => {
    // Keep the last facing while nobody is tracked; clear it only when the claim ends.
    if (t === null) emit('facing', null)
    else if (dir) emit('facing', { team: t, dir: toWorld(dir, t) })
  },
)

const facingText = computed(() => {
  const f = live.value.facing
  if (!live.value.present) return 'No one in the LEGS half'
  return `Legs facing ${f === 'screen' ? 'the screen' : f}`
})

onMounted(() => {
  sendTimer = setInterval(tick, SEND_MS)
  if (team.value !== null) {
    void startCamera()
    if (session.data.status === 'connected') claim()
  }
})
onBeforeUnmount(() => {
  if (sendTimer) clearInterval(sendTimer)
  stopCamera()
})
</script>

<template>
  <div class="camera" :class="{ big }">
    <div v-if="big" class="switch">
      <h2>{{ phase === 'role_switch' ? 'Switch spots!' : 'Get in position' }}</h2>
      <p>
        <strong :style="{ color: TEAM_HEX[team ?? 1] }">Team {{ team }} Legs</strong>: stand in the
        <strong>right half</strong>, face the screen. Arms: left half.
      </p>
    </div>
    <video ref="video" class="hidden-video" playsinline muted />
    <canvas v-show="team !== null" ref="canvas" class="preview" />
    <p v-if="team !== null" class="state" :class="{ ok: big ? inPosition : live.present }">
      {{ big ? (inPosition ? '✓ Legs player in position' : facingText) : facingText }}
    </p>
    <p v-if="status" class="status">{{ status }}</p>
    <label v-if="!big" class="pick">
      Camera controls
      <select :value="team ?? ''" @change="onPick">
        <option value="">nobody</option>
        <option value="1">Team 1 Legs</option>
        <option value="2">Team 2 Legs</option>
      </select>
    </label>
  </div>
</template>

<style scoped>
.camera {
  position: absolute;
  right: 12px;
  bottom: 12px;
  width: min(320px, 40vw);
  padding: 8px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.6);
  font-size: 0.85rem;
  z-index: 5;
}
.camera.big {
  inset: 6vh 8vw;
  width: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: rgba(0, 0, 0, 0.85);
  font-size: 1.2rem;
}
.switch {
  text-align: center;
}
.switch h2 {
  margin: 0.2rem 0;
  font-size: clamp(1.8rem, 5vw, 3.5rem);
}
.hidden-video {
  display: none;
}
.preview {
  display: block;
  width: 100%;
  border-radius: 6px;
}
.camera.big .preview {
  width: auto;
  max-width: 100%;
  max-height: 60vh;
}
.state {
  margin: 0.4rem 0 0;
  color: #fc6;
}
.state.ok {
  color: #3c6;
}
.camera.big .state {
  font-size: 1.6rem;
  font-weight: 800;
}
.status {
  margin: 0.3rem 0 0;
  color: #f88;
}
.pick {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-top: 0.4rem;
  color: #ccc;
}
</style>
