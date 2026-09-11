import { afterEach, describe, expect, it } from 'vitest'
import { RealtimeConnection, type RealtimeSocket } from './connection'
import type { WebSocketMessage } from '@/types/dashboard'

class FakeSocket implements RealtimeSocket {
  static opened: FakeSocket[] = []

  readyState = 0
  closed = false
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(readonly url: string) {
    FakeSocket.opened.push(this)
  }

  close(): void {
    this.closed = true
    this.readyState = 3
  }

  serverOpen(): void {
    this.readyState = 1
    this.onopen?.()
  }

  serverSend(message: WebSocketMessage): void {
    this.onmessage?.({ data: JSON.stringify(message) })
  }

  serverDrop(): void {
    this.readyState = 3
    this.onclose?.()
  }
}

const lines = (message: WebSocketMessage): string => `${message.type}:${message.timestamp}`

interface TestClock {
  connection: RealtimeConnection
  lastDelay: () => number
  flushTimers: () => void
}

function makeConnection(): TestClock {
  const pending = new Map<number, () => void>()
  let nextId = 1
  let lastDelay = 0

  const connection = new RealtimeConnection({
    url: 'ws://test/ws',
    createSocket: (url) => new FakeSocket(url),
    setTimeout: (handler, ms) => {
      const id = nextId++
      pending.set(id, handler)
      lastDelay = ms
      return id
    },
    clearTimeout: (id) => {
      pending.delete(id)
    },
  })

  const flushTimers = () => {
    while (pending.size > 0) {
      const [id, handler] = pending.entries().next().value as [number, () => void]
      pending.delete(id)
      handler()
    }
  }

  return { connection, lastDelay: () => lastDelay, flushTimers }
}

function message(type: WebSocketMessage['type']): WebSocketMessage {
  return { type, payload: {}, timestamp: '2026-09-12T10:00:00Z' }
}

afterEach(() => {
  FakeSocket.opened = []
})

describe('RealtimeConnection', () => {
  it('держит одно соединение на всех потребителей', () => {
    const { connection } = makeConnection()
    const releaseFirst = connection.acquire()
    const releaseSecond = connection.acquire()

    expect(FakeSocket.opened).toHaveLength(1)
    expect(connection.getState().status).toBe('connecting')

    FakeSocket.opened[0].serverOpen()
    expect(connection.getState().status).toBe('connected')

    releaseFirst()
    releaseSecond()
  })

  it('отдаёт последнее сообщение подписчикам состояния', () => {
    const { connection } = makeConnection()
    const seen: string[] = []
    connection.subscribe(() => seen.push(connection.getState().status))
    const received: string[] = []
    connection.setMessageHandler((incoming) => received.push(lines(incoming)))

    const release = connection.acquire()
    FakeSocket.opened[0].serverOpen()
    FakeSocket.opened[0].serverSend(message('line_update'))

    expect(received).toEqual(['line_update:2026-09-12T10:00:00Z'])
    expect(connection.getState().lastMessage?.type).toBe('line_update')
    expect(seen).toEqual(['connecting', 'connected', 'connected'])

    release()
  })

  it('переподключается после разрыва с растущей, но ограниченной паузой', () => {
    const { connection, lastDelay, flushTimers } = makeConnection()
    const release = connection.acquire()
    FakeSocket.opened[0].serverOpen()

    const retryDelays: number[] = []
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const socket = FakeSocket.opened[FakeSocket.opened.length - 1]
      socket.serverDrop()
      retryDelays.push(lastDelay())
      flushTimers()
    }

    expect(FakeSocket.opened.length).toBe(7)
    expect(retryDelays.length).toBe(6)
    expect(retryDelays[0]).toBe(3000)
    expect(Math.max(...retryDelays)).toBe(60000)
    expect([...retryDelays].sort((a, b) => a - b)).toEqual(retryDelays)
    expect(connection.getState().status).toBe('connecting')

    release()
  })

  it('закрывает сокет и перестаёт переподключаться, когда уходит последний потребитель', () => {
    const { connection, flushTimers } = makeConnection()
    const release = connection.acquire()
    const socket = FakeSocket.opened[0]
    socket.serverOpen()

    release()
    flushTimers()

    expect(socket.closed).toBe(true)
    expect(FakeSocket.opened).toHaveLength(1)
    expect(connection.getState().status).toBe('disconnected')
  })
})
