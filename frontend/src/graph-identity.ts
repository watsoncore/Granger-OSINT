import type { GraphEntity, GraphRelation } from './types'

export const profileTypes = new Set(['public_profile','social_profile','github_profile','telegram_channel'])
const infrastructureTypes = new Set(['domain','website','ip','ip_address','infrastructure_asset','dns_record','network','asn','service'])
const infrastructureRelations = new Set(['published_on_domain','uses_email_domain','resolves_to','belongs_to_asn','dns_resolves_to','platform_infrastructure'])
const evidenceTypes = new Set(['source','document','observation','claim','hypothesis','analyst_note'])
const evidenceRelations = new Set(['supported_by','groups_observations','reference_for_candidate','contradicts','cites'])
const enrichmentRelations = new Set(['repository_namespace','public_organization_membership','profile_publishes_url','has_public_release'])

export function identityProjection(nodes: GraphEntity[], edges: GraphRelation[], root: string,
  mode: 'socmint'|'infrastructure'|'evidence', profiles: GraphEntity[]) {
  const profileIds=new Set(profiles.filter(node=>!node.attributes.visual_instance_of).map(node=>node.id))
  const ids=new Set([root,...profileIds])
  if(mode==='socmint') {
    for(let depth=0;depth<2;depth++){
      for(const edge of edges)if(enrichmentRelations.has(edge.relation_type)&&(ids.has(edge.from_id)||ids.has(edge.to_id))){
        ids.add(edge.from_id)
        ids.add(edge.to_id)
      }
    }
    const groups=new Map(nodes.filter(node=>node.type==='entity_group').map(node=>[node.id,node]))
    for(const node of nodes) {
      if(!ids.has(node.id))continue
      let parent=String(node.attributes.parent_group_id||'')
      while(groups.has(parent)&&!ids.has(parent)) {
        ids.add(parent)
        parent=String(groups.get(parent)?.attributes.parent_group_id||'')
      }
    }
    for(const group of groups.values())if(group.attributes.origin==='analyst'&&group.attributes._collapsed)ids.add(group.id)
    const relevant=edges.filter(edge=>ids.has(edge.from_id)&&ids.has(edge.to_id)&&
      (edge.origin==='analyst'||edge.relation_type==='group_contains'||edge.relation_type==='returned_for_query'||
        edge.relation_type==='investigates'||enrichmentRelations.has(edge.relation_type)||edge.verification_status==='verified'))
    return {nodes:nodes.filter(node=>ids.has(node.id)).map(node=>node.id===root&&['username','nickname'].includes(node.type)
      ?{...node,attributes:{...node.attributes,_profile_count:profileIds.size}}:node),edges:relevant}
  }
  const types=mode==='infrastructure'?infrastructureTypes:evidenceTypes
  const relations=mode==='infrastructure'?infrastructureRelations:evidenceRelations
  for(const node of nodes)if(types.has(node.type)&&!node.attributes.visual_instance_of)ids.add(node.id)
  const kinds=new Map(nodes.map(node=>[node.id,node.type]))
  const selected=edges.filter(edge=>ids.has(edge.from_id)&&ids.has(edge.to_id)&&
    (relations.has(edge.relation_type)||types.has(kinds.get(edge.from_id)||'')||types.has(kinds.get(edge.to_id)||'')))
  const connected=new Set([root,...selected.flatMap(edge=>[edge.from_id,edge.to_id])])
  return {nodes:nodes.filter(node=>connected.has(node.id)||types.has(node.type)),edges:selected}
}

export function focusedIds(nodes: GraphEntity[], edges: GraphRelation[], root: string, depth: number) {
  if(depth>=4)return new Set(nodes.map(node=>node.id))
  const adjacent=new Map<string,string[]>()
  for(const {from_id,to_id} of edges) {
    const from=adjacent.get(from_id)||[],to=adjacent.get(to_id)||[]
    from.push(to_id);to.push(from_id)
    adjacent.set(from_id,from);adjacent.set(to_id,to)
  }
  const visited=new Set([root])
  let frontier=[root]
  for(let level=0;level<depth&&frontier.length;level++){
    const next:string[]=[]
    for(const id of frontier)for(const neighbor of adjacent.get(id)||[])if(!visited.has(neighbor)){
      visited.add(neighbor);next.push(neighbor)
    }
    frontier=next
  }
  return visited
}
