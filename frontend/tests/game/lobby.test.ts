import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { session } from '@/stores/session'
import Lobby from '@/views/Lobby.vue'
import { leave, transport } from '@/stores/connection'
import type { ServerMessage } from '@/contracts/pending'
import welcome from '../../../contracts/fixtures/valid/welcome.json'

const { push } = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/stores/connection', () => ({
  transport: { send: vi.fn() },
  leave: vi.fn(() => session.reset()),
}))

const options = { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } }
const registration = { room_id: 'r1', room_code: 'ABC234', member_id: 's1', token: 'test', ws_path: '/ws/rooms/ABC234' }

afterEach(() => session.reset())

describe('lobby connection states', () => {
  it.each(['connected', 'reconnecting'] as const)('stops the game and returns home while %s', async (status) => {
    session.setRegistration(registration)
    session.setStatus(status)
    session.apply(welcome as ServerMessage)
    const wrapper = mount(Lobby, options)
    const reset = wrapper.findAll('button').find((button) => button.text() === 'Return to main menu')!
    await reset.trigger('click')
    expect(transport.send).toHaveBeenCalledWith({ v: 1, type: 'match.reset', payload: {} })
    expect(leave).toHaveBeenCalled()
    expect(session.data.registration).toBeNull()
    expect(session.data.state).toBeNull()
    expect(push).toHaveBeenCalledWith('/')
    wrapper.unmount()
  })

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
    expect(wrapper.text()).toContain('0/4 ready · Match starts automatically when all 4 players are ready.')
    expect(wrapper.text()).not.toContain('Start match')
    expect(wrapper.text()).not.toContain('Waiting for the game server')
    wrapper.unmount()
  })
})
