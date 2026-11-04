import {describe,it,expect} from 'vitest'
import {fitViewport,hitNode,hitRelation,layoutGraph,visibleGraph,zoomAt} from './graph-model'
import type {GraphEntity,GraphRelation,GraphView} from './types'
import {routeEdges} from './graph-geometry'

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
    expect(visibleGraph(nodes,[e],'r',{...view,expanded:['r']}).nodes).toHaveLength(2)
    expect(visibleGraph(nodes,[e],'r',{...view,expanded_relations:[e.id]}).nodes).toHaveLength(3)
  })
  it('preserves pinned positions during relayout and computes independent tree positions',()=>{
    const nodes=['r','a','b'].map(id=>node(id)),edges=[edge('r','a'),edge('a','b')]
    const positions=layoutGraph(nodes,edges,'r','graph',{a:{x:900,y:200,pinned:true}},false)
    expect(positions.a).toEqual({x:900,y:200,pinned:true})
    expect(layoutGraph(nodes,edges,'r','tree').b).not.toEqual(positions.b)
    expect(layoutGraph(nodes,edges,'r','graph',positions)).toEqual(positions)
  })
  it('places newly expanded transactions outside preserved cards without moving existing nodes',()=>{
    const initial=['r','a','b','c','d','e','f','g','h','i'].map(id=>node(id)),edges=initial.slice(1).map(n=>edge('r',n.id))
    const saved=layoutGraph(initial,edges,'r','graph')
    const added=Array.from({length:10},(_,i)=>node('tx'+i,'transaction'))
    const result=layoutGraph([...initial,...added],[...edges,...added.map(n=>edge('r',n.id))],'r','graph',saved)
    initial.forEach(n=>expect(result[n.id]).toEqual(saved[n.id]))
    added.forEach(n=>initial.forEach(old=>expect(Math.abs(result[n.id].x-result[old.id].x)>=260||Math.abs(result[n.id].y-result[old.id].y)>=120).toBe(true)))
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
    expect(selected.nodes).toHaveLength(1000);expect(selected.edges).toHaveLength(999)
    expect(selected.hiddenRelations).toBe(4001);expect(edges).toHaveLength(5000)
    const focused=visibleGraph(nodes,edges,'0',{...view,expanded:['10']},1200)
    const incident=edges.filter(edge=>edge.from_id==='10'||edge.to_id==='10')
    expect(incident.every(edge=>focused.edges.some(visible=>visible.id===edge.id))).toBe(true)
    for(const mode of ['tree','graph'] as const){const result=layoutGraph(nodes,edges,'0',mode);expect(Object.keys(result)).toHaveLength(1000);expect(Object.values(result).every(p=>Number.isFinite(p.x+p.y))).toBe(true)}
  })
  it('picks opposing transfers separately and supports self-transfer loops',()=>{
    const nodes=[node('a','blockchain_address'),node('b','blockchain_address')],positions={a:{x:0,y:0},b:{x:500,y:0}},v={x:200,y:150,scale:1}
    const edges=[edge('a','b','out'),edge('b','a','in'),edge('a','a','self')]
    for(const route of routeEdges(edges,positions,v,nodes)){
      const point=route.points[Math.floor(route.points.length/2)]
      expect(hitRelation(edges,positions,v,point.x,point.y,nodes)?.id).toBe(route.edge.id)
    }
  })
  it('culls distant edge geometry while retaining offscreen-endpoint crossings',()=>{
    const nodes=['a','b','c','d'].map(id=>node(id)),positions={a:{x:-10000,y:200},b:{x:10000,y:200},c:{x:10000,y:10000},d:{x:11000,y:11000}}
    const routes=routeEdges([edge('a','b','crossing'),edge('c','d','distant')],positions,{x:0,y:0,scale:1},nodes,'graph',{left:0,top:0,right:800,bottom:600})
    expect(routes.map(r=>r.edge.id)).toEqual(['crossing'])
  })
  it('queries public object fields without matching thousands of internal member IDs or image bytes',()=>{
    const nodes=[node('root'),{...node('group','entity_group'),attributes:{member_ids:['needle','other'],media:{thumbnail:'needle'}}},
      {...node('target'),label:'needle',attributes:{parent_group_id:'group'}},...Array.from({length:100},(_,i)=>({...node('extra'+i),attributes:{parent_group_id:'group'}}))]
    const edges=nodes.slice(2).map(item=>edge('group',item.id))
    expect(visibleGraph(nodes,edges,'root',{version:1,query:'needle'}).nodes.map(item=>item.id)).toEqual(['root','group','target'])
  })
})
