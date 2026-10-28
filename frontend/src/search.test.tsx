import { fireEvent, render, screen } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { describe, expect, it, vi } from 'vitest'
import { emptyState, type DesktopState } from './types'
import { SearchWorkspace } from './components/Search'
import { act } from './bridge'

vi.mock('./bridge', () => ({ act: vi.fn().mockResolvedValue(true) }))
function search(search: Partial<DesktopState['search']>) {
  return render(<Tooltip.Provider><SearchWorkspace state={{ ...emptyState, search: { ...emptyState.search, query: 'example.com', ...search } }} query="example.com" setQuery={() => {}} onSource={() => {}}/></Tooltip.Provider>)
}
describe('real search explanations', () => {
  it('opens the existing Google operators constructor with the current draft', () => {
    search({})
    fireEvent.click(screen.getByRole('button', { name: 'Операторы Google' }))
    expect(act).toHaveBeenCalledWith('search_dorks', { query: 'example.com' })
  })
  it('shows Google browser fallback guidance instead of claiming no search results', () => {
    search({ phase: 'completed', status: 'Поиск Google открыт в браузере. Результаты доступны там: API не настроен.', checkedLabel: 'Проверено источников: 0' })
    expect(screen.getByRole('status')).toHaveTextContent('Поиск Google открыт в браузере')
    expect(screen.getByText('Проверено источников: 0')).toBeInTheDocument()
    expect(screen.queryByText('По этому запросу результатов нет')).toBeNull()
  })
  it('keeps a failed search visible as an error rather than an empty result', () => {
    search({ phase: 'failed', status: 'Поиск не завершён', error: 'Источник недоступен: истёк таймаут запроса.' })
    expect(screen.getByRole('alert')).toHaveTextContent('Источник недоступен: истёк таймаут запроса.')
    expect(screen.queryByText('По этому запросу результатов нет')).toBeNull()
    expect(screen.queryByText('Поиск не завершён')).toBeNull()
  })
  it('uses human progress labels and preserves the exact checked label during a run', () => {
    search({ phase: 'checking', busy: true, checked: 3, checkedLabel: 'Проверено: 3 из 12' })
    expect(screen.getByRole('status')).toHaveTextContent('Проверка источников')
    expect(screen.getByRole('status')).toHaveTextContent('Проверено: 3 из 12')
    expect(screen.queryByText('checking')).toBeNull()
  })
})
