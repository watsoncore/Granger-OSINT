import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest'
import {GraphAnalyticalIndex,GraphOverview} from './components/GraphAnalyticalIndex'
import {ResearchCanvas} from './components/ResearchCanvas'
import {emptyState,type GraphEntity,type GraphRelation,type ResearchDocument} from './types'

const hooks=vi.hoisted(()=>({edit:vi.fn(),center:vi.fn(),fit:vi.fn(),worker:vi.fn()}))
vi.mock('./bridge',()=>({act:vi.fn().mockResolvedValue(true)}))
vi.mock('./useCanvasMutations',()=>({registerCanvasDraftProvider:vi.fn(),useCanvasMutations:()=>({pending:0,error:'',retry:vi.fn(),discard:vi.fn(),send:vi.fn().mockResolvedValue(true),edit:hooks.edit})}))
vi.mock('./components/InvestigationCanvas',async()=>{
 const {forwardRef,useImperativeHandle}=await import('react')
 return {InvestigationCanvas:forwardRef(({nodes,root,selected}:{nodes:GraphEntity[];root:string;selected:string},ref)=>{
  useImperativeHandle(ref,()=>({center:hooks.center,fit:hooks.fit,zoom:vi.fn()}))
  return <div data-testid="analytical-renderer" data-root={root} data-selected={selected}>{nodes.map(node=><span key={node.id} data-node-id={node.id}>{node.label}</span>)}</div>
 })}
})

const identifier=(value:number)=>'ent_'+value.toString(16).padStart(24,'0')
const address=(value:number)=>'0:'+value.toString(16).padStart(64,'0')
const walletFixture=(count=120)=>{
 const root:GraphEntity={id:identifier(0),type:'blockchain_address',label:'Контрольный TON-кошелёк',attributes:{address:address(0),chain:'ton',transaction_count:count},evidence_ids:[],verification_status:'source_reported'}
 const peers:GraphEntity[]=Array.from({length:count},(_,index)=>({id:identifier(index+1),type:'blockchain_address',label:`Контрагент ${index+1}`,attributes:{address:address(index+1),chain:'ton'},evidence_ids:['ev_peer_'+index],verification_status:'source_reported'}))
 const edges:GraphRelation[]=peers.map((node,index)=>({id:'rel_'+index,from_id:index%2?root.id:node.id,to_id:index%2?node.id:root.id,relation_type:'transfers',direction:'directed',verification_status:'source_reported',evidence_ids:['ev_peer_'+index],source_urls:[`https://tonviewer.com/transaction/fixture-${index}`],aggregate:{count:1,amount:index===0?'0.000000001':String(index+1),asset:index%3?'TON':'USDT',asset_key:index%3?'ton|TON':'ton|USDT',known_amount_count:1,unknown_amount_count:0,first_seen:'2026-11-01T00:00:00Z',last_seen:'2026-11-03T00:00:00Z',transaction_ids:['ent_tx_'+index],owner_verified:false}}))
 return {root,peers,nodes:[root,...peers],edges}
}
const socialFixture=(count=120)=>{
 const root:GraphEntity={id:identifier(1000),type:'username',label:'solvnox',attributes:{username:'solvnox',value:'solvnox'},evidence_ids:[]}
 const profiles:GraphEntity[]=Array.from({length:count},(_,index)=>({id:identifier(2000+index),type:'public_profile',label:`solvnox · Site ${String(index+1).padStart(3,'0')}`,attributes:{platform:'Site '+String(index+1).padStart(3,'0'),username:'solvnox',url:`https://platform-${index+1}.example/solvnox`,owner_verified:false,identity_verified:false},evidence_ids:['ev_profile_'+index],verification_status:'source_reported'}))
 const technical:GraphEntity[]=profiles.flatMap((_,index)=>[{id:identifier(3000+index),type:'domain',label:`platform-${index+1}.example`,attributes:{technical:true},evidence_ids:[]},{id:identifier(4000+index),type:'username',label:'solvnox',attributes:{technical:true},evidence_ids:[]}])
 const edges:GraphRelation[]=profiles.map((node,index)=>({id:'rel_profile_'+index,from_id:root.id,to_id:node.id,relation_type:'returned_for_query',direction:'directed',verification_status:'source_reported',evidence_ids:['ev_profile_'+index],attributes:{owner_verified:false,identity_verified:false}}))
 return {root,profiles,nodes:[root,...profiles,...technical],edges}
}

beforeEach(()=>{
 hooks.edit.mockReset().mockResolvedValue({revision:11});hooks.center.mockReset();hooks.fit.mockReset();hooks.worker.mockReset()
 vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{callback(performance.now());return 1})
 vi.stubGlobal('Worker',class {constructor(){hooks.worker();throw new Error('Manual browsing must not create a layout worker')}})
})
afterEach(()=>vi.unstubAllGlobals())

