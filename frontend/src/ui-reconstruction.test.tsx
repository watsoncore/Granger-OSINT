import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SourceInspector, isReadSource, sourceLabel } from './components/Sources'
import { SettingsWorkspace } from './components/Settings'
import { emptyState, type Source } from './types'
import { applyTheme, restoreTheme, themes } from './themes'
import { act } from './bridge'

vi.mock('./bridge', () => ({ act: vi.fn().mockResolvedValue(true) }))
const source = (id: string, values: Partial<Source> = {}): Source => ({ evidence_id: id, title: `Источник ${id}`, url: `https://example.org/${id}`, kind: 'page', status: 'unverified', ...values })

describe('truthful current task source inspector', () => {
  it('labels actual image metadata without claiming the photograph is authenticated or geolocated', () => {
    expect(sourceLabel(source('pixels',{kind:'image',status:'metadata'}))).toBe('Локальные данные изображения получены')
    expect(isReadSource(source('pixels',{kind:'image',status:'metadata'}))).toBe(false)
  })
  beforeEach(() => vi.clearAllMocks())
  it('does not confuse search snippets, shell pages, errors or discovered URLs with read content', () => {
    expect(isReadSource(source('1', { kind: 'snippet', status: 'read', details: { content_fetched: true } }))).toBe(false)
    expect(isReadSource(source('2', { status: 'success' }))).toBe(false)
    expect(isReadSource(source('3', { status: 'error', details: { content_fetched: true } }))).toBe(false)
    expect(isReadSource(source('empty', { status: 'read', details: { content_fetched: false } }))).toBe(false)
    expect(isReadSource(source('4', { status: 'read', details: { javascript_shell: true } }))).toBe(false)
    expect(sourceLabel(source('5', { status: 'read' }))).toBe('Содержимое получено')
  })
  it('filters actual statuses and searches current task records without losing failed records', () => {
    render(<Tooltip.Provider><SourceInspector sources={[source('read', { status: 'read', title: 'Полученная страница' }), source('error', { status: 'failed', title: 'Отказ сервера' }), source('snippet', { kind: 'snippet', status: 'indexed', title: 'Поисковый сниппет' })]} onSelect={() => {}}/></Tooltip.Provider>)
    fireEvent.click(screen.getByRole('button', { name: 'Прочитаны' }))
    expect(screen.getByRole('button', { name: 'Полученная страница' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Поисковый сниппет' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Ошибки' }))
    expect(screen.getByRole('button', { name: 'Отказ сервера' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Все' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Поиск по источникам задачи' }), { target: { value: 'Поисковый' } })
    expect(screen.getByRole('button', { name: 'Поисковый сниппет' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Отказ сервера' })).toBeNull()
  })
  it('opens the real source URL and exposes answer navigation only when a citation exists', () => {
    const onFocus = vi.fn()
    render(<Tooltip.Provider><SourceInspector sources={[source('1')]} onSelect={() => {}} onFocus={onFocus} canFocus={() => true}/></Tooltip.Provider>)
    fireEvent.click(screen.getByRole('button', { name: 'Открыть исходный URL' }))
    expect(act).toHaveBeenCalledWith('open_url', { url: 'https://example.org/1' })
    fireEvent.click(screen.getByRole('button', { name: 'К ответу с этим источником' }))
    expect(onFocus).toHaveBeenCalledWith(expect.objectContaining({ evidence_id: '1' }))
  })
  it('keeps hundreds of records while mounting a bounded viewport', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(300)
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(240)
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(142)
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(240)
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 0, y: 0, top: 0, left: 0, right: 240, bottom: 300, width: 240, height: 300, toJSON() {} })
    const sources = Array.from({ length: 500 }, (_, index) => source(String(index)))
    const { container } = render(<Tooltip.Provider><SourceInspector sources={sources} onSelect={() => {}}/></Tooltip.Provider>)
    await waitFor(() => expect(container.querySelectorAll('[data-source-id]').length).toBeGreaterThan(0))
    expect(container.querySelectorAll('[data-source-id]').length).toBeLessThan(30)
    expect(sources).toHaveLength(500)
  })
  afterEach(() => vi.restoreAllMocks())
})

describe('appearance and native vault controls', () => {
  it('restores all four saved themes without network access or page reload', () => {
    for (const theme of themes) {
      applyTheme(theme.id)
      expect(document.documentElement.dataset.theme).toBe(theme.id)
      document.documentElement.dataset.theme = 'dark'
      restoreTheme()
      expect(document.documentElement.dataset.theme).toBe(theme.id)
    }
    expect(applyTheme('unknown')).toBe('dark')
  })
  it('previews a chosen theme and saves it with the existing settings action', async () => {
    render(<Tooltip.Provider><SettingsWorkspace state={{ ...emptyState, settings: { ui_theme: 'dark' } }} category="interface"/></Tooltip.Provider>)
    fireEvent.click(screen.getByRole('button', { name: 'Тема: Белая' }))
    expect(document.documentElement.dataset.theme).toBe('light')
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(act).toHaveBeenCalledWith('settings_save', { values: { ui_theme: 'light' } }))
  })
  it('opens a native vault dialog without a password input in React', () => {
    render(<Tooltip.Provider><SettingsWorkspace state={emptyState} category="privacy"/></Tooltip.Provider>)
    fireEvent.click(screen.getByRole('button', { name: 'Создать vault и перенести данные' }))
    expect(act).toHaveBeenCalledWith('vault_manage', { operation: 'create' })
    expect(screen.queryByRole('textbox')).toBeNull()
  })
})
