import {describe,it,expect} from 'vitest'
import {cardSize,cardVariant,withCardPresentation} from './graph-cards'
import {layoutGraph,visibleGraph,hitNode} from './graph-model'
import {nodeBox,routeEdges} from './graph-geometry'
import type {GraphEntity,GraphRelation} from './types'
const node=(id:string,type:string,attributes:Record<string,unknown>={}):GraphEntity=>({id,type,label:'Длинная подпись объекта '+id,attributes,evidence_ids:[]})
const edge=(a:string,b:string,type='transfers'):GraphRelation=>({id:a+b,from_id:a,to_id:b,relation_type:type,direction:'directed',evidence_ids:[],verification_status:'source_reported'})
describe('shared analytical projection and semantic cards',()=>{
  it('keeps source facts and raw transactions out of wallet overview until explicitly requested',()=>{
    const rows=[node('root','blockchain_address'),node('peer','blockchain_address'),node('tx','transaction'),node('source','source'),node('label','service')],aggregate={...edge('root','peer'),aggregate:{count:1,amount:'0.125',asset:'TON',known_amount_count:1,unknown_amount_count:0,transaction_ids:['tx'],owner_verified:false as const}},links=[aggregate,edge('root','tx','sent_from'),edge('root','source','supported_by'),edge('root','label','source_labels_address')]
    const view={version:1 as const,mode:'graph' as const,projection_mode:'wallet' as const}
    expect(visibleGraph(rows,links,'root',view).nodes.map(n=>n.id)).toEqual(['root','peer'])
    expect(visibleGraph(rows,links,'root',{...view,expanded_relations:[aggregate.id]}).nodes.map(n=>n.id)).toContain('tx')
    expect(visibleGraph(rows,links,'root',{...view,filters:{show_sources:true}}).nodes.map(n=>n.id)).toContain('source')
    expect(rows).toHaveLength(5);expect(links).toHaveLength(4)
  })
  it('limits counterparties to target-connected wallets and path mode to reachable semantic path',()=>{
    const rows=['root','peer','other','deep'].map(id=>node(id,'blockchain_address')),links=[edge('root','peer'),edge('peer','deep')]
    expect(visibleGraph(rows,links,'root',{version:1,projection_mode:'counterparties'}).nodes.map(n=>n.id)).toEqual(['root','peer'])
    const path=visibleGraph(rows,links,'root',{version:1,projection_mode:'paths',selected_id:'deep'})
    expect(path.nodes.map(n=>n.id)).toEqual(expect.arrayContaining(['root','peer','deep']));expect(path.nodes.some(n=>n.id==='other')).toBe(false)
  })
  it('reveals only the selected flow transactions even when their collection is collapsed by default',()=>{
    const rows=[node('root','blockchain_address'),node('peer','blockchain_address'),node('group','entity_group'),node('tx','transaction',{parent_group_id:'group'}),node('other-tx','transaction',{parent_group_id:'group'})]
    const transfer={...edge('root','peer'),aggregate:{count:1,amount:'1',asset:'TRX',known_amount_count:1,unknown_amount_count:0,transaction_ids:['tx'],owner_verified:false as const}}
    const links=[transfer,edge('root','tx','sent_from'),edge('root','other-tx','sent_from')]
    const result=visibleGraph(rows,links,'root',{version:1,mode:'graph',projection_mode:'wallet',expanded_relations:[transfer.id]})
    expect(result.nodes.map(n=>n.id)).toContain('tx')
    expect(result.nodes.map(n=>n.id)).not.toContain('other-tx')
    expect(rows).toHaveLength(5)
  })
  it('retains a reported counterparty without inventing a financial flow',()=>{
    const rows=[node('root','blockchain_address'),node('btcpeer','blockchain_address')],claim={...edge('root','btcpeer','source_reports_counterparty'),direction:'undirected',attributes:{count:23,financial_transfer:false,owner_verified:false}}
    expect(visibleGraph(rows,[claim],'root',{version:1,projection_mode:'counterparties'}).nodes).toHaveLength(2)
    expect(visibleGraph(rows,[claim],'root',{version:1,projection_mode:'flow'}).edges).toHaveLength(0)
    expect(claim).not.toHaveProperty('aggregate');expect(claim.attributes).not.toHaveProperty('amount')
  })
  it('uses distinct media geometry, persisted sizes, scalable hit tests and endpoint boundaries',()=>{
    const media=node('photo','image',{media:{width:1600,height:900}}),note=node('note','analyst_note'),wallet=node('root','blockchain_address')
    expect(cardVariant(media)).toBe('media');expect(cardVariant(note)).toBe('note');expect(cardSize(media).height).toBeGreaterThan(cardSize(wallet).height)
    const rows=withCardPresentation([media,wallet],{photo:{width:500,height:330}}),points={photo:{x:0,y:0},root:{x:700,y:0}},view={x:100,y:100,scale:.4}
    expect(nodeBox(rows[0],.4)).toEqual({width:200,height:132});expect(hitNode(rows,points,view,190,100)?.id).toBe('photo');expect(hitNode(rows,points,view,215,100)).toBeUndefined()
    const route=routeEdges([edge('photo','root')],points,view,rows)[0];expect(route.points[0].x).toBeCloseTo(204)
  })
  it('lays out large resizable media with unequal cards without overlapping or moving pins',()=>{
    const rows=withCardPresentation([node('root','blockchain_address'),node('photo','image'),node('note','analyst_note'),node('peer','blockchain_address')],{photo:{width:650,height:430}}),links=[edge('root','photo'),edge('root','note'),edge('root','peer')]
    const pins={root:{x:0,y:0,pinned:true}},points=layoutGraph(rows,links,'root','graph',pins,false)
    expect(points.root).toEqual(pins.root)
    for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){const a=points[rows[i].id],b=points[rows[j].id],sa=cardSize(rows[i]),sb=cardSize(rows[j]);expect(Math.abs(a.x-b.x)>=(sa.width+sb.width)/2||Math.abs(a.y-b.y)>=(sa.height+sb.height)/2).toBe(true)}
  })
})
