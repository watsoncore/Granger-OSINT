import { fireEvent, render, screen, within } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AISettings, SourceSettings, balancePresentation } from './components/ConnectionSettings'
import { emptyState } from './types'
import { act } from './bridge'
import { ToolCatalog } from './components/ToolCatalog'
import { executionLabel, stateLabel } from './tool-presentation'

vi.mock('./bridge', () => ({ act: vi.fn().mockResolvedValue(true) }))
const common = { value: (_key: string, fallback: string | number | boolean = '') => fallback, set: vi.fn(), save: vi.fn().mockResolvedValue(true) }
describe('unified secure settings', () => {
  beforeEach(() => vi.clearAllMocks())
  it('opens a narrow VK credential dialog without rendering a token input', () => {
    render(<Tooltip.Provider><SourceSettings {...common} state={{ ...emptyState, credentials: { vk: false } }}/></Tooltip.Provider>)
    expect(screen.queryByLabelText(/токен/i)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Добавить' }))
    expect(act).toHaveBeenCalledWith('credentials_edit', { service: 'vk' })
    expect(screen.getByText(/отзовите его и выпустите новый/)).toBeInTheDocument()
  })
  it('keeps provider and model ordinary fields inside React and saves before checking', async () => {
    const value = (key: string, fallback: string | number | boolean = '') => key === 'ai_provider' ? 'deepseek' : fallback
    render(<Tooltip.Provider><AISettings {...common} value={value} state={emptyState}/></Tooltip.Provider>)
    expect(screen.getByRole('combobox')).toHaveValue('deepseek')
    expect(screen.getByRole('textbox', { name: 'Модель' })).toHaveValue('deepseek-v4-flash')
    expect(screen.queryByRole('button', { name: 'Обновить список моделей' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Проверить подключение' }))
    expect(common.save).toHaveBeenCalledOnce()
    await vi.waitFor(() => expect(act).toHaveBeenCalledWith('connection_test'))
  })
  it('requests Ollama model metadata without triggering a generation check', async () => {
    const value = (key: string, fallback: string | number | boolean = '') => key === 'ai_provider' ? 'ollama' : fallback
    render(<Tooltip.Provider><AISettings {...common} value={value} state={emptyState}/></Tooltip.Provider>)
    fireEvent.click(screen.getByRole('button', { name: 'Обновить список моделей' }))
    await vi.waitFor(() => expect(act).toHaveBeenCalledWith('connection_models'))
    expect(act).not.toHaveBeenCalledWith('connection_test')
  })
  it('shows actual model-list state without marking the chat connected', () => {
    const value = (key: string, fallback: string | number | boolean = '') => key === 'ai_provider' ? 'ollama' : fallback
    render(<Tooltip.Provider><AISettings {...common} value={value} state={{ ...emptyState, connection: { ...emptyState.connection, modelsChecking: true, modelsError: 'Не удалось получить список локальных моделей' } }}/></Tooltip.Provider>)
    expect(screen.getByRole('button', { name: 'Обновление моделей…' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось получить список локальных моделей')
    expect(screen.queryByText('Подключён')).toBeNull()
  })
  it('applies a chosen native tool path to the ordinary settings draft', async () => {
    vi.mocked(act).mockResolvedValueOnce({ path: 'C:/Tools' })
    render(<Tooltip.Provider><SourceSettings {...common} state={emptyState}/></Tooltip.Provider>)
    fireEvent.click(screen.getAllByRole('button', { name: 'Выбрать' })[0])
    await vi.waitFor(() => expect(common.set).toHaveBeenCalledWith('source_root', 'C:/Tools'))
  })
  it('does not call unknown token_balance values model tokens or credits', () => {
    const shown = balancePresentation({ status: 'available', amount: 1234, unit: 'unknown', field: 'token_balance' })
    expect(shown.unit).toBe('Единицы шлюза (token_balance)')
    expect(shown.unit).not.toContain('Токены')
    expect(shown.note).toContain('не пересчитываются')
  })
  it('keeps failed balance retrieval separate from a working chat connection', () => {
    render(<Tooltip.Provider><AISettings {...common} state={{ ...emptyState, connection: { ...emptyState.connection, status: 'connected', canSend: true }, usage: { balance: { status: 'error', error: 'Не удалось обновить баланс' } } }}/></Tooltip.Provider>)
    expect(screen.getByText('Подключён')).toBeInTheDocument()
    expect(screen.getByText('Не удалось обновить баланс')).toBeInTheDocument()
  })
  it('keeps the exact failure visible with a clearly stale previously received balance', () => {
    const shown = balancePresentation({ status: 'unavailable', amount: '1234', unit: 'gateway_units', stale: true, message: 'Остаток не получен.', error: 'Шлюз отклонил API-ключ.' })
    expect(shown.value).toBe('1234')
    expect(shown.note).toContain('Шлюз отклонил API-ключ.')
    expect(shown.note).toContain('Показан предыдущий остаток, он может быть устаревшим.')
  })
  it('shows the refresh spinner while the backend reports checking', () => {
    const value = (key: string, fallback: string | number | boolean = '') => key === 'ai_provider' ? 'deepseek' : fallback
    render(<Tooltip.Provider><AISettings {...common} value={value} state={{ ...emptyState, usage: { balance: { status: 'checking' } } }}/></Tooltip.Provider>)
    const button = screen.getByRole('button', { name: 'Обновить баланс' })
    expect(button).toBeDisabled()
    expect(button.querySelector('svg')).toHaveClass('spin')
  })
})
describe('real tool readiness presentation', () => {
  it('distinguishes configured credentials and local readiness from a verified external call', () => {
    expect(stateLabel('configured_unverified', true)).toBe('Настроен, доступ не проверен')
    expect(stateLabel('unverified', true)).toBe('Локально готов')
    expect(executionLabel('complete')).toBe('Завершено')
    expect(executionLabel('empty')).toBe('Совпадений нет')
    expect(executionLabel('timeout')).toBe('Превышено время ожидания')
    expect(executionLabel('error')).toBe('Ошибка выполнения')
  })
  it('shows the real last execution and readiness timestamp only in details', () => {
    render(<Tooltip.Provider><ToolCatalog tools={[{ id: 'web_read', name: 'web_read', description: 'Чтение', inputTypes: ['url'], available: true, state: 'unverified', diagnostic: { checked_at: '2026-10-28T12:00:00Z' }, last_execution: { status: 'empty', obtained_at: '2026-10-28T12:01:00Z', result_count: 0 } }]}/></Tooltip.Provider>)
    expect(screen.queryByText('Последнее выполнение')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Подробнее' }))
    expect(screen.getByText('Последнее выполнение')).toBeInTheDocument()
    expect(screen.getByText('Совпадений нет · Результатов: 0')).toBeInTheDocument()
    expect(screen.getByText(/Готовность проверена:/)).toBeInTheDocument()
  })
  it('shows a concrete problem and remedy while keeping unavailable tools inspectable', () => {
    render(<Tooltip.Provider><ToolCatalog tools={[{ id: 'username_maigret', name: 'username_maigret', description: 'Проверка никнейма', inputTypes: ['username'], available: false, state: 'missing_dependency', reason: 'Не найден Python-пакет maigret', diagnostic: { remedy: 'Укажите Python с установленным maigret.' } }]} onSelect={() => {}}/></Tooltip.Provider>)
    expect(screen.getByRole('heading', { name: 'Maigret' })).toBeInTheDocument()
    expect(screen.getByText('Нет зависимости')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Выбрать' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Что исправить' }))
    expect(screen.getByText('Не найден Python-пакет maigret')).toBeInTheDocument()
    expect(screen.getByText('Укажите Python с установленным maigret.')).toBeInTheDocument()
  })
  it('filters tools by actual readiness instead of manufacturing ready sources', () => {
    render(<Tooltip.Provider><ToolCatalog tools={[{ id: 'web_read', name: 'web_read', description: 'Чтение', inputTypes: ['url'], available: true, state: 'ready' }, { id: 'vk_public', name: 'vk_public', description: 'VK', inputTypes: ['vk'], available: false, state: 'auth_required' }]}/></Tooltip.Provider>)
    fireEvent.change(screen.getByRole('combobox', { name: 'Фильтр доступности' }), { target: { value: 'ready' } })
    expect(screen.getByRole('heading', { name: 'Чтение страницы' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'VK' })).toBeNull()
    expect(within(screen.getByRole('heading', { name: /Инструментарий/ })).getByText('1 локально готовы · 2 адаптеров')).toBeInTheDocument()
  })
})
