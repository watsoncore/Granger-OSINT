import {describe,it,expect} from 'vitest'
import {researchLayout} from './research-layout'
import type {GraphEntity,GraphRelation} from './types'

describe('shared analyst layouts',()=>{
  it('uses observed transfer direction for flow columns and keeps wallet and path layouts distinct',()=>{
    const nodes:GraphEntity[]=['root','incoming','outgoing','both'].map(id=>({id,type:'blockchain_address',label:id,attributes:{chain:'ton'},evidence_ids:[]})),edges:GraphRelation[]=[['incoming','root'],['root','outgoing'],['both','root'],['root','both']].map(([from_id,to_id],i)=>({id:'flow'+i,from_id,to_id,relation_type:'transfers',direction:'directed',evidence_ids:[],verification_status:'source_reported'}))
    const flow=researchLayout(nodes,edges,'root',{},'flow'),wallet=researchLayout(nodes,edges,'root',{},'wallet'),paths=researchLayout(nodes,edges,'root',{},'paths')
    expect(flow.incoming.x).toBeLessThan(flow.root.x);expect(flow.outgoing.x).toBeGreaterThan(flow.root.x);expect(flow.both.y).toBeGreaterThan(flow.root.y)
    expect(wallet).not.toEqual(flow);expect(paths).not.toEqual(wallet);expect(edges).toHaveLength(4)
  })
  for(const count of [50,100,500,1000,5000])it(`bounded mixed ${count}-node layout retains pins and finite coordinates`,()=>{
    const nodes:GraphEntity[]=Array.from({length:count},(_,i)=>({id:'n'+i,type:['person','blockchain_address','image','domain'][i%4],label:'Контроль '+i,attributes:{timestamp:i%5?'2026-11-03T00:00:00Z':null},evidence_ids:[]}))
    const edges:GraphRelation[]=nodes.slice(1).map((n,i)=>({id:'e'+i,from_id:'n'+Math.floor(i/3),to_id:n.id,relation_type:'potentially_related',direction:'directed',evidence_ids:[],verification_status:'inferred'}))
    const samples:Record<string,number>={}
    for(const mode of ['hierarchical','radial','types','communities','timeline']){
      const started=performance.now(),points=researchLayout(nodes,edges,'n0',{n0:{x:-500,y:-200,pinned:true}},mode)
      samples[mode]=Math.round((performance.now()-started)*100)/100
      expect(Object.keys(points)).toHaveLength(count);expect(points.n0).toEqual({x:-500,y:-200,pinned:true})
      expect(Object.values(points).every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y))).toBe(true)
      expect(samples[mode]).toBeLessThan(5000)
    }
    console.log(JSON.stringify({origin:'source-algorithm-jsdom-not-native-FPS',nodes:count,edges:edges.length,layout_ms:samples}))
  })
})
