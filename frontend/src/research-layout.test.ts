import {describe,it,expect} from 'vitest'
import {researchLayout} from './research-layout'
import type {GraphEntity,GraphRelation} from './types'
import {cardSize} from './graph-cards'

describe('shared analyst layouts',()=>{
  it('uses observed transfer direction for flow columns and keeps wallet and path layouts distinct',()=>{
    const nodes:GraphEntity[]=['root','incoming','outgoing','both'].map(id=>({id,type:'blockchain_address',label:id,attributes:{chain:'ton'},evidence_ids:[]})),edges:GraphRelation[]=[['incoming','root'],['root','outgoing'],['both','root'],['root','both']].map(([from_id,to_id],i)=>({id:'flow'+i,from_id,to_id,relation_type:'transfers',direction:'directed',evidence_ids:[],verification_status:'source_reported'}))
    const flow=researchLayout(nodes,edges,'root',{},'flow'),wallet=researchLayout(nodes,edges,'root',{},'wallet'),paths=researchLayout(nodes,edges,'root',{},'paths')
    expect(flow.incoming.x).toBeLessThan(flow.root.x);expect(flow.outgoing.x).toBeGreaterThan(flow.root.x);expect(flow.both.y).toBeGreaterThan(flow.root.y)
    expect(wallet).not.toEqual(flow);expect(paths).not.toEqual(wallet);expect(edges).toHaveLength(4)
  })
  it('keeps 100 counterparties compact around the root, with no overlapping actual card bounds',()=>{
    const nodes:GraphEntity[]=Array.from({length:101},(_,i)=>({id:i?'peer'+i:'root',type:'blockchain_address',label:'Wallet '+i,attributes:i===1?{_card_size:{width:520,height:220}}:{},evidence_ids:[]}))
    const edges:GraphRelation[]=nodes.slice(1).map(node=>({id:node.id,from_id:'root',to_id:node.id,relation_type:'transfers',direction:'directed',verification_status:'source_reported',evidence_ids:[]}))
    const points=researchLayout(nodes,edges,'root',{},'wallet')
    expect(points.root).toEqual({x:0,y:0})
    const xs=Object.values(points).map(point=>point.x),ys=Object.values(points).map(point=>point.y)
    expect(Math.max(...xs)-Math.min(...xs)).toBeLessThan(7000)
    expect(Math.max(...ys)-Math.min(...ys)).toBeLessThan(3500)
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const a=points[nodes[i].id],b=points[nodes[j].id],sa=cardSize(nodes[i]),sb=cardSize(nodes[j])
      expect(Math.abs(a.x-b.x)>=(sa.width+sb.width)/2||Math.abs(a.y-b.y)>=(sa.height+sb.height)/2).toBe(true)
    }
    expect(researchLayout(nodes,edges,'root',points,'manual')).toBe(points)
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
