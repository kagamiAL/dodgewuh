// The one live Transport for this tab, plus REST registration.
// Every server message goes through session.apply(), the same entry point the mocks use.

import { WebSocketTransport } from '@/net/transport'
import type { Device, Registration } from '@/contracts/pending'
import { session } from './session'

export const transport = new WebSocketTransport()
transport.subscribe((message) => session.apply(message))
transport.subscribeStatus((status) => session.setStatus(status))

export class RegistrationError extends Error {
  constructor(public code: string, message: string) {
    super(message)
  }
}

async function register(path: string, body: object): Promise<Registration> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await response.json().catch(() => null)
  if (response.status !== 201 || !data) {
    throw new RegistrationError(data?.code ?? 'SERVER_BUSY', data?.message ?? `Request failed (${response.status})`)
  }
  return data as Registration
}

/** Create a room; the creator is always the host screen (plans/01). */
export async function createRoom(name: string): Promise<Registration> {
  const registration = await register('/api/rooms', { name })
  session.setRegistration(registration)
  return registration
}

export async function joinRoom(code: string, name: string, device: Device): Promise<Registration> {
  const normalized = code.trim().toUpperCase()
  const registration = await register(`/api/rooms/${encodeURIComponent(normalized)}/members`, { name, device })
  session.setRegistration(registration)
  return registration
}

/** Connect with the stored registration. Resolves once the validated welcome arrived. */
export async function connect(): Promise<void> {
  const registration = session.data.registration
  if (!registration) throw new Error('Not registered')
  await transport.connect(registration)
}

export function leave(): void {
  transport.close()
  session.reset()
}
