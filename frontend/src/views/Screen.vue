<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { createScene, type GameScene } from '@/game/scene'
import { session } from '@/stores/session'

const route = useRoute()
// Dev-only mock routes (plans/04), compiled out of production builds:
//   /screen?mock=1         scripted 20 Hz feed through session.apply (same path as live)
//   /screen?mock=lobby     Richard's reset-lobby fixture
//   /screen?mock=movement  Richard's active-movement fixture
//   /screen?mock=held      03 example 11–12 (Team 1 holding b1)
const mock = import.meta.env.DEV ? (route.query.mock as string | undefined) : undefined

const canvas = ref<HTMLCanvasElement | null>(null)
const error = ref<string | null>(null)
// Engine objects stay out of Vue's deep reactivity (plans/01-architecture.md).
const scene = shallowRef<GameScene | null>(null)
let stopMock: (() => void) | null = null

// The screen only ever draws what the session store holds.
watch(
  () => session.data.state,
  (state) => {
    if (state) scene.value?.renderState(state)
  },
)

onMounted(async () => {
  if (!canvas.value) return
  try {
    scene.value = createScene(canvas.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    return
  }
  if (session.data.state) scene.value.renderState(session.data.state)

  if (mock === '1') {
    const { startMockSource } = await import('@/game/mockSource')
    stopMock = startMockSource((msg) => session.apply(msg))
  } else if (mock) {
    const { FIXTURES } = await import('@/game/fixtures')
    const fixture = FIXTURES[mock]
    if (fixture) session.apply(fixture)
    else error.value = `Unknown mock "${mock}". Try: 1, ${Object.keys(FIXTURES).join(', ')}`
  }
})

onBeforeUnmount(() => {
  stopMock?.()
  if (mock) session.reset() // never leak fake state into a real session
  scene.value?.destroy()
  scene.value = null
})
</script>

<template>
  <main class="screen">
    <canvas ref="canvas" class="game-canvas" />
    <p v-if="error" class="error">Could not start the 3D view: {{ error }}</p>
    <p v-if="mock && session.data.state" class="mock-label">
      MOCK · {{ session.data.state.phase }} · epoch {{ session.data.state.epoch }} · tick
      {{ session.data.state.tick }}
    </p>
  </main>
</template>

<style scoped>
.screen {
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}
.game-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
.mock-label {
  position: absolute;
  top: 8px;
  left: 12px;
  margin: 0;
  font: 12px ui-monospace, monospace;
  color: #fc6;
}
.error {
  position: absolute;
  inset: 0;
  margin: auto;
  height: fit-content;
  text-align: center;
}
</style>
