import { render, screen } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Chat } from './components/Chat'
import { emptyState } from './types'
import { act } from './bridge'

vi.mock('./bridge', () => ({ act: vi.fn().mockResolvedValue(true) }))
let callback: IntersectionObserverCallback
const observe = vi.fn()
const disconnect = vi.fn()
const props = { draft: '', setDraft: vi.fn(), onSource: vi.fn(), onRoute: vi.fn() }
describe('unread acknowledgement from visible content', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    globalThis.CSS ??= {} as typeof CSS
    CSS.escape = value => value
    globalThis.IntersectionObserver = class {
      constructor(handler: IntersectionObserverCallback) { callback = handler }
      observe = observe
      disconnect = disconnect
      unobserve() {}
      takeRecords() { return [] }
      root = null
      rootMargin = ''
      thresholds = [0]
    }
  })
  it('acknowledges only completed model messages actually visible in the active chat', async () => {
    const state = { ...emptyState, conversation_id: 'conversation', window: { ...emptyState.window, active: true }, messages: [{ id: 'm1', role: 'model' as const, text: 'Готовый ответ' }, { id: 'm2', role: 'model' as const, text: 'Поток', streaming: true }, { id: 'u1', role: 'user' as const, text: 'Вопрос' }] }
    const { container } = render(<Tooltip.Provider><Chat {...props} state={state}/></Tooltip.Provider>)
    expect(observe).toHaveBeenCalledOnce()
    const target = container.querySelector('[data-message-id="m1"]')!
    callback([{ target, isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver)
    expect(act).not.toHaveBeenCalled()
    callback([{ target, isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
    await vi.waitFor(() => expect(act).toHaveBeenCalledWith('messages_seen', { conversation_id: 'conversation', message_ids: ['m1'] }))
    callback([{ target, isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
    expect(act).toHaveBeenCalledOnce()
  })
  it('does not mark messages read from an inactive native window', () => {
    render(<Tooltip.Provider><Chat {...props} state={{ ...emptyState, conversation_id: 'conversation', window: { ...emptyState.window, active: false }, messages: [{ id: 'm1', role: 'model', text: 'Ответ' }] }}/></Tooltip.Provider>)
    expect(observe).not.toHaveBeenCalled()
    expect(act).not.toHaveBeenCalled()
  })
  it('acknowledges a visible final error status and never observes user or streaming status messages', async () => {
    const state = { ...emptyState, conversation_id: 'conversation', window: { ...emptyState.window, active: true }, messages: [{ id: 'error-1', role: 'status' as const, text: 'Провайдер не ответил.' }, { id: 'status-stream', role: 'status' as const, text: 'Выполняется', streaming: true }, { id: 'user-1', role: 'user' as const, text: 'Вопрос' }] }
    const { container } = render(<Tooltip.Provider><Chat {...props} state={state}/></Tooltip.Provider>)
    const target = container.querySelector('[data-message-id="error-1"]')!
    expect(target).toHaveTextContent('Провайдер не ответил.')
    expect(observe).toHaveBeenCalledExactlyOnceWith(target)
    callback([{ target, isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
    await vi.waitFor(() => expect(act).toHaveBeenCalledWith('messages_seen', { conversation_id: 'conversation', message_ids: ['error-1'] }))
    expect(observe).not.toHaveBeenCalledWith(container.querySelector('[data-message-id="user-1"]'))
    expect(observe).not.toHaveBeenCalledWith(container.querySelector('[data-message-id="status-stream"]'))
  })
  it('keeps an archive failure visible separately from the working AI connection', () => {
    const state = { ...emptyState, archiveError: 'Не удалось сохранить историю. Диалог остаётся открыт.', connection: { ...emptyState.connection, canSend: true, status: 'connected' } }
    const { rerender } = render(<Tooltip.Provider><Chat {...props} state={state}/></Tooltip.Provider>)
    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось сохранить историю. Диалог остаётся открыт.')
    rerender(<Tooltip.Provider><Chat {...props} state={{ ...state, busy: true }}/></Tooltip.Provider>)
    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось сохранить историю.')
    expect(screen.getByRole('button', { name: 'Остановить ответ' })).toBeInTheDocument()
  })
})
