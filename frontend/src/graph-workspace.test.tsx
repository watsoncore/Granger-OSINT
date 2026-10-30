import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {describe,it,expect,vi} from 'vitest'
import {InvestigationWorkspace} from './components/InvestigationWorkspace'
import {emptyState,type GraphEntity,type GraphRelation} from './types'

vi.mock('./bridge',()=>({act:vi.fn().mockImplementation(async (name:string)=>name==='investigation_graph_get'?{generation:1}:true)}))
vi.mock('./components/InvestigationCanvas',()=>({InvestigationCanvas:({nodes}:{nodes:GraphEntity[]})=><div data-testid="visible-nodes">{nodes.map(node=>node.label).join(',')}</div>}))

describe('selected flow expansion in the existing workspace',()=>{
  it('updates visible transactions immediately and collapses the same flow without showing another flow',async()=>{
    const node=(id:string,type:string):GraphEntity=>({id,type,label:id,attributes:{},evidence_ids:[]})
    const edge=(id:string,transaction:string):GraphRelation=>({id,from_id:'root',to_id:'peer',relation_type:'transfers',direction:'directed',evidence_ids:[],verification_status:'source_reported',aggregate:{count:1,amount:'2',asset:'TON',known_amount_count:1,unknown_amount_count:0,transaction_ids:[transaction],owner_verified:false}})
    const state={...emptyState,search:{...emptyState.search,investigation_id:'fixture'},investigation_graph:{state:'ready' as const,investigation_id:'fixture',generation:1,root_id:'root',entities:[node('root','blockchain_address'),node('peer','blockchain_address'),node('selected-operation','transaction'),node('other-operation','transaction')],relations:[edge('flow','selected-operation'),edge('other-flow','other-operation')],view:{version:1 as const,mode:'graph' as const,selected_relation:'flow'}}}
    render(<InvestigationWorkspace state={state} onSource={()=>{}}/>)
    await waitFor(()=>expect(screen.getByRole('button',{name:'Раскрыть транзакции'})).toBeInTheDocument())
    expect(screen.getByTestId('visible-nodes').textContent).not.toContain('selected-operation')
    fireEvent.click(screen.getByRole('button',{name:'Раскрыть транзакции'}))
    expect(screen.getByTestId('visible-nodes').textContent).toContain('selected-operation')
    expect(screen.getByTestId('visible-nodes').textContent).not.toContain('other-operation')
    fireEvent.click(screen.getByRole('button',{name:'Свернуть транзакции'}))
    expect(screen.getByTestId('visible-nodes').textContent).not.toContain('selected-operation')
  })
})
