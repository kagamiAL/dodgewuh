import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// Backend runs on 127.0.0.1:8000 locally (plans/04-repository-structure.md); BACKEND_URL
// overrides it when that port is taken. Proxy keeps /api and /ws same-origin without rewriting.
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // Phones need HTTPS for motion sensors; a `cloudflared tunnel --url http://localhost:5173`
    // URL must be accepted as a host (and listed in the coordinator's DEV_ORIGINS).
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/api': { target: backend, changeOrigin: false },
      '/ws': { target: backend, ws: true, changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.ts'],
  },
})
