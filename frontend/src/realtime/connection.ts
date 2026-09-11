import type { WebSocketMessage } from '@/types/dashboard'
import { WS_RECONNECT_INTERVAL } from '@/config/intervals'

/** Единственный владелец WebSocket-соединения на всё приложение. */

const CONNECT_TIMEOUT_MS = 10_000
const MAX_RECONNECT_DELAY_MS = 60_000
const READY_STATE_CONNECTING = 0
const READY_STATE_OPEN = 1

export type RealtimeStatus = 'connecting' | 'connected' | 'disconnected'

export interface RealtimeState {
  status: RealtimeStatus
  lastMessage: WebSocketMessage | null
}

/** Структурный минимум WebSocket: подменяется фейком в тестах. */
export interface RealtimeSocket {
  readyState: number
  onopen: (() => void) | null
  onmessage: ((event: { data: string }) => void) | null
  onclose: (() => void) | null
  onerror: (() => void) | null
  close(): void
}

export interface RealtimeDeps {
  url?: string
  createSocket?: (url: string) => RealtimeSocket
  setTimeout?: (handler: () => void, ms: number) => number
  clearTimeout?: (id: number) => void
}

function defaultSocketUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

export class RealtimeConnection {
  private readonly resolveUrl: () => string
  private readonly createSocket: (url: string) => RealtimeSocket
  private readonly schedule: (handler: () => void, ms: number) => number
  private readonly cancel: (id: number) => void

  private state: RealtimeState = { status: 'disconnected', lastMessage: null }
  private readonly stateListeners = new Set<() => void>()
  private socket: RealtimeSocket | null = null
  private consumers = 0
  private attempts = 0
  private reconnectTimer: number | null = null
  private connectTimer: number | null = null
  private messageHandler: ((message: WebSocketMessage) => void) | null = null

  constructor(deps: RealtimeDeps = {}) {
    const fixedUrl = deps.url
    this.resolveUrl = fixedUrl ? () => fixedUrl : defaultSocketUrl
    this.createSocket = deps.createSocket ?? ((url) => new WebSocket(url) as unknown as RealtimeSocket)
    this.schedule = deps.setTimeout ?? ((handler, ms) => window.setTimeout(handler, ms))
    this.cancel = deps.clearTimeout ?? ((id) => window.clearTimeout(id))
  }

  getState = (): RealtimeState => this.state

  subscribe = (listener: () => void): (() => void) => {
    this.stateListeners.add(listener)
    return () => {
      this.stateListeners.delete(listener)
    }
  }

  /** Подписчик канала: соединение живёт, пока жив хотя бы один потребитель. */
  acquire = (): (() => void) => {
    this.consumers += 1
    if (this.consumers === 1) this.connect()

    let released = false
    return () => {
      if (released) return
      released = true
      this.consumers -= 1
      if (this.consumers === 0) this.disconnect()
    }
  }

  setMessageHandler = (handler: ((message: WebSocketMessage) => void) | null): void => {
    this.messageHandler = handler
  }

  private connect(): void {
    if (this.socket && [READY_STATE_CONNECTING, READY_STATE_OPEN].includes(this.socket.readyState)) return

    this.setState({ status: 'connecting' })
    const socket = this.createSocket(this.resolveUrl())
    this.socket = socket
    this.connectTimer = this.schedule(() => socket.close(), CONNECT_TIMEOUT_MS)

    socket.onopen = () => {
      this.clearConnectTimer()
      this.attempts = 0
      this.setState({ status: 'connected' })
    }
    socket.onmessage = (event) => this.handleMessage(event.data)
    socket.onerror = () => socket.close()
    socket.onclose = () => {
      this.clearConnectTimer()
      if (this.socket === socket) this.socket = null
      this.setState({ status: 'disconnected' })
      if (this.consumers > 0) this.scheduleReconnect()
    }
  }

  /** Без потолка попыток: киоск обязан подняться сам после любого сетевого сбоя. */
  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) return

    const delay = Math.min(WS_RECONNECT_INTERVAL * 2 ** this.attempts, MAX_RECONNECT_DELAY_MS)
    this.attempts += 1
    this.reconnectTimer = this.schedule(() => {
      this.reconnectTimer = null
      if (this.consumers > 0) this.connect()
    }, delay)
  }

  private disconnect(): void {
    this.clearConnectTimer()
    if (this.reconnectTimer !== null) {
      this.cancel(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.attempts = 0

    const socket = this.socket
    this.socket = null
    socket?.close()
    this.setState({ status: 'disconnected' })
  }

  private handleMessage(data: string): void {
    let message: WebSocketMessage
    try {
      message = JSON.parse(data) as WebSocketMessage
    } catch {
      return
    }

    this.setState({ lastMessage: message })
    this.messageHandler?.(message)
  }

  private setState(next: Partial<RealtimeState>): void {
    const merged: RealtimeState = { ...this.state, ...next }
    if (merged.status === this.state.status && merged.lastMessage === this.state.lastMessage) return

    this.state = merged
    for (const listener of this.stateListeners) listener()
  }

  private clearConnectTimer(): void {
    if (this.connectTimer === null) return
    this.cancel(this.connectTimer)
    this.connectTimer = null
  }
}

export const realtime = new RealtimeConnection()
