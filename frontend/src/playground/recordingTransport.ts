// Development stand-in for Alan's Transport: always "connected", checks each outgoing message
// against the 03 rules a server would enforce, and hands it to the playground instead of a socket.

import type { ClientMessage, Transport, TransportStatus } from '@/contracts/pending'

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
    if (m.type !== 'input.legs') return null
    const { seq: s, epoch, move } = m.payload
    if (!Number.isSafeInteger(s) || s <= lastSent) return `seq ${s} not increasing`
    if (!Number.isSafeInteger(epoch) || epoch < 0) return 'bad epoch'
    if (!Number.isFinite(move.x) || !Number.isFinite(move.z)) return 'non-finite move'
    if (Math.abs(move.x) > 1 || Math.abs(move.z) > 1 || Math.hypot(move.x, move.z) > 1.001) return 'move out of range'
    lastSent = s
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
