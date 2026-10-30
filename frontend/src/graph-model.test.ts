import {describe,it,expect} from 'vitest'
import {fitViewport,hitNode,hitRelation,layoutGraph,visibleGraph,zoomAt} from './graph-model'
import type {GraphEntity,GraphRelation,GraphView} from './types'

const node=(id:string,type='website'):GraphEntity=>({id,type,label:id,attributes:{},evidence_ids:[],verification_status:'source_reported'})
const edge=(a:string,b:string,id=a+b):GraphRelation=>({id,from_id:a,to_id:b,relation_type:'publishes_link',direction:'directed',evidence_ids:[],verification_status:'verified'})
const view:GraphView={version:1}
describe('investigation graph transformations',()=>{
  it('keeps filters distinct from an empty selection and excludes unsupported background',()=>{
    const nodes=[node('root'),node('a'),{...node('b'),relevance:{level:'background',score:0}},node('source','source')]
    expect(visibleGraph(nodes,[],'root',view).nodes.map(n=>n.id)).toEqual(['root','a'])
    expect(visibleGraph(nodes,[],'root',{...view,filters:{types:[]}}).nodes.map(n=>n.id)).toEqual(['root'])
    expect(visibleGraph(nodes,[],'root',{...view,filters:{include_background:true,show_sources:true}}).nodes).toHaveLength(4)
  })
  it('collapses branches without deleting their saved data and shows query neighbors',()=>{
    const nodes=['r','a','b','c'].map(id=>node(id)),edges=[edge('r','a'),edge('a','b'),edge('r','c')]
    expect(visibleGraph(nodes,edges,'r',{...view,collapsed:['a']}).nodes.map(n=>n.id)).toEqual(['r','a','c'])
    expect(visibleGraph(nodes,edges,'r',{...view,query:'b'}).nodes.map(n=>n.id)).toEqual(['r','a','b'])
    expect(nodes).toHaveLength(4)
  })
  it('expands aggregate transaction nodes only on demand',()=>{
    const nodes=[node('r','blockchain_address'),node('b','blockchain_address'),node('tx','transaction')]
    const e={...edge('r','b'),aggregate:{count:1,amount:'2',asset:'TON',known_amount_count:1,unknown_amount_count:0,transaction_ids:['tx'],owner_verified:false as const}}
    expect(visibleGraph(nodes,[e],'r',view).nodes).toHaveLength(2)
    expect(visibleGraph(nodes,[e],'r',{...view,expanded:['r']}).nodes).toHaveLength(3)
  })
  it('preserves pinned positions during relayout and computes independent tree positions',()=>{
    const nodes=['r','a','b'].map(id=>node(id)),edges=[edge('r','a'),edge('a','b')]
    const positions=layoutGraph(nodes,edges,'r','graph',{a:{x:900,y:200,pinned:true}},false)
    expect(positions.a).toEqual({x:900,y:200,pinned:true})
    expect(layoutGraph(nodes,edges,'r','tree').b).not.toEqual(positions.b)
    expect(layoutGraph(nodes,edges,'r','graph',positions)).toEqual(positions)
  })
  it('uses anchored zoom, fit and hit tests in screen coordinates',()=>{
    const points={r:{x:0,y:0},a:{x:100,y:0}},v={x:40,y:50,scale:2}
    expect(zoomAt(v,80,100,2)).toEqual({x:0,y:0,scale:4})
    expect(hitNode([node('r'),node('a')],points,v,240,50)?.id).toBe('a')
    expect(hitRelation([edge('r','a')],points,v,140,50)?.id).toBe('ra')
    expect(fitViewport(points,800,400).scale).toBeGreaterThan(0)
  })
  it('lays out 1000 nodes and 5000 directed edges with finite coordinates',()=>{
    const nodes=Array.from({length:1000},(_,i)=>node(String(i)))
    const edges=Array.from({length:5000},(_,i)=>edge(String(i%1000),String((i%1000+Math.floor(i/1000)+1)%1000),String(i)))
    const selected=visibleGraph(nodes,edges,'0',view,1200)
    expect(selected.nodes).toHaveLength(1000);expect(selected.edges).toHaveLength(5000)
    for(const mode of ['tree','graph'] as const){const result=layoutGraph(nodes,edges,'0',mode);expect(Object.keys(result)).toHaveLength(1000);expect(Object.values(result).every(p=>Number.isFinite(p.x+p.y))).toBe(true)}
  })
})
