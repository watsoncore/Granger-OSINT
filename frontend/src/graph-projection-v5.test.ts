import {it,expect} from 'vitest'
import {visibleGraph,walletSummary,socmintProfiles} from './graph-model'
import {formatGraphAmount,exactGraphAmount,addGraphAmounts} from './graph-money'
import type {GraphEntity,GraphRelation,GraphView} from './types'
const node=(id:string,type='blockchain_address',attributes:Record<string,unknown>={}):GraphEntity=>({id,type,label:id,attributes:{chain:'ton',address:id,...attributes},evidence_ids:['proof-'+id]})
const flow=(id:string,from_id:string,to_id:string,asset='TON',amount='0.000000001'):GraphRelation=>({id,from_id,to_id,relation_type:'transfers',direction:'directed',verification_status:'source_reported',evidence_ids:['proof-'+id],source_urls:['https://example.org/'+id],aggregate:{count:1,amount,asset,asset_key:'ton|'+asset,known_amount_count:1,unknown_amount_count:0,transaction_ids:['tx-'+id],owner_verified:false}})
it('uses a selected financial page but reveals its exact transfer and endpoint above the page budget',()=>{
 const nodes=[node('root'),node('one'),node('two'),node('unrelated'),node('tx-b','transaction')],edges=[flow('a','root','one'),flow('b','two','root')]
 const view:GraphView={version:1,mode:'graph',projection_mode:'wallet',filters:{peer_ids:['one']}}
 const result=visibleGraph(nodes,edges,'root',view,20)
 expect(result.nodes.map(n=>n.id)).toEqual(['root','one'])
 const drill=visibleGraph(nodes,edges,'root',{...view,expanded_relations:['b']},20)
 expect(drill.nodes.map(n=>n.id)).toEqual(expect.arrayContaining(['root','one','two','tx-b']))
 expect(drill.nodes.some(n=>n.id==='unrelated')).toBe(false)
})
it('summarizes separate assets and both directions without inventing UTXO financial flows',()=>{
 const nodes=[node('root','blockchain_address',{transaction_count:45}),node('one'),node('two')]
 const edges=[flow('a','root','one'),flow('b','one','root','USD','2'),{id:'claim',from_id:'root',to_id:'two',relation_type:'source_reports_counterparty',direction:'undirected',verification_status:'source_reported',evidence_ids:['utxo'],attributes:{count:20}} satisfies GraphRelation]
 const report=walletSummary(nodes,edges,'root')
 expect(report.observed_transaction_count).toBe(2);expect(report.source_reported_transaction_count).toBe(45)
 expect(report.counterparty_count).toBe(2);expect(report.coverage).toBe('observed_sample_only')
 expect(report.counterparties.find(n=>n.id==='one')!.flows.map(f=>[f.direction,f.asset,f.amount])).toEqual([['outgoing','TON','0.000000001'],['incoming','USD','2']])
 expect(report.counterparties.find(n=>n.id==='two')).toMatchObject({direction_unknown:true,source_claim_count:20,flows:[]})
})
it('keeps self transfers observable without reporting the root as its own counterparty',()=>{
 const report=walletSummary([node('root')],[flow('self','root','root')],'root')
 expect(report.counterparties).toEqual([]);expect(report.counterparty_count).toBe(0)
 expect(report.observed_transaction_count).toBe(1);expect(report.self_flows[0].direction).toBe('self')
})
it('projects one username to its actual profiles, preserving source access and excluding unrelated accounts',()=>{
 const nodes=[node('root','username'),node('profile','public_profile',{username:'solvnox',platform:'GitHub'}),node('other','public_profile'),node('scoped','username'),node('domain','domain'),node('source','source')]
 const edge=(id:string,from_id:string,to_id:string,relation_type:string):GraphRelation=>({id,from_id,to_id,relation_type,direction:'directed',verification_status:'source_reported',evidence_ids:['proof']})
 const edges=[edge('found','root','profile','returned_for_query'),edge('technical','profile','scoped','uses_public_identifier'),edge('domainref','profile','domain','published_on_domain'),edge('proof','profile','source','supported_by')]
 const original=structuredClone({nodes,edges}),view:GraphView={version:1,mode:'graph',projection_mode:'socmint',filters:{show_sources:false}}
 expect(socmintProfiles(nodes,edges,'root').map(n=>n.id)).toEqual(['profile'])
 expect(visibleGraph(nodes,edges,'root',view).nodes.map(n=>n.id)).toEqual(['root','profile'])
 expect(visibleGraph(nodes,edges,'root',{...view,projection_mode:'infrastructure'}).nodes.map(n=>n.id)).toEqual(expect.arrayContaining(['root','profile','domain']))
 expect(visibleGraph(nodes,edges,'root',{...view,projection_mode:'evidence'}).nodes.map(n=>n.id)).toEqual(expect.arrayContaining(['root','profile','source']))
 expect({nodes,edges}).toEqual(original)
})
it('formats tiny and large decimal strings while preserving complete precision in details',()=>{
 expect(formatGraphAmount('0.000000001')).toBe('1e-9')
 expect(exactGraphAmount('0.000000001')).toBe('0.000000001')
 expect(formatGraphAmount('123456789012345678901.123456789',false)).toBe('123456789012345678901.123456789')
 expect(formatGraphAmount('1000.000000001')).toBe('1K')
 expect(formatGraphAmount('1000000000000000000000000')).toBe('1e+24')
 expect(addGraphAmounts(['0.123456789012345678901','0.000000000000000000001'])).toBe('0.123456789012345678902')
 expect(addGraphAmounts(['100000000000000000000','1'])).toBe('100000000000000000001')
 expect(formatGraphAmount(null)).toBe('Неизвестно')
})
