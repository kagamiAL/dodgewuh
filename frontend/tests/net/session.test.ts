import { afterEach, describe, expect, it } from 'vitest'
import { session } from '@/stores/session'
import type { ServerMessage } from '@/contracts/pending'
import welcome from '../../../contracts/fixtures/valid/welcome.json'

afterEach(() => session.reset())

describe('errors', () => {
  it('ignores stale gameplay input rejected after a phase change', () => {
    session.apply(welcome as ServerMessage)
    session.apply({ v: 1, type: 'error', server_ms: 0, payload: { code: 'INVALID_PHASE', message: 'gameplay input requires active', ref_seq: 42 } })
    session.apply({ v: 1, type: 'error', server_ms: 0, payload: { code: 'STALE_EPOCH', message: 'command carries a stale epoch', ref_seq: 43 } })
    expect(session.data.lastError).toBeNull()
  })

  it('still shows other errors and clears them on the next phase', () => {
    session.apply(welcome as ServerMessage)
    session.apply({ v: 1, type: 'error', server_ms: 0, payload: { code: 'FORBIDDEN', message: 'That team is full. Choose another team.', ref_seq: null } })
    expect(session.data.lastError?.code).toBe('FORBIDDEN')
    const st = session.data.state!
    session.apply({ v: 1, type: 'phase.changed', server_ms: 0, payload: { state: { ...st, epoch: st.epoch + 1 } } })
    expect(session.data.lastError).toBeNull()
  })
})

describe('roles.changed', () => {
  it('applies the new mapping immediately and clears stale errors', () => {
    session.apply(welcome as ServerMessage)
    const st = session.data.state!
    session.apply({ v: 1, type: 'error', server_ms: 0, payload: { code: 'STALE_ASSIGNMENT', message: 'Roles changed; recalibrate', ref_seq: null } })
    const assignments = [...st.assignments].reverse()
    session.apply({
      v: 1, type: 'roles.changed', server_ms: 0,
      payload: { assignments, assignment_version: st.assignment_version + 1, epoch: st.epoch },
    })
    expect(session.data.state!.assignment_version).toBe(st.assignment_version + 1)
    expect(session.data.state!.assignments).toEqual(assignments)
    expect(session.data.lastError).toBeNull()
  })

  it('ignores a mapping from another epoch or an older version', () => {
    session.apply(welcome as ServerMessage)
    const st = session.data.state!
    session.apply({ v: 1, type: 'roles.changed', server_ms: 0, payload: { assignments: [], assignment_version: st.assignment_version + 1, epoch: st.epoch - 1 } })
    session.apply({ v: 1, type: 'roles.changed', server_ms: 0, payload: { assignments: [], assignment_version: st.assignment_version, epoch: st.epoch } })
    expect(session.data.state).toEqual(st)
  })
})
