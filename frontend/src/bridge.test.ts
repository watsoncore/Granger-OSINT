import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('QWebChannel bridge', () => {
  beforeEach(() => { vi.resetModules(); delete window.qt; delete window.QWebChannel })
  afterEach(() => { vi.useRealTimers() })
  it('cannot silently succeed when opened outside the desktop application', async () => {
    const { request } = await import('./bridge')
    await expect(request('chat_send', { text: 'Тест' })).rejects.toThrow('Нет связи')
  })
  it('dispatches real actions and preserves a successful null backend result', async () => {
    let reply: ((id: string, json: string) => void) | undefined
    const sent: { action: string; payload: unknown }[] = []
    window.qt = { webChannelTransport: {} }
    window.QWebChannel = class {
      constructor(_transport: unknown, callback: (channel: never) => void) {
        callback({ objects: { desktop: {
          request(id: string, action: string, raw: string) { sent.push({ action, payload: JSON.parse(raw) }); queueMicrotask(() => reply?.(id, JSON.stringify({ ok: true, result: action === 'snapshot' ? {} : null }))) },
          response: { connect(handler: typeof reply) { reply = handler } }, stateChanged: { connect() {} },
        } } } as never)
      }
    }
    const { connectDesktop, act } = await import('./bridge')
    connectDesktop()
    expect(await act('chat_send', { text: 'Русский текст' })).toBe(true)
    expect(sent.at(-1)).toEqual({ action: 'chat_send', payload: { text: 'Русский текст' } })
  })
  it('propagates an explicit backend error without claiming a successful result', async () => {
    let reply: ((id: string, json: string) => void) | undefined
    window.qt = { webChannelTransport: {} }
    window.QWebChannel = class {
      constructor(_transport: unknown, callback: (channel: never) => void) {
        callback({ objects: { desktop: { request(id: string, action: string) { queueMicrotask(() => reply?.(id, JSON.stringify(action === 'snapshot' ? { ok: true, result: {} } : { ok: false, error: 'Инструмент недоступен' }))) }, response: { connect(handler: typeof reply) { reply = handler } }, stateChanged: { connect() {} } } } } as never)
      }
    }
    const { connectDesktop, request } = await import('./bridge')
    connectDesktop()
    await expect(request('tool_run', { tool: 'unavailable' })).rejects.toThrow('Инструмент недоступен')
  })
  it.each([
    { action: 'canvas_export', outcome: 'saved', response: { ok: true, result: { exported: true, filename: 'Исследование.md' } }, expected: { exported: true, filename: 'Исследование.md' } },
    { action: 'canvas_export', outcome: 'cancelled', response: { ok: true, result: { exported: false, filename: null } }, expected: { exported: false, filename: null } },
    { action: 'tool_run', outcome: 'approved', response: { ok: true, result: null }, expected: true },
    { action: 'tool_run', outcome: 'cancelled', response: { ok: false, error: 'Действие не подтверждено.' }, expected: null },
  ])('waits beyond 30 seconds for native dialog: $action / $outcome', async ({ action: requestedAction, response, expected }) => {
    vi.useFakeTimers()
    let reply: ((id: string, json: string) => void) | undefined
    let dialogId = ''
    window.qt = { webChannelTransport: {} }
    window.QWebChannel = class {
      constructor(_transport: unknown, callback: (channel: never) => void) {
        callback({ objects: { desktop: {
          request(id: string, action: string) {
            if (action === 'snapshot') reply?.(id, JSON.stringify({ ok: true, result: {} }))
            else if (action === requestedAction) dialogId = id
          },
          response: { connect(handler: typeof reply) { reply = handler } }, stateChanged: { connect() {} },
        } } } as never)
      }
    }
    const { connectDesktop, act } = await import('./bridge')
    connectDesktop()
    const settled = vi.fn()
    const waitingForDialog = act(requestedAction).then(value => { settled(value); return value })
    await vi.advanceTimersByTimeAsync(65000)
    expect(dialogId).not.toBe('')
    expect(settled).not.toHaveBeenCalled()
    reply?.(dialogId, JSON.stringify(response))
    expect(await waitingForDialog).toEqual(expected)
    expect(settled).toHaveBeenCalledExactlyOnceWith(expected)
  })
  it('keeps the 30 second timeout for actions without a native user dialog', async () => {
    vi.useFakeTimers()
    let reply: ((id: string, json: string) => void) | undefined
    window.qt = { webChannelTransport: {} }
    window.QWebChannel = class {
      constructor(_transport: unknown, callback: (channel: never) => void) {
        callback({ objects: { desktop: {
          request(id: string, action: string) { if (action === 'snapshot') reply?.(id, JSON.stringify({ ok: true, result: {} })) },
          response: { connect(handler: typeof reply) { reply = handler } }, stateChanged: { connect() {} },
        } } } as never)
      }
    }
    const { connectDesktop, request } = await import('./bridge')
    connectDesktop()
    const rejected = vi.fn()
    const waiting = request('chat_send', { text: 'Проверка' }).catch(error => { rejected(error.message); return error.message })
    await vi.advanceTimersByTimeAsync(29999)
    expect(rejected).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(await waiting).toBe('Приложение не ответило. Повторите действие.')
    expect(rejected).toHaveBeenCalledOnce()
  })
})
