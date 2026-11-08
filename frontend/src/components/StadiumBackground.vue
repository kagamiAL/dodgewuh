<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { GameScene } from '@/game/scene'

const canvas = ref<HTMLCanvasElement | null>(null)
let scene: GameScene | null = null
let disposed = false
let resizeObserver: ResizeObserver | null = null

onMounted(async () => {
  // Keep the form interactive while the game renderer loads. This decorative
  // scene is isolated from room membership and authoritative game state.
  try {
    const { createScene } = await import('@/game/scene')
    if (disposed || !canvas.value) return
    scene = createScene(canvas.value)
    const app = scene.app
    app.graphicsDevice.maxPixelRatio = 1
    app.updateCanvasSize()
    // A blurred backdrop needs a still, not a continuously rendered game.
    app.autoRender = false
    const redraw = () => { app.renderNextFrame = true }
    app.assets.on('load', redraw)
    resizeObserver = new ResizeObserver(redraw)
    resizeObserver.observe(canvas.value)
    redraw()
  } catch {
    // The page's solid background remains usable without WebGL.
    scene?.destroy()
    scene = null
  }
})

onBeforeUnmount(() => {
  disposed = true
  resizeObserver?.disconnect()
  scene?.destroy()
})
</script>

<template>
  <div class="stadium-background" aria-hidden="true">
    <canvas ref="canvas" tabindex="-1" />
    <div class="shade" />
  </div>
</template>

<style scoped>
.stadium-background {
  position: fixed;
  inset: 0;
  z-index: -1;
  overflow: hidden;
  pointer-events: none;
  background: var(--bg);
}
canvas {
  display: block;
  width: 100%;
  height: 100%;
  filter: blur(8px);
  transform: scale(1.04);
}
.shade {
  position: absolute;
  inset: 0;
  background: rgba(10, 17, 25, 0.62);
}
</style>
