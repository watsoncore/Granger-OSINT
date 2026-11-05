import {describe,it,expect} from 'vitest'
import {semanticGraph} from './graph-semantic'
import type {GraphEntity,GraphRelation} from './types'

describe('distant semantic glyph groups',()=>{
  const nodes:GraphEntity[]=['root','a','b','selected'].map(id=>({id,type:'blockchain_address',label:id,attributes:{chain:'ton'},evidence_ids:[id]})),positions={root:{x:0,y:0},a:{x:900,y:0},b:{x:920,y:10},selected:{x:950,y:0}}
  const edge=(id:string,to:string,amount:string):GraphRelation=>({id,from_id:'root',to_id:to,relation_type:'transfers',direction:'directed',evidence_ids:[id],verification_status:'source_reported',aggregate:{count:1,amount,asset:'TON',known_amount_count:1,unknown_amount_count:0,transaction_ids:['tx_'+id],owner_verified:false}})
  it('retains root and selected originals, groups peers with exact amounts, and leaves source data untouched',()=>{
    const edges=[edge('e1','a','0.000000001'),edge('e2','b','0.000000002')],before=JSON.stringify({nodes,edges,positions})
    const view=semanticGraph(nodes,edges,positions,.18,new Set(['root','selected']))
    expect(view.clusters).toHaveLength(1);expect(view.clusters[0].members).toEqual(['a','b'])
    expect(view.nodes.map(node=>node.id)).toEqual(expect.arrayContaining(['root','selected',view.clusters[0].id]))
    expect(view.edges).toHaveLength(1);expect(view.edges[0].aggregate).toMatchObject({amount:'0.000000003',count:2,transaction_ids:['tx_e1','tx_e2']})
    expect(JSON.stringify({nodes,edges,positions})).toBe(before)
  })
  it('does not regroup on pan, does not mix assets, and restores original objects at medium zoom',()=>{
    const ton=edge('ton','a','1'),other={...edge('token','b','2'),aggregate:{...edge('token','b','2').aggregate!,asset:'token'}}
    const first=semanticGraph(nodes,[ton,other],positions,.18,new Set(['root']))
    expect(first.edges).toHaveLength(2)
    expect(semanticGraph(nodes,[ton,other],positions,.18,new Set(['root'])).clusters).toEqual(first.clusters)
    expect(semanticGraph(nodes,[ton,other],positions,.5,new Set(['root'])).nodes).toBe(nodes)
  })
  it('keeps the root visible when a selected transaction occupies the same far position',()=>{
    const overlapped={...positions,selected:{...positions.root}}
    const view=semanticGraph(nodes,[],overlapped,.18,new Set(['root','selected']))
    expect(view.positions.root).toEqual(overlapped.root)
    expect(Math.abs(view.positions.selected.y-view.positions.root.y)*.18).toBeGreaterThanOrEqual(48)
    expect(overlapped.selected).toEqual(overlapped.root)
  })
})
