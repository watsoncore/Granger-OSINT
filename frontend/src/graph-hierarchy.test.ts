import {describe,it,expect} from 'vitest'
import {hierarchy} from './graph-hierarchy'
import {layoutGraph,visibleGraph} from './graph-model'
import {nodeBox,routeEdges} from './graph-geometry'
import type {GraphEntity,GraphRelation} from './types'
const n=(id:string,attributes:Record<string,unknown>={}):GraphEntity=>({id,label:id,type:'public_profile',attributes,evidence_ids:[]})
const e=(a:string,b:string,type='publishes_link'):GraphRelation=>({id:a+'-'+b,from_id:a,to_id:b,relation_type:type,direction:'directed',verification_status:'source_reported',evidence_ids:[]})

describe('independent branching tree and constrained network',()=>{
  const nodes=[n('root'),n('inventory'),n('category'),n('item',{parent_group_id:'category'}),n('peer')]
  const edges=[e('root','inventory','has_public_inventory'),e('inventory','category','contains_inventory_category'),e('category','item','contains_inventory_item'),e('root','item','owns_public_item'),e('root','peer'),e('item','peer')]
  it('chooses one semantic parent, retains shortcuts as separate cross-links and has no cycles',()=>{
    const h=hierarchy(nodes,edges,'root')
    expect(h.path('item')).toEqual(['root','inventory','category','item'])
    expect(h.treeEdges.filter(edge=>edge.to_id==='item')).toHaveLength(1)
    expect(h.crossEdges.some(edge=>edge.relation_type==='owns_public_item')).toBe(true)
    for(const node of nodes)expect(new Set(h.path(node.id)).size).toBe(h.path(node.id).length)
  })
  it('lays out each child below its own parent branch with distinct radial graph coordinates',()=>{
    const rows=['root','a','b','a1','a2','b1','b2'].map(id=>n(id)),links=[e('root','a'),e('root','b'),e('a','a1'),e('a','a2'),e('b','b1'),e('b','b2')]
    const tree=layoutGraph(rows,links,'root','tree',{},false),graph=layoutGraph(rows,links,'root','graph',{},false)
    expect(tree.a1.x).toBeGreaterThan(tree.a.x);expect(tree.a2.y).toBeLessThan(tree.b1.y)
    expect(tree.a.y).toBe((tree.a1.y+tree.a2.y)/2)
    expect(graph.a.y).not.toEqual(tree.a.y);expect(graph.b.x).not.toEqual(tree.b.x)
    expect(layoutGraph(rows,links,'root','graph',{},false)).toEqual(graph)
    expect(routeEdges(links,tree,{x:0,y:0,scale:1},rows,'tree').every(route=>route.points.length===4)).toBe(true)
  })
  it('limits the initial tree to two levels and reveals the selected path or a searched deep item',()=>{
    const initial=visibleGraph(nodes,edges,'root',{version:1,mode:'tree'})
    expect(initial.nodes.some(node=>node.id==='item')).toBe(false)
    const expanded=visibleGraph(nodes,edges,'root',{version:1,mode:'tree',expanded:['category']})
    expect(expanded.nodes.some(node=>node.id==='item')).toBe(true)
    const found=visibleGraph(nodes,edges,'root',{version:1,mode:'tree',query:'item'})
    expect(found.nodes.map(node=>node.id)).toEqual(expect.arrayContaining(['root','inventory','category','item']))
    expect(found.edges.filter(edge=>edge.to_id==='item')).toHaveLength(1)
  })
  it('keeps a 1000-item collection intact while default tree shows a readable preview',()=>{
    const rows=[n('root'),n('inventory'),...Array.from({length:1000},(_,i)=>n('item'+i))],links=[e('root','inventory'),...rows.slice(2).map(row=>e('inventory',row.id))]
    expect(visibleGraph(rows,links,'root',{version:1,mode:'tree'}).nodes.length).toBeLessThanOrEqual(7)
    const expanded=visibleGraph(rows,links,'root',{version:1,mode:'tree',expanded:['inventory']},1200)
    expect(expanded.nodes).toHaveLength(1002);expect(expanded.edges).toHaveLength(1001)
    expect(rows).toHaveLength(1002)
  })
  it('never replaces a low-zoom node with an unlabeled ten-pixel square',()=>{
    const box=nodeBox(n('item'),.17);expect(box.width).toBeGreaterThanOrEqual(136);expect(box.height).toBeGreaterThanOrEqual(54)
  })
  it('retains branching hierarchy after expansion instead of appending a grid of new cards',()=>{
    const rows=['root','a','b','a1','a2','b1'].map(id=>n(id)),links=[e('root','a'),e('root','b'),e('a','a1'),e('a','a2'),e('b','b1')]
    const saved=layoutGraph(rows.slice(0,3),links,'root','tree')
    const expanded=layoutGraph(rows,links,'root','tree',saved,true)
    expect(expanded.a.y).toBe((expanded.a1.y+expanded.a2.y)/2)
    expect(expanded.b.x).toBe(expanded.a.x);expect(expanded.b.y).toBeGreaterThan(expanded.a2.y)
  })
  it('does not let hidden raw model priors consume the visible candidate preview',()=>{
    const rows=[n('root'),{...n('group'),type:'entity_group',attributes:{topic_group:true}},
      ...Array.from({length:8},(_,i)=>({...n('prior'+i),type:'geographic_candidate',attributes:{raw_prediction_only:true,attachment_id:'img_fixture',parent_group_id:'group'}})),
      {...n('researched'),type:'geographic_candidate',attributes:{candidate_id:'geo_fixture',attachment_id:'img_fixture',parent_group_id:'group'}}]
    const links=[e('root','group','groups_observations'),...rows.slice(2).map(row=>e('group',row.id,'group_contains'))]
    const visible=visibleGraph(rows,links,'root',{version:1,mode:'tree'})
    expect(visible.nodes.map(row=>row.id)).toEqual(['root','group','researched'])
  })
})
