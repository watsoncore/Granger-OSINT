import {it,expect} from 'vitest'
import {visibleGraph} from './graph-model'
import type {GraphEntity,GraphRelation,GraphView} from './types'
it('adds only explicitly requested transactions above a compact wallet overview budget',()=>{
 const nodes:GraphEntity[]=['root','peer','other'].map(id=>({id,type:'blockchain_address',label:id,attributes:{chain:'ton'},evidence_ids:[]}))
 for(const id of ['tx','unrequested'])nodes.push({id,type:'transaction',label:id,attributes:{chain:'ton'},evidence_ids:[]})
 const edges:GraphRelation[]=[{id:'flow',from_id:'root',to_id:'peer',relation_type:'transfers',direction:'directed',verification_status:'source_reported',evidence_ids:[],aggregate:{count:1,amount:'1',asset:'TON',asset_key:'ton',known_amount_count:1,unknown_amount_count:0,transaction_ids:['tx'],owner_verified:false}}]
 const before=structuredClone({nodes,edges}),view:GraphView={version:1,mode:'graph',filters:{show_transactions:false,show_sources:false}}
 const overview=visibleGraph(nodes,edges,'root',view,2)
 const expanded=visibleGraph(nodes,edges,'root',{...view,expanded_relations:['flow']},2)
 expect(overview.nodes).toHaveLength(2);expect(expanded.nodes.map(n=>n.id)).toEqual(expect.arrayContaining(['root','peer','tx']))
 expect(expanded.nodes.some(n=>n.id==='unrequested')).toBe(false);expect({nodes,edges}).toEqual(before)
})
