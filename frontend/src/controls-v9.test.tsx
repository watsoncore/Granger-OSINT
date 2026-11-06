import {useState} from 'react'
import {render,screen,waitFor,within} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {describe,it,expect,vi} from 'vitest'
import {Checkbox,Details,Select,Summary} from './components/ui'
import {ComboBox} from './components/ComboBox'
import {ResultsTable} from './components/ResultsTable'
import {applyAppearance,defaults} from './appearance'

describe('shared V9 controls',()=>{
  it('keeps accent checkmarks readable independently from the button foreground',()=>{
    applyAppearance({...defaults('azure'),colors:{accent:'#ffffff',button:'#000000'}},false)
    expect(document.documentElement.style.getPropertyValue('--user-accent-text')).toBe('#121820')
    expect(document.documentElement.style.getPropertyValue('--user-button-text')).toBe('#ffffff')
    applyAppearance(defaults('dark'),false)
  })
  it('chooses a filtered option with Enter and keeps disabled options inert',async()=>{
    const user=userEvent.setup(),change=vi.fn()
    render(<Select aria-label="Качество" value="auto" onValueChange={change}>
      <option value="auto">Автоматическое</option><option value="original">Оригинальное</option>
      <option disabled value="missing">Недоступное</option>
    </Select>)
    await user.click(screen.getByRole('button',{name:'Качество'}))
    const query=screen.getByRole('textbox',{name:'Найти: Качество'})
    await waitFor(()=>expect(query).toHaveFocus())
    await user.type(query,'Оригинальное')
    await user.keyboard('{Enter}')
    expect(change).toHaveBeenCalledWith('original')
    expect(screen.queryByRole('menuitemradio')).toBeNull()
  })
  it('retains mixed and read-only checkbox states without a mutation',async()=>{
    const user=userEvent.setup(),change=vi.fn()
    render(<Checkbox aria-label="Группа" checked={false} indeterminate readOnly onChange={change}/>)
    const checkbox=screen.getByRole('checkbox',{name:'Группа'})
    expect(checkbox).toBePartiallyChecked()
    await user.click(checkbox)
    expect(change).not.toHaveBeenCalled()
    expect(checkbox).toBePartiallyChecked()
  })
  it('uses an SVG disclosure while preserving native keyboard activation',async()=>{
    const user=userEvent.setup()
    render(<Details><Summary>Параметры</Summary><p>Содержимое</p></Details>)
    const summary=screen.getByText('Параметры').closest('summary')!
    expect(summary.querySelector('svg')).not.toBeNull()
    await user.click(summary)
    expect(summary.parentElement).toHaveAttribute('open')
  })
  it('supports editable model values and keyboard suggestions without a native datalist',async()=>{
    function Model(){
      const [value,setValue]=useState('')
      return <ComboBox label="Модель" value={value} onChange={setValue} options={['flash-a','flash-b']}/>
    }
    const user=userEvent.setup()
    const {container}=render(<Model/>)
    const input=screen.getByRole('combobox',{name:'Модель'})
    await user.type(input,'flash')
    await user.keyboard('{ArrowDown}{Enter}')
    expect(input).toHaveValue('flash-a')
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(container.querySelector('datalist')).toBeNull()
    await user.clear(input);await user.type(input,'своя-модель');await user.keyboard('{Escape}')
    expect(input).toHaveValue('своя-модель')
  })
  it('sorts result rows, shows mixed page selection and supports row keyboard actions',async()=>{
    const user=userEvent.setup(),toggle=vi.fn(),activate=vi.fn()
    render(<ResultsTable rows={[{id:'b',name:'Beta'},{id:'a',name:'Alpha'}]} rowId={row=>row.id}
      label="Наблюдения" columns={[{id:'name',label:'Название',value:row=>row.name}]}
      selected={new Set(['b'])} onToggle={toggle} onTogglePage={vi.fn()} onActivate={activate}/>)
    expect(screen.getByRole('checkbox',{name:'Выбрать страницу'})).toBePartiallyChecked()
    await user.click(screen.getByRole('button',{name:'Название'}))
    const table=screen.getByRole('table',{name:'Наблюдения'})
    const rows=within(table).getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('Alpha')
    rows[0].focus();await user.keyboard('{ArrowDown}{Enter}')
    expect(activate).toHaveBeenCalledWith({id:'b',name:'Beta'})
  })
})
