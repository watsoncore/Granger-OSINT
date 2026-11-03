import {fireEvent,render,screen} from '@testing-library/react'
import {describe,it,expect,vi} from 'vitest'
import {ResearchCanvas} from './components/ResearchCanvas'
import {emptyState,type ResearchDocument} from './types'
import {act} from './bridge'
vi.mock('./bridge',()=>({act:vi.fn().mockResolvedValue(true)}))
vi.mock('./components/InvestigationCanvas',()=>({InvestigationCanvas:()=> <div data-testid="renderer"/>}))

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
})
