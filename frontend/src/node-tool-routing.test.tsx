import {render,screen,waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {describe,it,expect,vi} from 'vitest'
import {ResearchCanvas} from './components/ResearchCanvas'
import {act} from './bridge'
import {emptyState,type GraphEntity,type ResearchDocument,type DesktopState} from './types'
import {cardBadge,cardVariant} from './graph-cards'
vi.mock('./bridge',()=>({act:vi.fn()}))
vi.mock('./useCanvasMutations',()=>({registerCanvasDraftProvider:vi.fn(),useCanvasMutations:(current?:{document?:{id:string;revision:number}})=>({pending:0,error:'',retry:vi.fn(),discard:vi.fn(),send:(op:string,payload={})=>act('research_canvas_'+op,{id:current?.document?.id,revision:current?.document?.revision,...payload}),edit:vi.fn().mockResolvedValue(true)})}))
vi.mock('./components/InvestigationCanvas',()=>({InvestigationCanvas:({nodes,onSelect}:{nodes:GraphEntity[];onSelect(id:string,multi:boolean):void})=><div>{nodes.map(node=><button key={node.id} onClick={()=>onSelect(node.id,false)}>Select {node.id}</button>)}</div>}))
const username:GraphEntity={id:'username',type:'username',label:'Моя подпись',attributes:{username:'solvnox',value:'solvnox'},evidence_ids:[]}
const wallet:GraphEntity={id:'wallet',type:'blockchain_address',label:'dsdsd',attributes:{address:'0:'+'a'.repeat(64),value:'0:'+'a'.repeat(64),chain:'ton'},evidence_ids:[]}
const document:ResearchDocument={id:'a'.repeat(32),schema:'granger-investigation/1',revision:1,title:'Routing',description:'',entities:[username,wallet],relations:[],evidence:[],annotations:{},custom_types:{},view:{positions:{username:{x:0,y:0},wallet:{x:400,y:0}},viewport:{x:0,y:0,scale:1},hidden:[],removed:[],collapsed:[],layout:'manual'}}
const tools:DesktopState['tools']=[{id:'username_maigret',name:'Maigret',available:true,state:'ready',description:'',inputTypes:['username'],manifest:{input_schema:{type:'object',properties:{username:{type:'string'},mode:{type:'string',enum:['quick','standard','full','custom']}},required:['username']}}},{id:'blockchain_gansar',name:'Gansar',available:true,state:'ready',description:'',inputTypes:['blockchain'],manifest:{input_schema:{type:'object',properties:{address:{type:'string'},chain:{type:'string',enum:['auto','ton']},operation:{type:'string',enum:['profile','balances']}},required:['address']}}},{id:'network_rdap',name:'RDAP',available:true,state:'ready',description:'',inputTypes:['ip']}]
describe('typed node tool selection',()=>{
 it('keeps configured tool parameters when presentation media finishes loading',async()=>{
  vi.mocked(act).mockImplementation(async(action)=>action==='research_canvas_capability'?{tools:[{id:'username_maigret',compatible:true,available:true,arguments:{username:'solvnox'}}]}:true)
  const user=userEvent.setup(),state={...emptyState,tools,research_canvas:{state:'ready',document,types:[],choices:[]}}
  const view=render(<ResearchCanvas active onSource={()=>{}} state={state}/>);await user.click(screen.getByRole('button',{name:'Select username'}));await user.click(screen.getByRole('button',{name:'Действия'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Инструмент узла'})).not.toBeDisabled())
  await user.click(screen.getByRole('button',{name:'Инструмент узла'}));await user.click(screen.getByRole('menuitemradio',{name:'Maigret'}))
  await user.click(screen.getByRole('button',{name:'Режим Maigret'}));await user.click(screen.getByRole('menuitemradio',{name:/Полный/}))
  view.rerender(<ResearchCanvas active onSource={()=>{}} state={{...state,research_canvas:{...state.research_canvas,document:{...document,revision:2,entities:[{...username,attributes:{...username.attributes,media:{state:'ready'}}},wallet]}}}}/>)
  expect(screen.getByRole('button',{name:'Инструмент узла'})).toHaveTextContent('Maigret');expect(screen.getByRole('button',{name:'Режим Maigret'})).toHaveTextContent('Полный')
 })
 it('refreshes a selected node capability after the runtime catalog becomes ready',async()=>{
  let available=false
  vi.mocked(act).mockImplementation(async(action)=>action==='research_canvas_capability'?{tools:[{id:'username_maigret',compatible:true,available,arguments:{username:'solvnox'}}]}:true)
  const user=userEvent.setup(),state={...emptyState,tools:tools.map(t=>({...t,available:false})),research_canvas:{state:'ready',document,types:[],choices:[]}}
  const view=render(<ResearchCanvas active onSource={()=>{}} state={state}/>);await user.click(screen.getByRole('button',{name:'Select username'}));await user.click(screen.getByRole('button',{name:'Действия'}))
  await waitFor(()=>expect(act).toHaveBeenCalledWith('research_canvas_capability',expect.anything()))
  available=true;view.rerender(<ResearchCanvas active onSource={()=>{}} state={{...state,tools}}/>)
  await waitFor(()=>expect(screen.getByRole('button',{name:'Инструмент узла'})).not.toBeDisabled())
  await user.click(screen.getByRole('button',{name:'Инструмент узла'}));await waitFor(()=>expect(screen.getByRole('menuitemradio',{name:'Maigret'})).not.toHaveAttribute('data-disabled'))
  await user.click(screen.getByRole('menuitemradio',{name:'Maigret'}));expect(screen.getByLabelText('Никнейм Maigret')).toHaveValue('solvnox')
 })
 it('keeps an identifier visually distinct from a public account',()=>{expect(cardVariant(username)).toBe('username');expect(cardBadge(username)).toBe('Никнейм');expect(cardBadge({...username,type:'public_profile'})).not.toBe('Никнейм')})
 it('selects Maigret and Gansar by actual menu clicks, resets stale tool and sends machine targets',async()=>{
  vi.mocked(act).mockImplementation(async(action,payload)=>{
   if(action!=='research_canvas_capability')return true
   const crypto=payload?.entity_id==='wallet'
   return {valid:crypto,chain:'ton',supported_operations:['profile','balances'],tools:[
    {id:'username_maigret',compatible:!crypto,arguments:{username:'solvnox'}},
    {id:'blockchain_gansar',compatible:crypto,arguments:{address:wallet.attributes.address,chain:'ton',operation:'profile'}},
    {id:'network_rdap',compatible:false}]}
  })
  const user=userEvent.setup()
  render(<ResearchCanvas active onSource={()=>{}} state={{...emptyState,tools,research_canvas:{state:'ready',document,types:[],choices:[]}}}/>)
  await user.click(screen.getByRole('button',{name:'Select username'}));await user.click(screen.getByRole('button',{name:'Действия'}))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Инструмент узла'})).not.toBeDisabled())
  expect(screen.getByRole('button',{name:'Выполнить → просмотр'})).toBeDisabled()
  await user.click(screen.getByRole('button',{name:'Инструмент узла'}));expect(screen.getByRole('menuitemradio',{name:'RDAP'})).toHaveAttribute('data-disabled')
  await user.click(screen.getByRole('menuitemradio',{name:'Maigret'}));expect(screen.getByLabelText('Никнейм Maigret')).toHaveValue('solvnox')
  await user.click(screen.getByRole('button',{name:'Выполнить → просмотр'}))
  expect(act).toHaveBeenCalledWith('research_canvas_tool',expect.objectContaining({tool:'username_maigret',entity_id:'username',arguments:{username:'solvnox'}}))
  await user.click(screen.getByRole('button',{name:'Select wallet'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Инструмент узла'})).toHaveTextContent('Выберите'))
  expect(screen.getByRole('button',{name:'Выполнить → просмотр'})).toBeDisabled()
  await user.click(screen.getByRole('button',{name:'Инструмент узла'}));await user.click(screen.getByRole('menuitemradio',{name:'Gansar'}))
  expect(screen.getByLabelText('Адрес кошелька или контракта')).toHaveValue(String(wallet.attributes.address))
  await user.click(screen.getByRole('button',{name:'Выполнить → просмотр'}))
  expect(act).toHaveBeenCalledWith('research_canvas_tool',expect.objectContaining({tool:'blockchain_gansar',entity_id:'wallet',query:wallet.attributes.address,arguments:{address:wallet.attributes.address,chain:'ton',operation:'profile'}}))
 })
})
