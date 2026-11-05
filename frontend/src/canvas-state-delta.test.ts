import {describe,it,expect} from 'vitest'
import {emptyState,parseState,type ResearchDocument} from './types'
const document:ResearchDocument={schema:'granger-investigation/1',id:'a'.repeat(32),revision:3,title:'Тест',description:'',entities:[{id:'node',type:'analyst_note',label:'Заметка',attributes:{},evidence_ids:[]}],relations:[],evidence:[],annotations:{},custom_types:{},view:{positions:{node:{x:20,y:30}},viewport:{x:10,y:10,scale:1},layout:'manual',hidden:[],removed:[],collapsed:[]}}
const previous={...emptyState,research_canvas:{state:'ready',document,types:[],choices:[]}}
const delta=()=>({canvas_id:document.id,base_revision:3,state:{},state_removed:[],document:{revision:4},document_removed:[],view:{viewport:{x:150,y:-200,scale:1}},view_removed:[],positions:{},positions_removed:[]})
describe('ordered canvas channel deltas',()=>{
 it('retains entity/evidence identity for camera-only saves',()=>{
  const next=parseState(JSON.stringify({patch:true,research_canvas_delta:delta()}),previous)
  expect(next.research_canvas?.document?.entities).toBe(document.entities)
  expect(next.research_canvas?.document?.evidence).toBe(document.evidence)
  expect(next.research_canvas?.document?.view.positions).toBe(document.view.positions)
  expect(next.research_canvas?.document?.view.viewport.x).toBe(150)
  expect(next.research_canvas?.document?.revision).toBe(4)
  expect(document.view.viewport.x).toBe(10)
 })
 it('requires the matching document and revision before applying a delta',()=>{
  expect(()=>parseState(JSON.stringify({research_canvas_delta:{...delta(),base_revision:2}}),previous)).toThrow(/Версия/)
  expect(()=>parseState(JSON.stringify({research_canvas_delta:{...delta(),canvas_id:'b'.repeat(32)}}),previous)).toThrow(/Версия/)
 })
 it('applies ordered position edits without losing concurrent panels or evidence',()=>{
  const next=parseState(JSON.stringify({research_canvas_delta:{...delta(),positions:{node:{x:60,y:50}},state:{busy:false}}}),previous)
  expect(next.research_canvas?.document?.view.positions.node).toEqual({x:60,y:50})
  expect(next.research_canvas?.document?.entities).toBe(document.entities)
  const after=parseState(JSON.stringify({research_canvas_delta:{...delta(),base_revision:4,document:{revision:5}}}),next)
  expect(after.research_canvas?.document?.view.positions.node).toEqual({x:60,y:50})
 })
})
