import {render,screen,fireEvent} from '@testing-library/react'
import {describe,it,expect,vi,beforeEach,afterEach} from 'vitest'
import {SteamInventory} from './components/SteamInventory'
import type {GraphEntity,SteamInventorySummary} from './types'

const summary:SteamInventorySummary={steamid64:'76561198045277210',appid:730,contextid:'2',observed_assets:1000,observed_units:1000,
  reported_total:1100,coverage_status:'partial',coverage_reason:'server_exhausted_before_reported_count',categories:{Pistol:1000},
  valuation:{currency:'USD',priced_assets:1,unpriced_assets:999,observed_subtotal_decimal:'0.11',method:'Только известные котировки'}}
const nodes:GraphEntity[]=Array.from({length:1000},(_,index)=>({id:'item_'+index,type:'inventory_item',label:'Synthetic skin '+index,
  evidence_ids:['ev_fixture_'+index],attributes:{steamid64:summary.steamid64,appid:730,contextid:'2',assetid:String(index+1),
    category:'Pistol',exterior:'Field-Tested',amount:'1',float_value:null,price:null,
    media:{id:'media_fixture_'+index,state:'unverified',url:'https://untrusted.invalid/raw.jpg'}}}))

describe('large public item inventory',()=>{
  beforeEach(()=>{
    vi.spyOn(HTMLElement.prototype,'offsetHeight','get').mockReturnValue(320)
    vi.spyOn(HTMLElement.prototype,'offsetWidth','get').mockReturnValue(800)
    vi.spyOn(HTMLElement.prototype,'clientHeight','get').mockReturnValue(320)
    vi.spyOn(HTMLElement.prototype,'clientWidth','get').mockReturnValue(800)
  })
  afterEach(()=>vi.restoreAllMocks())
  it('virtualizes the item table, preserves unknown prices and filters by actual item name',()=>{
    const open=vi.fn()
    render(<SteamInventory summaries={[summary]} nodes={nodes} onOpen={open} onMedia={()=>{}}/>)
    expect(screen.getByText(/1000 уникальных asset ID/)).toBeInTheDocument()
    expect(screen.getByText(/Источник завершил пагинацию/)).toBeInTheDocument()
    expect(screen.getAllByRole('row').length).toBeLessThan(60)
    expect(screen.getAllByText('Неизвестна').length).toBeGreaterThan(0)
    fireEvent.change(screen.getByLabelText('Поиск предмета'),{target:{value:'Synthetic skin 999'}})
    fireEvent.click(screen.getByRole('button',{name:'Synthetic skin 999'}))
    expect(open).toHaveBeenCalledWith('item_999')
  })
  it('never loads source URLs in renderer and fetches only through backend media requests',()=>{
    const media=vi.fn()
    render(<SteamInventory summaries={[summary]} nodes={nodes} onOpen={()=>{}} onMedia={media}/>)
    fireEvent.click(screen.getByRole('button',{name:'Галерея'}))
    expect(media).toHaveBeenCalledWith('item_0')
    expect(document.querySelector('img')).toBeNull()
  })
})