describe('large analytical indexes use original IDs and complete identifiers',()=>{
 it('makes every one of 120 wallet counterparties reachable by paging and keeps complete address text/title',()=>{
  const fixture=walletFixture(),onWindow=vi.fn(),onSelect=vi.fn(),before=JSON.stringify(fixture)
  render(<GraphAnalyticalIndex {...fixture} root={fixture.root.id} social={false} selected="" onWindow={onWindow} onSelect={onSelect}/>)
  const index=screen.getByRole('navigation',{name:'Индекс контрагентов'}),seen=new Set<string>()
  for(let page=0;page<15;page++){
   const rows=within(index).getAllByRole('button',{name:/^Исследовать /})
   expect(rows).toHaveLength(8)
   for(const row of rows){const code=row.querySelector('code')!;expect(code.textContent).toMatch(/^0:[a-f0-9]{64}$/);expect(code.title).toBe(code.textContent);expect(code.textContent).not.toContain('…');seen.add(code.textContent!)}
   if(page<14)fireEvent.click(within(index).getByRole('button',{name:'Следующая страница объектов'}))
  }
  expect(seen).toEqual(new Set(fixture.peers.map(peer=>String(peer.attributes.address))))
  expect(within(index).getByRole('button',{name:'Следующая страница объектов'})).toBeDisabled()
  expect(onWindow.mock.calls.flatMap(call=>call[0])).not.toContain(fixture.root.id)
  expect(JSON.stringify(fixture)).toBe(before)
 })

 it('searches the complete address, selects its full stable entity ID, and filters actual flow directions',()=>{
  const fixture=walletFixture(),onWindow=vi.fn(),onSelect=vi.fn(),last=fixture.peers.at(-1)!
  render(<GraphAnalyticalIndex {...fixture} root={fixture.root.id} social={false} selected={last.id} onWindow={onWindow} onSelect={onSelect}/>)
  fireEvent.change(screen.getByRole('textbox',{name:'Поиск в аналитическом индексе'}),{target:{value:last.attributes.address}})
  expect(screen.getAllByRole('button',{name:/^Исследовать /})).toHaveLength(1)
  const selected=screen.getByRole('button',{name:'Исследовать '+last.attributes.address})
  expect(selected).toHaveClass('is-selected');fireEvent.click(selected)
  expect(onSelect).toHaveBeenLastCalledWith(last.id);expect(onWindow).toHaveBeenLastCalledWith([last.id])
  fireEvent.change(screen.getByRole('textbox',{name:'Поиск в аналитическом индексе'}),{target:{value:''}})
  fireEvent.click(screen.getByRole('button',{name:'Входящие'}))
  expect(screen.getByRole('button',{name:'Входящие'})).toHaveAttribute('aria-pressed','true')
  expect(screen.getByText('60 / 120')).toBeInTheDocument()
  expect(onWindow.mock.calls.at(-1)![0].every((id:string)=>fixture.edges.some(edge=>edge.from_id===id&&edge.to_id===fixture.root.id))).toBe(true)
  fireEvent.click(screen.getByRole('button',{name:'Исходящие'}))
  expect(onWindow.mock.calls.at(-1)![0].every((id:string)=>fixture.edges.some(edge=>edge.to_id===id&&edge.from_id===fixture.root.id))).toBe(true)
 })

 it('labels coverage and ownership conservatively and keeps tiny amounts nonzero',()=>{
  const fixture=walletFixture(),onIndex=vi.fn(),onCenter=vi.fn()
  render(<><GraphOverview {...fixture} root={fixture.root.id} social={false} partial onIndex={onIndex} onCenter={onCenter}/><GraphAnalyticalIndex {...fixture} root={fixture.root.id} social={false} selected="" onWindow={()=>{}} onSelect={()=>{}}/></>)
  expect(screen.getByText('Частичные данные')).toBeInTheDocument()
  expect(screen.getByText('Суммы по активам раздельно · владение не установлено')).toBeInTheDocument()
  expect(screen.getByRole('region',{name:'Аналитический обзор'})).toHaveTextContent('TON · USDT')
  expect(screen.getByRole('button',{name:'Исследовать '+fixture.peers[0].attributes.address})).toHaveTextContent('1e-9')
  fireEvent.click(screen.getByRole('button',{name:/120\s*контрагентов в данных/}));expect(onIndex).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button',{name:'К центру'}));expect(onCenter).toHaveBeenCalledOnce()
 })

 it('indexes all 120 found profiles without technical username/domain duplicates or a claimed common person',()=>{
  const fixture=socialFixture(),onWindow=vi.fn(),onSelect=vi.fn(),before=JSON.stringify(fixture)
  render(<><GraphOverview {...fixture} root={fixture.root.id} social partial onIndex={()=>{}} onCenter={()=>{}}/><GraphAnalyticalIndex {...fixture} root={fixture.root.id} social selected="" onWindow={onWindow} onSelect={onSelect}/></>)
  const index=screen.getByRole('navigation',{name:'Индекс публичных профилей'}),seen=new Set<string>()
  for(let page=0;page<15;page++){
   within(index).getAllByRole('button',{name:/^Исследовать /}).forEach(row=>seen.add(row.querySelector('code')!.textContent!))
   if(page<14)fireEvent.click(within(index).getByRole('button',{name:'Следующая страница объектов'}))
  }
  expect(seen).toEqual(new Set(fixture.profiles.map(profile=>String(profile.attributes.url))))
  expect(screen.getByText('Совпадение username не доказывает общего владельца')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'Входящие'})).not.toBeInTheDocument()
  const last=fixture.profiles.at(-1)!,url=String(last.attributes.url)
  fireEvent.change(screen.getByRole('textbox',{name:'Поиск в аналитическом индексе'}),{target:{value:url}})
  const row=within(index).getByRole('button',{name:'Исследовать '+url})
  expect(row.querySelector('code')).toHaveAttribute('title',url);fireEvent.click(row)
  expect(onSelect).toHaveBeenLastCalledWith(last.id);expect(onWindow).toHaveBeenLastCalledWith([last.id])
  fireEvent.change(screen.getByRole('textbox',{name:'Поиск в аналитическом индексе'}),{target:{value:'sItE 120'}})
  expect(within(index).getAllByRole('button',{name:/^Исследовать /})).toHaveLength(1)
  expect(within(index).getByRole('button',{name:'Исследовать '+url})).toBeInTheDocument()
  expect(JSON.stringify(fixture)).toBe(before)
 })

 it('resets index query, direction and page when the actual research root changes',()=>{
  const first=walletFixture(),second=walletFixture(12),onWindow=vi.fn()
  second.root={...second.root,id:identifier(9000),label:'Other root'};second.nodes=[second.root,...second.peers];second.edges=second.edges.map(edge=>({...edge,from_id:edge.from_id===first.root.id?second.root.id:edge.from_id,to_id:edge.to_id===first.root.id?second.root.id:edge.to_id}))
  const view=render(<GraphAnalyticalIndex {...first} root={first.root.id} social={false} selected="" onWindow={onWindow} onSelect={()=>{}}/>)
  fireEvent.click(screen.getByRole('button',{name:'Исходящие'}));fireEvent.click(screen.getByRole('button',{name:'Следующая страница объектов'}))
  fireEvent.change(screen.getByRole('textbox',{name:'Поиск в аналитическом индексе'}),{target:{value:'not-in-next-root'}})
  view.rerender(<GraphAnalyticalIndex {...second} root={second.root.id} social={false} selected="" onWindow={onWindow} onSelect={()=>{}}/>)
  expect(screen.getByRole('textbox',{name:'Поиск в аналитическом индексе'})).toHaveValue('')
  expect(screen.getByRole('button',{name:'Все'})).toHaveAttribute('aria-pressed','true');expect(screen.getByText('1 / 2')).toBeInTheDocument()
  expect(onWindow.mock.calls.at(-1)![0]).toHaveLength(8)
 })

 it.each(['manual','wallet'])('browses and selects index pages without writing positions in %s layout',async(layout)=>{
  const fixture=walletFixture(),manual=Object.fromEntries(fixture.nodes.map((node,index)=>[node.id,{x:index*301.5,y:(index%5)*177.25,pinned:true}]))
  const document:ResearchDocument={id:'f'.repeat(32),schema:'granger-investigation/1',revision:10,title:'Existing manually arranged investigation',description:'',entities:fixture.nodes,relations:fixture.edges,evidence:[],annotations:{},custom_types:{},view:{positions:manual,viewport:{x:-800,y:120,scale:.8},hidden:[],removed:[],collapsed:[],layout,manual_position_ids:fixture.nodes.map(node=>node.id),ui:{graph_mode:'wallet',crypto_root_id:fixture.root.id}}}
  const state={...emptyState,research_canvas:{state:'ready',document,types:[],choices:[]}},before=JSON.stringify(document)
  render(<ResearchCanvas state={state} onSource={()=>{}} active/>)
  fireEvent.click(screen.getByRole('button',{name:'Список объектов'}));await waitFor(()=>expect(screen.getByRole('navigation',{name:'Индекс контрагентов'})).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button',{name:'Следующая страница объектов'}))
  const peer=fixture.peers.at(-1)!
  fireEvent.change(screen.getByRole('textbox',{name:'Поиск в аналитическом индексе'}),{target:{value:peer.attributes.address}})
  fireEvent.click(screen.getByRole('button',{name:'Исследовать '+peer.attributes.address}))
  await waitFor(()=>expect(screen.getByTestId('analytical-renderer')).toHaveAttribute('data-selected',peer.id))
  expect(screen.getByTestId('analytical-renderer')).toHaveAttribute('data-root',fixture.root.id)
  expect(screen.getByTestId('analytical-renderer').querySelector(`[data-node-id="${fixture.root.id}"]`)).toBeInTheDocument()
  expect(hooks.center).toHaveBeenCalledWith(peer.id);expect(hooks.worker).not.toHaveBeenCalled()
  expect(hooks.edit.mock.calls.every(call=>!['layout','positions'].includes(call[0]))).toBe(true)
  fireEvent.click(screen.getByRole('button',{name:'Настроить граф'}));expect(screen.getByRole('button',{name:'Раскладка графа'})).toHaveTextContent(layout==='manual'?'Ручная':'Вокруг кошелька')
  expect(JSON.stringify(document)).toBe(before)
 })
})
