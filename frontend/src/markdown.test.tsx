import { fireEvent, render, screen } from '@testing-library/react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { describe, expect, it, vi } from 'vitest'
import { Markdown, safeUrl } from './components/Markdown'
import { documentHeadings } from './components/Canvas'
import { sourceLabel } from './components/Sources'
import type { Source } from './types'

vi.mock('./bridge', () => ({ act: vi.fn().mockResolvedValue(true) }))
function markdown(text: string) { return render(<Tooltip.Provider><Markdown text={text}/></Tooltip.Provider>) }
describe('safe Markdown', () => {
  it('renders actual semantic headings, nested lists, emphasis, quotes and GFM tables', () => {
    const { container } = markdown('# Вывод\n\n**Подтверждено** и *проверено*.\n\n- Список\n  - Вложенный\n\n> Источник\n\n---\n\n| Имя | Статус |\n| --- | --- |\n| Пример | прочитан |')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Вывод')
    expect(container.querySelector('strong')).toHaveTextContent('Подтверждено')
    expect(container.querySelector('em')).toHaveTextContent('проверено')
    expect(container.querySelector('ul ul li')).toHaveTextContent('Вложенный')
    expect(container.querySelector('blockquote')).toHaveTextContent('Источник')
    expect(container.querySelector('hr')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Таблица' })).toHaveClass('table-scroll')
    expect(screen.getByRole('table')).toBeInTheDocument()
  })
  it('never creates HTML, scripts, remote images or active unsafe links', () => {
    const { container } = markdown('<script>window.alert(1)</script>\n\n<img src="https://tracker.test/pixel">\n\n[Небезопасно](javascript:alert%281%29)\n\n[Файл](file:///C:/secret.txt)\n\n![Фото](https://tracker.test/photo)\n\n[Безопасно](https://example.com/a)')
    expect(container.querySelector('script,img,iframe,object')).toBeNull()
    expect(container.querySelectorAll('a')).toHaveLength(1)
    expect(screen.getByRole('link')).toHaveAttribute('href', 'https://example.com/a')
  })
  it('does not navigate local content when a public link is activated', async () => {
    const { act } = await import('./bridge')
    markdown('[Открыть](https://example.com/проверка)')
    fireEvent.click(screen.getByRole('link'))
    expect(act).toHaveBeenCalledWith('open_url', { url: 'https://example.com/%D0%BF%D1%80%D0%BE%D0%B2%D0%B5%D1%80%D0%BA%D0%B0' })
  })
  it('supports an unfinished streaming code fence and copying its exact UTF8 content', async () => {
    const { act } = await import('./bridge')
    markdown('```python\nprint("Гермиона")\n')
    expect(screen.getByText('print("Гермиона")')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Копировать код' }))
    expect(act).toHaveBeenCalledWith('copy', { text: 'print("Гермиона")' })
  })
  it.each(['javascript:alert(1)', 'file:///C:/key', 'data:text/html,hello', 'http://user:secret@example.com', '//example.com', '/local/file', 'https://bad.test\u0000/'])('rejects unsafe URL %s', value => {
    expect(safeUrl(value)).toBe('')
  })
  it('allows only local evidence anchors and public http(s)', () => {
    expect(safeUrl('#ev_ab123')).toBe('#ev_ab123')
    expect(safeUrl('#unknown')).toBe('')
    expect(safeUrl('https://example.com')).toBe('https://example.com/')
  })
})
describe('documents and source provenance', () => {
  it('excludes fenced code from document navigation', () => {
    expect(documentHeadings('# Документ\n\n```md\n## Код\n```\n\n## Вывод')).toEqual([{ level: 1, text: 'Документ' }, { level: 2, text: 'Вывод' }])
  })
  it('never labels a search snippet as a read page', () => {
    const snippet = { evidence_id: 'ev_1', title: 'Сниппет', url: 'https://example.com', kind: 'snippet', status: 'success' } as Source
    expect(sourceLabel(snippet)).toBe('Поисковый сниппет')
    expect(sourceLabel({ ...snippet, kind: 'page', status: 'blocked' })).toBe('Доступ ограничен')
  })
})
