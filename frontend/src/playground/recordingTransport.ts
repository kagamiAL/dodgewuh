// Development stand-in for Alan's Transport: always "connected", checks each outgoing message
// against the 03 rules a server would enforce, and hands it to the playground instead of a socket.

import type { Arms, ClientMessage, Transport, TransportStatus } from '@/contracts/pending'

export interface SentMessage {
  at: number
  message: ClientMessage
  /** Why a real server would reject it, or null. */
  problem: string | null
}

export function createRecordingTransport(onSend: (sent: SentMessage) => void): Transport {
  let seq = 0
  let lastSent = 0

  function check(m: ClientMessage): string | null {
    if (m.v !== 1) return 'wrong version'
    if (m.type === 'input.arms') return checkArms(m.payload)
    if (m.type !== 'input.legs') return null
    const { seq: s, epoch, move } = m.payload
    if (!Number.isSafeInteger(s) || s <= lastSent) return `seq ${s} not increasing`
    if (!Number.isSafeInteger(epoch) || epoch < 0) return 'bad epoch'
    if (!Number.isFinite(move.x) || !Number.isFinite(move.z)) return 'non-finite move'
    if (Math.abs(move.x) > 1 || Math.abs(move.z) > 1 || Math.hypot(move.x, move.z) > 1.001) return 'move out of range'
    lastSent = s
    return null
  }

  // 02/03: aim length in [0.99, 1.01]; strength in [0,1] only on release, null otherwise.
  // The team hemisphere check needs the sender's team, which the playground shows separately.
  function checkArms(p: Arms): string | null {
    if (!Number.isSafeInteger(p.seq) || p.seq <= lastSent) return `seq ${p.seq} not increasing`
    if (!Number.isSafeInteger(p.epoch) || p.epoch < 0) return 'bad epoch'
    if (!Number.isFinite(p.aim.x) || !Number.isFinite(p.aim.z)) return 'non-finite aim'
    const len = Math.hypot(p.aim.x, p.aim.z)
    if (len < 0.99 || len > 1.01) return `aim length ${len.toFixed(3)}`
    if (p.action === 'release') {
      if (p.strength === null || !Number.isFinite(p.strength) || p.strength < 0 || p.strength > 1) return 'release needs strength in [0,1]'
    } else if (p.strength !== null) return `${p.action} must have strength null`
    lastSent = p.seq
    return null
  }

  return {
    connect: () => Promise.resolve(),
    send(message) {
      onSend({ at: performance.now(), message, problem: check(message) })
    },
    subscribe: () => () => {},
    subscribeStatus(handler: (status: TransportStatus) => void) {
      handler('connected')
      return () => {}
    },
    nextInputSeq: () => ++seq,
    close: () => {},
  }
}
