import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PhoneShell from '@/views/PhoneShell.vue'
import { session } from '@/stores/session'
import { transport } from '@/stores/connection'
import type { ServerMessage } from '@/contracts/pending'
import welcome from '../../../contracts/fixtures/valid/welcome.json'

vi.mock('@/stores/connection', () => ({
  connect: vi.fn(async () => {}),
  transport: { send: vi.fn(), subscribe: vi.fn(() => () => {}), close: vi.fn(), nextInputSeq: vi.fn(() => 1) },
}))
vi.mock('@/sensors/sensorService', () => ({
  SENSOR_STALE_MS: 500,
  createSensorService: () => ({
    requestPermissionFromGesture: vi.fn(async () => 'granted'),
    subscribe: vi.fn(() => () => {}), stop: vi.fn(),
  }),
}))

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  session.setRegistration({ room_id: 'r1', room_code: 'ABC234', member_id: 's1', token: 'test', ws_path: '/ws/rooms/ABC234' })
  const message = structuredClone(welcome) as ServerMessage & { type: 'session.welcome' }
  message.payload.room.assignments = [{ member_id: 's1', team: 1, role: 'arms' }]
  message.payload.state.assignments = message.payload.room.assignments
  session.apply(message)
  session.setStatus('connected')
})
afterEach(() => { session.reset(); vi.useRealTimers() })

describe('phone setup', () => {
  it('keeps the setup action before player details', async () => {
    const wrapper = mount(PhoneShell)
    await wrapper.get('.setup-action').trigger('click')
    await flushPromises()
    const order = [...wrapper.element.querySelectorAll('.setup-action, .seats')]
    expect(order[0]?.classList.contains('setup-action')).toBe(true)
    expect(wrapper.get('.setup-action').text()).toBe('Ready to start')
    wrapper.unmount()
  })

  it('locks hand selection while calibrating and offers a retry after failure without claiming progress', async () => {
    const wrapper = mount(PhoneShell)
    await wrapper.get('.setup-action').trigger('click')
    await flushPromises()
    expect(wrapper.get('.hand button').attributes('aria-pressed')).toBe('true')
    await wrapper.get('.setup-action').trigger('click')
    expect(wrapper.get('.setup-status').text()).toContain('Calibrating')
    expect(wrapper.findAll('.hand button').every((b) => b.attributes('disabled') !== undefined)).toBe(true)
    await vi.advanceTimersByTimeAsync(650)
    expect(wrapper.get('.setup-status').text()).toContain('Setup incomplete')
    expect(wrapper.get('.setup-status').text()).not.toContain('Calibrating')
    expect(wrapper.get('.setup-action').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('.hand button').attributes('disabled')).toBeUndefined()
    expect(transport.send).not.toHaveBeenCalledWith(expect.objectContaining({ payload: expect.objectContaining({ ready: true }) }))
    wrapper.unmount()
  })
})
