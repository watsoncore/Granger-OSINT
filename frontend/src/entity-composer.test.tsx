import {render,screen,fireEvent,waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {describe,it,expect,vi} from 'vitest'
import {EntityComposer,type CompanyJurisdiction} from './components/EntityComposer'
vi.mock('./bridge',()=>({act:vi.fn()}))
const jurisdictions:CompanyJurisdiction[]=[{id:'KZ',label:'Казахстан',identifiers:{name:'Название',bin:'БИН',lei:'LEI'}},
  {id:'RU',label:'Россия',identifiers:{name:'Название',inn:'ИНН юридического лица',ogrn:'ОГРН'}}]

describe('typed object creation',()=>{
  it('shows jurisdiction-specific company fields without username or machine identifier',async()=>{
    const user=userEvent.setup(),create=vi.fn().mockResolvedValue(true)
    render(<EntityComposer jurisdictions={jurisdictions} onCreate={create}/>);
    await user.click(screen.getByRole('button',{name:'Тип нового узла'}))
    await user.click(screen.getByRole('menuitemradio',{name:'Компания / организация'}))
    expect(screen.queryByPlaceholderText(/Никнейм, URL/)).not.toBeInTheDocument()
    expect(screen.queryByText('Машинный идентификатор')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button',{name:'Способ поиска компании'}))
    await user.click(screen.getByRole('menuitemradio',{name:'БИН'}))
    fireEvent.change(screen.getByLabelText('БИН'),{target:{value:'123456789012'}})
    await user.click(screen.getByRole('button',{name:'Добавить объект'}))
    await waitFor(()=>expect(create).toHaveBeenCalledWith(expect.objectContaining({type:'organization',
      company:expect.objectContaining({jurisdiction:'KZ',identifier_type:'bin',identifier:'123456789012'})})))
  })
  it('retains typed values when durable saving is rejected',async()=>{
    const user=userEvent.setup()
    render(<EntityComposer onCreate={async()=>{throw new Error('Save rejected')}}/>);
    fireEvent.change(screen.getByLabelText('Имя или подпись'),{target:{value:'Сохранить этот черновик'}})
    await user.click(screen.getByRole('button',{name:'Добавить объект'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Save rejected')
    expect(screen.getByLabelText('Имя или подпись')).toHaveValue('Сохранить этот черновик')
  })
})
