import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {describe,it,expect,vi} from 'vitest'
import {ResearchCanvas} from './components/ResearchCanvas'
import {emptyState,type ResearchDocument,type GraphEntity} from './types'
import {act} from './bridge'
import userEvent from '@testing-library/user-event'
vi.mock('./bridge',()=>({act:vi.fn().mockResolvedValue(true)}))
vi.mock('./components/InvestigationCanvas',()=>({InvestigationCanvas:({nodes,onSelect}:{nodes:GraphEntity[];onSelect(id:string,multi:boolean):void})=> <div data-testid="renderer">{nodes.map(n=><button key={n.id} onClick={()=>onSelect(n.id,false)}>Select {n.id}</button>)}</div>}))

const document:ResearchDocument={schema:'granger-investigation/1',id:'a'.repeat(32),revision:4,title:'Мой проект',description:'',entities:[],relations:[],evidence:[],annotations:{},custom_types:{},view:{positions:{},viewport:{x:0,y:0,scale:1},layout:'manual',hidden:[],removed:[],collapsed:[]}}
describe('Search analyst canvas controls',()=>{
  it('retains the separate automatic Search and requires explicit insertion from a partial preview',()=>{
    const state={...emptyState,research_canvas:{state:'ready',types:['analyst_note','domain'],choices:[],document,preview:{token:'receipt-token',canvas_id:document.id,node_id:'',tool:'network_rdap',status:'partial',limitations:['source timeout'],results:[{evidence_id:'ev_'+'a'.repeat(20),title:'Retained partial record',url:'https://example.org',status:'source_reported',kind:'adapter' as const}]}}}
    render(<ResearchCanvas state={state} onSource={()=>{}}/>);fireEvent.click(screen.getByRole('button',{name:'Мои расследования'}))
    expect(screen.getByText('source timeout')).toBeInTheDocument();expect(vi.mocked(act).mock.calls.some(c=>c[0]==='research_canvas_insert')).toBe(false)
    fireEvent.click(screen.getByRole('button',{name:'Добавить выбранные (1)'}))
    expect(act).toHaveBeenCalledWith('research_canvas_insert',{id:document.id,revision:4,token:'receipt-token',evidence_ids:['ev_'+'a'.repeat(20)]})
  })
  it('sends a Russian manual note as an analyst node rather than fabricated evidence',()=>{
    render(<ResearchCanvas state={{...emptyState,research_canvas:{state:'ready',types:['analyst_note'],choices:[],document}}} onSource={()=>{}}/>);
    fireEvent.click(screen.getByRole('button',{name:'Мои расследования'}));fireEvent.change(screen.getByLabelText('Заметка узла'),{target:{value:'**Гипотеза** — требует проверки'}})
    fireEvent.click(screen.getByRole('button',{name:'Сохранить заметку'}))
    expect(act).toHaveBeenCalledWith('research_canvas_edit',expect.objectContaining({operation:'node',arguments:expect.objectContaining({type:'analyst_note',markdown:'**Гипотеза** — требует проверки'})}))
  })
  it('runs a string tool on the canonical value after a user changes the visible label',async()=>{
    const user=userEvent.setup()
    vi.mocked(act).mockImplementation(async(action)=>action==='research_canvas_capability'?{tools:[{id:'network_rdap',compatible:true,arguments:{target:'66.249.67.41'}}]}:true)
    const id='ent_'+'b'.repeat(24),doc={...document,entities:[{id,type:'infrastructure_asset',label:'Исследуемый сервер',attributes:{value:'66.249.67.41'},evidence_ids:[]}],view:{...document.view,positions:{[id]:{x:0,y:0}}}}
    render(<ResearchCanvas state={{...emptyState,tools:[{id:'network_rdap',name:'RDAP',available:true,description:'Registry lookup',inputTypes:['ip'],state:'ready'}],research_canvas:{state:'ready',types:[],choices:[],document:doc}}} onSource={()=>{}}/>)
    fireEvent.click(screen.getByRole('button',{name:'Мои расследования'}));fireEvent.click(screen.getByRole('button',{name:'Select '+id}))
    fireEvent.change(screen.getByLabelText('Название узла'),{target:{value:'Моя аннотация'}})
    fireEvent.click(screen.getByRole('button',{name:'Действия'}))
    await waitFor(()=>expect(screen.getByRole('button',{name:'Инструмент узла'})).not.toBeDisabled())
    await user.click(screen.getByRole('button',{name:'Инструмент узла'}));await user.click(screen.getByRole('menuitemradio',{name:/RDAP/}))
    fireEvent.click(screen.getByRole('button',{name:'Выполнить → просмотр'}))
    expect(act).toHaveBeenCalledWith('research_canvas_tool',expect.objectContaining({entity_id:id,query:'66.249.67.41',tool:'network_rdap'}))
  })
  it('retains unsaved note drafts across revisions and switching the selected node',()=>{
    const nodes:GraphEntity[]=['first','second'].map(id=>({id,type:'analyst_note',label:id,attributes:{},evidence_ids:[]})),doc={...document,id:'d'.repeat(32),entities:nodes},state={...emptyState,research_canvas:{state:'ready',types:[],choices:[],document:doc}}
    const view=render(<ResearchCanvas state={state} onSource={()=>{}} active/>);fireEvent.click(screen.getByRole('button',{name:'Select first'}))
    fireEvent.change(screen.getByLabelText('Заметка узла'),{target:{value:'Несохранённая русская гипотеза'}})
    view.rerender(<ResearchCanvas state={{...state,research_canvas:{...state.research_canvas,document:{...doc,revision:5}}}} onSource={()=>{}} active/>)
    expect(screen.getByLabelText('Заметка узла')).toHaveValue('Несохранённая русская гипотеза')
    fireEvent.click(screen.getByRole('button',{name:'Select second'}));fireEvent.change(screen.getByLabelText('Заметка узла'),{target:{value:'Вторая заметка'}});fireEvent.click(screen.getByRole('button',{name:'Select first'}))
    expect(screen.getByLabelText('Заметка узла')).toHaveValue('Несохранённая русская гипотеза')
  })
  it('keeps a mixed manual project visible when a wallet is not the investigation root',()=>{
    const nodes:GraphEntity[]=[{id:'manualroot',type:'analyst_note',label:'Мой план',attributes:{},evidence_ids:[]},{id:'wallet',type:'blockchain_address',label:'TON wallet',attributes:{chain:'ton'},evidence_ids:[]},{id:'domain',type:'domain',label:'example.org',attributes:{},evidence_ids:[]}],doc={...document,id:'e'.repeat(32),entities:nodes}
    render(<ResearchCanvas state={{...emptyState,research_canvas:{state:'ready',types:[],choices:[],document:doc}}} onSource={()=>{}} active/>)
    expect(screen.getByRole('button',{name:'Select manualroot'})).toBeInTheDocument();expect(screen.getByRole('button',{name:'Select domain'})).toBeInTheDocument();expect(screen.getByRole('button',{name:'Представление полотна'})).toHaveTextContent('Все объекты')
  })
})

vi.mock('./useCanvasMutations',()=>({registerCanvasDraftProvider:vi.fn(),useCanvasMutations:(current?:{document?:{id:string;revision:number}})=>({
  pending:0,error:'',retry:vi.fn(),discard:vi.fn(),
  send:(op:string,payload:Record<string,unknown>={})=>act('research_canvas_'+op,{id:current?.document?.id,revision:current?.document?.revision,...payload}),
  edit:(operation:string,args:Record<string,unknown>={})=>act('research_canvas_edit',{id:current?.document?.id,revision:current?.document?.revision,operation,arguments:args})
})}))
