import {render,screen,waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {describe,it,expect,vi} from 'vitest'
import {SearchableSelect} from './components/SearchableSelect'
describe('themed searchable selector',()=>{
  it('filters options, excludes disabled selection, supports arrow focus and returns focus on escape',async()=>{
    const user=userEvent.setup(),change=vi.fn()
    render(<SearchableSelect label="Сеть" value="eth" options={[{value:'eth',label:'Ethereum',group:'EVM'},{value:'ton',label:'TON',group:'Другие сети'},{value:'blocked',label:'Недоступная',disabled:true}]} onChange={change}/>)
    const trigger=screen.getByRole('button',{name:'Сеть'});await user.click(trigger)
    const input=screen.getByRole('textbox',{name:'Найти: Сеть'});await waitFor(()=>expect(input).toHaveFocus());await user.type(input,'ton')
    expect(screen.queryByRole('menuitemradio',{name:'Ethereum'})).toBeNull();await user.keyboard('{ArrowDown}');expect(screen.getByRole('menuitemradio',{name:'TON'})).toHaveFocus();await user.keyboard('{Enter}')
    expect(change).toHaveBeenCalledWith('ton');await waitFor(()=>expect(trigger).toHaveFocus());await user.click(trigger);await user.keyboard('{Escape}');await waitFor(()=>expect(trigger).toHaveFocus())
  })
})
