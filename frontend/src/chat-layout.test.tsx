import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Chat } from './components/Chat'
import { ToolCatalog } from './components/ToolCatalog'
import { Sources, SourceDialog } from './components/Sources'
import { act } from './bridge'
import { emptyState, type Source } from './types'

vi.mock('./bridge', () => ({ act: vi.fn().mockResolvedValue(true) }))
const props = { draft: '', setDraft: vi.fn(), onSource: vi.fn(), onRoute: vi.fn() }
const source = (index: number): Source => ({ evidence_id: `ev_${index}`, title: `Публичный источник ${index}`, url: `https://example.org/${index}`, kind: 'page', status: 'read' })

beforeEach(() => vi.clearAllMocks())
describe('chat composition and bounded inline evidence', () => {
  it('shares content wrappers without a permanent attachment-format row', () => {
    const { container } = render(<Tooltip.Provider><Chat {...props} state={emptyState}/></Tooltip.Provider>)
    expect(container.querySelector('.conversation.chat-content-width')).toBeInTheDocument()
    expect(container.querySelector('.composer-content.chat-content-width')).toBeInTheDocument()
    expect(container.querySelector('.composer .composer-tools button[aria-label="Выбрать изображение"]')).toBeInTheDocument()
    expect(container.querySelector('.attachment-actions small')).toBeNull()
    expect(screen.queryByText(/^JPEG, PNG, WebP/)).toBeNull()
  })

  it('keeps a hundred source records available without mounting a nested scrolling list', () => {
    const records = Array.from({ length: 120 }, (_, index) => source(index))
    const onSelect = vi.fn()
    const { container } = render(<Tooltip.Provider><Sources sources={records} onSelect={onSelect}/></Tooltip.Provider>)
    fireEvent.click(screen.getByRole('button', { name: /Источники/ }))
    expect(container.querySelectorAll('.source-card')).toHaveLength(6)
    expect(screen.getByText('1–6 из 120')).toBeInTheDocument()
    expect(container.querySelector('.sources-bounded')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Далее' }))
    expect(screen.getByText('7–12 из 120')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Публичный источник 6/ }))
    expect(onSelect).toHaveBeenCalledWith(records[6])
    fireEvent.click(screen.getByRole('button', { name: 'Назад' }))
    expect(screen.getByText('1–6 из 120')).toBeInTheDocument()
    expect(records).toHaveLength(120)
  })

  it('shows a compact paused task only for a real resumable state supplied by the backend', () => {
    const state = { ...emptyState, investigation: { id: 'checkpoint-id', canResume: true, stop_reason: 'Новые проверки не добавили данных.' } }
    const { container, rerender } = render(<Tooltip.Provider><Chat {...props} state={state}/></Tooltip.Provider>)
    expect(screen.getByRole('status', { name: 'Состояние исследования' })).toHaveTextContent('Исследование приостановлено')
    expect(container.querySelector('.resume-card.task-status')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }))
    expect(act).toHaveBeenCalledWith('investigation_continue')
    rerender(<Tooltip.Provider><Chat {...props} state={{ ...state, investigation: { ...state.investigation, canResume: false } }}/></Tooltip.Provider>)
    expect(screen.queryByRole('button', { name: 'Продолжить' })).toBeNull()
  })

  it('sends on Enter, retains Shift+Enter and IME composition, and restores input focus', async () => {
    const setDraft = vi.fn()
    const state = { ...emptyState, window: { ...emptyState.window, active: true }, connection: { ...emptyState.connection, canSend: true } }
    const { rerender } = render(<Tooltip.Provider><Chat {...props} draft="Публичный запрос" setDraft={setDraft} state={state}/></Tooltip.Provider>)
    const input = screen.getByRole('textbox', { name: 'Сообщение Гермионе' })
    input.focus()
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
    expect(act).not.toHaveBeenCalledWith('chat_send', expect.anything())
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(act).toHaveBeenCalledWith('chat_send', { text: 'Публичный запрос', attachment_ids: [] }))
    await waitFor(() => expect(setDraft).toHaveBeenCalledWith(''))
    await waitFor(() => expect(input).toHaveFocus())
    rerender(<Tooltip.Provider><Chat {...props} state={{ ...state, busy: true }}/></Tooltip.Provider>)
    rerender(<Tooltip.Provider><Chat {...props} state={state}/></Tooltip.Provider>)
    expect(input).toHaveFocus()
  })

  it('keeps a failed send draft and reports low OCR confidence as uncertainty', async () => {
    vi.mocked(act).mockResolvedValueOnce(false)
    const setDraft = vi.fn()
    render(<Tooltip.Provider><Chat {...props} draft="Сохранить черновик" setDraft={setDraft} state={{ ...emptyState, connection: { ...emptyState.connection, canSend: true } }}/></Tooltip.Provider>)
    fireEvent.click(screen.getByRole('button', { name: 'Отправить сообщение' }))
    await waitFor(() => expect(act).toHaveBeenCalledWith('chat_send', expect.anything()))
    expect(setDraft).not.toHaveBeenCalled()
    render(<Tooltip.Provider><SourceDialog source={{ ...source(1), kind: 'image', status: 'partial', details: { status: 'low_confidence', confidence: 0.35, segments: [{ text: 'НЕРАЗБОРЧИВО', confidence: 0.35, bbox: [0, 0, 5, 5] }] } }} onClose={() => {}}/></Tooltip.Provider>)
    expect(screen.getByText(/Низкая уверенность OCR/)).toBeInTheDocument()
    expect(screen.getByText('Средняя уверенность OCR: 35%')).toBeInTheDocument()
  })
})

describe('executable tool catalog', () => {
  it('never displays catalog-only candidates as working tools even if supplied by older backend state', () => {
    render(<Tooltip.Provider><ToolCatalog tools={[
      { id: 'web_read', name: 'web_read', description: 'Получение публичной страницы', inputTypes: ['url'], available: true, state: 'ready', implemented: true, manifest:{access_mode:'PERMITTED_HTTP',capabilities:['web_read']} },
      { id: 'candidate', name: 'Неинтегрированный сервис', description: 'Запись аудита', inputTypes: ['url'], available: false, state: 'catalog_only', implemented: false },
    ]}/></Tooltip.Provider>)
    expect(screen.getByRole('heading', { name: 'Чтение страницы' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Неинтегрированный сервис' })).toBeNull()
    expect(screen.getByText('1 локально готовы · 1 адаптеров')).toBeInTheDocument()
    expect(screen.getByText('HTML-парсер')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Подробнее'}))
    expect(screen.getByText('Поддерживаемые операции')).toBeInTheDocument()
  })
})
