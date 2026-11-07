<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useRoute } from 'vue-router'
import { createScene, type GameScene } from '@/game/scene'
import { activeSnapshotState } from '@/game/fixtures/activeSnapshot'

const route = useRoute()
// Dev-only mock route (plans/04): never reachable from a production build.
const mock = import.meta.env.DEV && route.query.mock === '1'

const canvas = ref<HTMLCanvasElement | null>(null)
const error = ref<string | null>(null)
// Engine objects stay out of Vue's deep reactivity (plans/01-architecture.md).
const scene = shallowRef<GameScene | null>(null)

onMounted(() => {
  if (!canvas.value) return
  try {
    scene.value = createScene(canvas.value)
    // Development stand-in: the 03 example snapshot until live/mock sources exist.
    if (mock) scene.value.renderState(activeSnapshotState)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
})

onBeforeUnmount(() => {
  scene.value?.destroy()
  scene.value = null
})
</script>

<template>
  <main class="screen">
    <canvas ref="canvas" class="game-canvas" />
    <p v-if="error" class="error">Could not start the 3D view: {{ error }}</p>
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
.error {
  position: absolute;
  inset: 0;
  margin: auto;
  height: fit-content;
  text-align: center;
}
</style>
