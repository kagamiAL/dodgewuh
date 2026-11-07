import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router'

describe('router', () => {
  it('registers every planned route', () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    for (const path of ['/', '/lobby', '/screen', '/phone', '/sensors']) {
      expect(router.resolve(path).matched.length).toBeGreaterThan(0)
    }
  })

  it('falls back to a placeholder when the sensor playground is not merged', async () => {
    const route = routes.find((r) => r.path === '/sensors')!
    const mod = await (route.component as () => Promise<{ default: unknown }>)()
    expect(mod.default).toBeTruthy()
  })
})
