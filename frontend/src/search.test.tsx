import { fireEvent, render, screen } from '@testing-library/react'
import {useState} from 'react'
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
  it('starts with the query editor open before the first result',()=>{
    search({query:'',results:[]})
    expect(screen.getByLabelText('Что исследуем?')).toBeVisible()
    expect(screen.queryByRole('button',{name:'Изменить запрос'})).toBeNull()
    expect(screen.getByRole('heading',{name:'Расследование'})).toBeVisible()
  })
  it('gives saved results the primary space while allowing edit, repeat and a new query',()=>{
    vi.mocked(act).mockClear()
    const state={...emptyState,search:{...emptyState.search,query:'example.org',results:[{title:'Сохранённый публичный документ',url:'https://example.org',status:'source_reported'}]}}
    function Harness(){const [query,setQuery]=useState('example.org');return <Tooltip.Provider><SearchWorkspace state={state} query={query} setQuery={setQuery} onSource={()=>{}}/></Tooltip.Provider>}
    render(<Harness/>)
    expect(screen.queryByRole('textbox',{name:'Что исследуем?'})).toBeNull()
    expect(screen.queryByRole('heading',{name:'Расследование'})).toBeNull()
    expect(screen.getByRole('button',{name:'Изменить запрос'})).toHaveAttribute('aria-expanded','false')
    fireEvent.click(screen.getByRole('button',{name:'Повторить поиск'}))
    expect(act).toHaveBeenCalledWith('search_run',{query:'example.org',kind:undefined})
    fireEvent.click(screen.getByRole('button',{name:'Изменить запрос'}))
    fireEvent.change(screen.getByLabelText('Что исследуем?'),{target:{value:'новый публичный запрос'}})
    fireEvent.click(screen.getByRole('button',{name:'Найти'}))
    expect(act).toHaveBeenCalledWith('search_run',{query:'новый публичный запрос',kind:undefined})
    expect(screen.queryByRole('textbox',{name:'Что исследуем?'})).toBeNull()
    expect(screen.getByRole('button',{name:/Поиск и результаты/})).toHaveAttribute('aria-pressed','true')
    fireEvent.click(screen.getByRole('button',{name:'Изменить запрос'}))
    expect(screen.getByLabelText('Что исследуем?')).toHaveValue('новый публичный запрос')
  })
  it('can reopen a saved-investigation query without changing the selected workspace',()=>{
    const state={...emptyState,search:{...emptyState.search,query:'saved.example',investigation_id:'saved'}}
    render(<Tooltip.Provider><SearchWorkspace state={state} query="" setQuery={()=>{}} onSource={()=>{}}/></Tooltip.Provider>)
    expect(screen.queryByRole('textbox',{name:'Что исследуем?'})).toBeNull()
    expect(screen.getByRole('button',{name:'Повторить поиск'})).toBeEnabled()
    fireEvent.click(screen.getByRole('button',{name:'Изменить запрос'}))
    expect(screen.getByLabelText('Что исследуем?')).toBeVisible()
    expect(screen.getByRole('button',{name:'Моё полотно'})).toHaveAttribute('aria-pressed','false')
  })
  it('opens the existing Google operators constructor with the current draft', () => {
    search({})
    fireEvent.click(screen.getByRole('button',{name:'Инструменты'}))
    fireEvent.click(screen.getByRole('button', { name: 'Операторы Google' }))
    expect(act).toHaveBeenCalledWith('search_dorks', { query: 'example.com' })
  })
  it('opens Avito only on an explicit user click and does not claim machine results', async () => {
    vi.mocked(act).mockResolvedValueOnce({ opened: true, url: 'https://www.avito.ru/all?q=example.com', machine_results: false })
    search({})
    fireEvent.click(screen.getByRole('button',{name:'Инструменты'}))
    fireEvent.click(screen.getByRole('button', { name: 'Искать на Avito' }))
    expect(act).toHaveBeenCalledWith('public_search_open', { source: 'avito', query: 'example.com' })
    expect(await screen.findByText(/Приложение не получало и не анализировало результаты/)).toBeInTheDocument()
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

vi.mock('./useCanvasMutations',()=>({registerCanvasDraftProvider:vi.fn(),useCanvasMutations:(current?:{document?:{id:string;revision:number}})=>({
  pending:0,error:'',retry:vi.fn(),discard:vi.fn(),
  send:(op:string,payload:Record<string,unknown>={})=>act('research_canvas_'+op,{id:current?.document?.id,revision:current?.document?.revision,...payload}),
  edit:(operation:string,args:Record<string,unknown>={})=>act('research_canvas_edit',{id:current?.document?.id,revision:current?.document?.revision,operation,arguments:args})
})}))
