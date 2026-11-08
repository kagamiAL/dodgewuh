import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { session } from '@/stores/session'
import Lobby from '@/views/Lobby.vue'
import type { ServerMessage } from '@/contracts/pending'
import welcome from '../../../contracts/fixtures/valid/welcome.json'

vi.mock('@/stores/connection', () => ({ transport: { send: vi.fn() } }))

const options = { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } }
const registration = { room_id: 'r1', room_code: 'ABC234', member_id: 's1', token: 'test', ws_path: '/ws/rooms/ABC234' }

afterEach(() => session.reset())

describe('lobby connection states', () => {
  it('shows the room code and recovery UI before the welcome arrives', () => {
    session.setRegistration(registration)
    session.setStatus('reconnecting')
    const wrapper = mount(Lobby, options)
    expect(wrapper.text()).toContain('ABC234')
    expect(wrapper.text()).toContain('Retrying automatically')
    expect(wrapper.text()).toContain('Back to home')
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })

  it('replaces the connection UI with seats and host controls on welcome', async () => {
    session.setRegistration(registration)
    const wrapper = mount(Lobby, options)
    session.apply(welcome as ServerMessage)
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.seats li')).toHaveLength(4)
    expect(wrapper.text()).toContain('Start match (0/4 ready)')
    expect(wrapper.text()).not.toContain('Waiting for the game server')
    wrapper.unmount()
  })
})
