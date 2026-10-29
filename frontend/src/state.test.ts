import { describe, expect, it } from 'vitest'
import { emptyState, parseState } from './types'

describe('real backend state', () => {
  it('keeps unavailable usage, balance and tools honest', () => {
    const state = parseState({})
    expect(state.connection.balance).toBeNull()
    expect(state.connection.contextLimit).toBeNull()
    expect(state.messages).toHaveLength(0)
    expect(state.tools).toHaveLength(0)
    expect(state.connection.canSend).toBe(false)
  })
  it('merges streaming updates and preserves all unchanged message identities', () => {
    const initial = parseState({ ...emptyState, messages: [{ id: 'u1', role: 'user', text: 'Привет' }, { id: 'm1', role: 'model', text: 'Пр', streaming: true }] })
    const updated = parseState(JSON.stringify({ patch: true, message_count: 2, message_updates: [{ index: 1, message: { id: 'm1', role: 'model', text: 'Привет!', streaming: true } }], busy: true }), initial)
    expect(updated.messages).toHaveLength(2)
    expect(updated.messages[0]).toBe(initial.messages[0])
    expect(updated.messages[1].text).toBe('Привет!')
    expect(updated.busy).toBe(true)
  })
  it('appends exactly one streaming message and truncates only when instructed', () => {
    const previous = parseState({ messages: [{ id: 'u', role: 'user', text: 'Вопрос' }] })
    const next = parseState('{"message_updates":[{"index":1,"message":{"id":"m","role":"model","text":"Ответ"}}],"message_count":2}', previous)
    expect(next.messages.map(item => item.id)).toEqual(['u', 'm'])
    expect(parseState('{"message_count":0}', next).messages).toHaveLength(0)
  })
  it('does not lose history or context when a patch only changes window geometry', () => {
    const previous = parseState({ messages: [{ id: 'm', role: 'model', text: 'Контекст' }], history: [{ id: 'h', title: 'Исследование' }] })
    const next = parseState('{"window":{"fullscreen":true}}', previous)
    expect(next.messages).toBe(previous.messages)
    expect(next.history).toBe(previous.history)
    expect(next.window.fullscreen).toBe(true)
    expect(next.window.maximized).toBe(false)
  })
  it('preserves unchanged nested slice identities during a streaming patch', () => {
    const previous = parseState({ messages: [{ id: 'm', role: 'model', text: 'Начало', streaming: true }] })
    const next = parseState('{"message_updates":[{"index":0,"message":{"id":"m","role":"model","text":"Продолжение","streaming":true}}]}', previous)
    for (const key of ['connection', 'search', 'canvas', 'launcher', 'hermione', 'window', 'activity', 'history', 'evidence', 'tools'] as const) expect(next[key]).toBe(previous[key])
    expect(next.messages).not.toBe(previous.messages)
  })
})
