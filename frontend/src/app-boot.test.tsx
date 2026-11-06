import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { emptyState } from './types'
import { act,useDesktop } from './bridge'
import App from './App'

vi.mock('./bridge', () => ({ useDesktop: vi.fn(), act: vi.fn().mockResolvedValue(true), dismissNotice: vi.fn() }))
describe('desktop bootstrap', () => {
  beforeEach(() => vi.clearAllMocks())
  it('shows a neutral startup view and window controls before the first snapshot', () => {
    vi.mocked(useDesktop).mockReturnValue({ state: emptyState, connected: false, notice: '' })
    render(<App/>)
    expect(screen.getByRole('status')).toHaveTextContent('Подключение к приложению')
    expect(screen.getByRole('button', { name: 'Закрыть окно' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Свернуть окно' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Гермиона · Granger-OSINT' })).toHaveAttribute('src', './brand-hermione.png')
    expect(screen.queryByRole('navigation', { name: 'Основная навигация' })).toBeNull()
    expect(screen.queryByRole('textbox', { name: 'Сообщение Гермионе' })).toBeNull()
  })
  it('retains the honest standalone error instead of showing an interactive chat', () => {
    vi.mocked(useDesktop).mockReturnValue({ state: emptyState, connected: false, notice: 'Интерфейс открыт без настольного приложения. Инструменты и чат недоступны.' })
    render(<App/>)
    expect(screen.getByRole('status')).toHaveTextContent('Инструменты и чат недоступны')
    expect(screen.queryByRole('textbox', { name: 'Сообщение Гермионе' })).toBeNull()
  })
  it('leaves a handled menu Escape alone and exits fullscreen on the next unhandled Escape',()=>{
    vi.mocked(useDesktop).mockReturnValue({state:{...emptyState,window:{...emptyState.window,fullscreen:true}},connected:false,notice:''})
    render(<App/>)
    const handled=new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})
    handled.preventDefault();window.dispatchEvent(handled)
    expect(act).not.toHaveBeenCalledWith('window',{mode:'fullscreen'})
    window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))
    expect(act).toHaveBeenCalledWith('window',{mode:'fullscreen'})
  })
  it('gives a focused popup Escape priority even when its keyboard event is not cancelable',()=>{
    vi.mocked(useDesktop).mockReturnValue({state:{...emptyState,window:{...emptyState.window,fullscreen:true}},connected:false,notice:''})
    render(<><App/><div role="menu"><input aria-label="Фильтр меню"/></div></>)
    screen.getByLabelText('Фильтр меню').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:false}))
    expect(act).not.toHaveBeenCalledWith('window',{mode:'fullscreen'})
  })
  it('renders the actual launcher after its connected snapshot', () => {
    vi.mocked(useDesktop).mockReturnValue({ state: { ...emptyState, surface: 'launcher' }, connected: true, notice: '' })
    render(<App/>)
    expect(screen.getByRole('button', { name: 'Запустить Гермиону' })).toBeInTheDocument()
    expect(screen.getByRole('slider', { name: 'Размер Гермионы' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Сообщение Гермионе' })).toBeNull()
  })
})

vi.mock('./useCanvasMutations',()=>({registerCanvasDraftProvider:vi.fn(),useCanvasMutations:(current?:{document?:{id:string;revision:number}})=>({
  pending:0,error:'',retry:vi.fn(),discard:vi.fn(),
  send:(op:string,payload:Record<string,unknown>={})=>act('research_canvas_'+op,{id:current?.document?.id,revision:current?.document?.revision,...payload}),
  edit:(operation:string,args:Record<string,unknown>={})=>act('research_canvas_edit',{id:current?.document?.id,revision:current?.document?.revision,operation,arguments:args})
})}))
