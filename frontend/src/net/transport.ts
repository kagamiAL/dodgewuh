import type { ClientMessage, Registration, ServerMessage } from '../generated/protocol';
import { validateClientMessage, validateServerMessage } from '../generated/validators';
export type ConnectionStatus = 'connecting' | 'connected' | 'reconnecting' | 'closed';
export interface Transport {
  connect(registration: Registration): Promise<void>;
  send(message: ClientMessage): void;
  subscribe(handler: (message: ServerMessage) => void): () => void;
  subscribeStatus(handler: (status: ConnectionStatus) => void): () => void;
  nextInputSeq(): number;
  close(): void;
}

export class WebSocketTransport implements Transport {
  private socket?: WebSocket;
  private status: ConnectionStatus = 'closed';
  private messages = new Set<(message: ServerMessage) => void>();
  private statuses = new Set<(status: ConnectionStatus) => void>();
  private seq = 0;
  private generation = 0;
  private heartbeat?: ReturnType<typeof setInterval>;
  private retry?: ReturnType<typeof setTimeout>;
  private pendingReject?: (reason: Error) => void;
  private lastMessage = 0;
  private setStatus(status: ConnectionStatus) {
    this.status = status;
    this.statuses.forEach(handler => handler(status));
  }
  subscribe(handler: (message: ServerMessage) => void) {
    this.messages.add(handler); return () => { this.messages.delete(handler); };
  }
  subscribeStatus(handler: (status: ConnectionStatus) => void) {
    this.statuses.add(handler); handler(this.status);
    return () => { this.statuses.delete(handler); };
  }
  nextInputSeq() { return ++this.seq; }
  close() {
    ++this.generation;
    clearInterval(this.heartbeat); clearTimeout(this.retry);
    this.socket?.close(); this.socket = undefined;
    this.pendingReject?.(new Error('Transport closed')); this.pendingReject = undefined;
    this.setStatus('closed');
  }
  send(message: ClientMessage) {
    if (this.status !== 'connected' || this.socket?.readyState !== WebSocket.OPEN) return;
    this.socket.send(JSON.stringify(validateClientMessage(message)));
  }
  connect(registration: Registration): Promise<void> {
    this.close();
    const generation = this.generation;
    const url = new URL(registration.ws_path, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith('/ws/rooms/') || url.search || url.hash)
      return Promise.reject(new Error('Invalid WebSocket path'));
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return new Promise((resolve, reject) => {
      this.pendingReject = reject;
      let attempt = 0;
      let welcomed = false;
      const open = () => {
        if (generation !== this.generation) return;
        this.setStatus(attempt ? 'reconnecting' : 'connecting');
        const socket = new WebSocket(url);
        this.socket = socket;
        const deadline = setTimeout(() => socket.close(), 7000);
        socket.onopen = () => {
          if (generation !== this.generation || this.socket !== socket) { socket.close(); return; }
          socket.send(JSON.stringify({ v: 1, type: 'session.hello', payload: { token: registration.token } }));
        };
        socket.onmessage = event => {
          if (generation !== this.generation || this.socket !== socket) return;
          let message: ServerMessage;
          try { message = validateServerMessage(JSON.parse(event.data)); }
          catch { this.close(); return; }
          this.lastMessage = performance.now();
          if (message.type === 'session.welcome') {
            if (welcomed || message.payload.member_id !== registration.member_id) { this.close(); return; }
            clearTimeout(deadline); this.seq = 0; attempt = 0; welcomed = true;
            this.messages.forEach(handler => handler(message));
            if (generation !== this.generation) return;
            this.setStatus('connected'); this.pendingReject = undefined; resolve();
            clearInterval(this.heartbeat);
            this.heartbeat = setInterval(() => {
              if (performance.now() - this.lastMessage >= 15000) { socket.close(); return; }
              this.send({ v: 1, type: 'session.ping', payload: { nonce: Math.floor(performance.now()) } });
            }, 5000);
            return;
          }
          if (!welcomed) { this.close(); return; }
          this.messages.forEach(handler => handler(message));
          if (message.type === 'room.closed') this.close();
        };
        socket.onclose = event => {
          clearTimeout(deadline);
          if (generation !== this.generation || this.socket !== socket) return;
          clearInterval(this.heartbeat);
          welcomed = false;
          if ([4400, 4401, 4404, 4409, 4429].includes(event.code)) { this.close(); return; }
          this.setStatus('reconnecting');
          const delay = [500,1000,2000,4000,5000][Math.min(attempt++,4)];
          this.retry = setTimeout(open, delay * (.8 + Math.random() * .4));
        };
      };
      open();
    });
  }
}
