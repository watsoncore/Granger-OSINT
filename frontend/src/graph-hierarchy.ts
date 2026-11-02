import type {GraphEntity,GraphRelation} from './types'

// A presentation hierarchy is a spanning tree, never an assertion of ownership.
// All original relations stay in the common evidence model and in the inspector.
const costs:Record<string,number>={groups_observations:1,group_contains:1,contains_inventory_category:1,
  contains_inventory_item:1,has_public_inventory:1,investigates:1,reference_for_candidate:1,
  has_geographic_hypothesis:1,within_announced_prefix:1,announced_by:1,within_registered_range:1,
  matched_parent_registration:1,registered_to:1,maintained_by:1,registry_administered_by:1,
  has_registry_contact:1,geoip_estimates_location:1,resolves_to:1,owns_public_item:12,
  supported_by:15,published_on_domain:18,locally_compared_with:8}

export function hierarchy(nodes:GraphEntity[],edges:GraphRelation[],root:string){
  const byId=new Map(nodes.map(n=>[n.id,n])),adjacent=new Map<string,{id:string;edge:GraphRelation;cost:number}[]>()
  const add=(a:string,b:string,edge:GraphRelation,cost:number)=>{const list=adjacent.get(a)||[];list.push({id:b,edge,cost});adjacent.set(a,list)}
  for(const edge of edges){
    if(!byId.has(edge.from_id)||!byId.has(edge.to_id)||edge.from_id===edge.to_id)continue
    const child=byId.get(edge.to_id)!,explicit=child.attributes.parent_group_id
    const cost=explicit===edge.from_id? .1:costs[edge.relation_type]||4
    // Explicit collection membership wins over a shortcut from owner to item.
    add(edge.from_id,edge.to_id,edge,explicit&&explicit!==edge.from_id?cost+20:cost)
    add(edge.to_id,edge.from_id,edge,cost+40)
  }
  const parent=new Map<string,string>(),parentEdge=new Map<string,GraphRelation>(),distance=new Map<string,number>()
  const remaining=new Set(byId.keys());if(byId.has(root))distance.set(root,0)
  while(remaining.size){
    let current='',best=Infinity
    for(const id of remaining){const d=distance.get(id)??Infinity;if(d<best||(d===best&&id<current)){best=d;current=id}}
    if(!current)break
    remaining.delete(current)
    for(const next of adjacent.get(current)||[]){
      if(!remaining.has(next.id))continue
      const candidate=best+next.cost,previous=distance.get(next.id)??Infinity
      if(candidate<previous||(candidate===previous&&current<(parent.get(next.id)||'~'))){
        distance.set(next.id,candidate);parent.set(next.id,current);parentEdge.set(next.id,next.edge)
      }
    }
  }
  // Disconnected observations remain browseable, under the research scope only.
  for(const id of remaining)if(id!==root)parent.set(id,root)
  const children=new Map<string,string[]>(),depth=new Map<string,number>([[root,0]])
  for(const [child,ancestor]of parent){const list=children.get(ancestor)||[];list.push(child);children.set(ancestor,list)}
  for(const list of children.values())list.sort((a,b)=>{
    const x=byId.get(a)!,y=byId.get(b)!
    return Number(y.type==='entity_group')-Number(x.type==='entity_group')||Number(y.attributes.member_count||0)-Number(x.attributes.member_count||0)||x.label.localeCompare(y.label,'ru')||a.localeCompare(b)
  })
  const queue=[root];for(let i=0;i<queue.length;i++)for(const id of children.get(queue[i])||[]){depth.set(id,(depth.get(queue[i])||0)+1);queue.push(id)}
  const path=(id:string)=>{const result=[id],seen=new Set(result);while(parent.has(id)){id=parent.get(id)!;if(seen.has(id))break;seen.add(id);result.unshift(id)}return result}
  const treeEdges=[...parentEdge].map(([child,edge])=>({...edge,from_id:parent.get(child)!,to_id:child}))
  const primary=new Set(parentEdge.values()),crossEdges=edges.filter(edge=>!primary.has(edge))
  return {parent,children,depth,path,treeEdges,crossEdges}
}
