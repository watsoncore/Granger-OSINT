import type {GraphEntity,GraphPoint,GraphRelation} from './types'
import {addGraphAmounts} from './graph-money'
import {nodeBox} from './graph-geometry'

export interface SemanticCluster {id:string;members:string[]}
export function semanticBand(scale:number) {
  return .38*2**Math.ceil(Math.log2(Math.max(scale,.001)/.38))
}

/** A zoom-only spatial representation. It never edits the analytical model.
 * Cells are anchored in world coordinates, so panning cannot regroup objects.
 * A cluster click zooms into original members; root/selection are never hidden.
 */
export function semanticGraph(nodes:GraphEntity[],edges:GraphRelation[],positions:Record<string,GraphPoint>,scale:number,protectedIds:Set<string>){
  if(scale>=.38)return {nodes,edges,positions,clusters:[] as SemanticCluster[]}
  const band=semanticBand(scale),cellWidth=154/band,cellHeight=68/band,cells=new Map<string,GraphEntity[]>(),mapped=new Map<string,string>(),display:GraphEntity[]=[],clusters:SemanticCluster[]=[],located={...positions},byId=new Map(nodes.map(node=>[node.id,node]))
  for(const node of nodes){const point=positions[node.id];if(!point||protectedIds.has(node.id)){display.push(node);mapped.set(node.id,node.id);continue}
    const key=`${Math.round(point.x/cellWidth)},${Math.round(point.y/cellHeight)}`,rows=cells.get(key)||[];rows.push(node);cells.set(key,rows)
  }
  for(const [key,rows]of cells){
    if(rows.length===1){display.push(rows[0]);mapped.set(rows[0].id,rows[0].id);continue}
    const id='far_'+key,counts=new Map<string,number>()
    for(const node of rows){mapped.set(node.id,id);counts.set(node.type,(counts.get(node.type)||0)+1)}
    const members=rows.map(node=>node.id),point={x:rows.reduce((sum,node)=>sum+positions[node.id].x,0)/rows.length,y:rows.reduce((sum,node)=>sum+positions[node.id].y,0)/rows.length}
    located[id]=point;clusters.push({id,members})
    display.push({id,type:'entity_group',label:`${rows.length} объектов`,attributes:{member_count:rows.length,semantic_cluster:true,type_counts:Object.fromEntries(counts),description:'Нажмите, чтобы приблизить исходные объекты'},evidence_ids:[...new Set(rows.flatMap(node=>node.evidence_ids))],verification_status:'unverified'})
  }
  // Keep the root visible before placing the other selected and grouped glyphs.
  // These offsets are local to the far projection.
  // Place against the low end of the zoom band. Zoom within the band keeps
  // stable world positions and adds clearance without recomputing clusters.
  const layoutScale=Math.max(.001,band/2),placed=new Set<string>()
  const displayById=new Map(display.map(node=>[node.id,node]))
  const boxes=new Map(display.map(node=>[node.id,nodeBox(node,layoutScale)]))
  const width=Math.max(126,...[...boxes.values()].map(box=>box.width+14))
  const height=Math.max(54,...[...boxes.values()].map(box=>box.height+10))
  const cellsByGlyph=new Map<string,{x:number;y:number;width:number;height:number}[]>()
  const cell=(point:GraphPoint)=>[Math.floor(point.x*layoutScale/width),Math.floor(point.y*layoutScale/height)]
  function overlaps(point:GraphPoint,box:{width:number;height:number}){
    const [x,y]=cell(point)
    for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++){
      const near=cellsByGlyph.get(`${x+dx},${y+dy}`)||[]
      if(near.some(other=>Math.abs(point.x-other.x)*layoutScale<(box.width+other.width)/2+6&&
          Math.abs(point.y-other.y)*layoutScale<(box.height+other.height)/2+5))return true
    }
    return false
  }
  for(const id of [...protectedIds,...displayById.keys()]){
    const base=located[id],box=boxes.get(id)
    if(!base||!box||placed.has(id))continue
    let point=base
    if(overlaps(base,box)){
      search:for(let ring=1;ring<=Math.ceil(Math.sqrt(display.length))+2;ring++){
        for(let dy=-ring;dy<=ring;dy++)for(let dx=-ring;dx<=ring;dx++){
          if(Math.max(Math.abs(dx),Math.abs(dy))!==ring)continue
          const next={x:base.x+dx*width/layoutScale,y:base.y+dy*height/layoutScale}
          if(!overlaps(next,box)){point=next;break search}
        }
      }
    }
    located[id]=point;placed.add(id)
    const key=cell(point).join(','),neighbors=cellsByGlyph.get(key)||[]
    neighbors.push({...point,...box});cellsByGlyph.set(key,neighbors)
  }
  const grouped=new Map<string,GraphRelation[]>(),direct:GraphRelation[]=[]
  for(const edge of edges){const from=mapped.get(edge.from_id),to=mapped.get(edge.to_id);if(!from||!to||from===to)continue
    if(from===edge.from_id&&to===edge.to_id){direct.push(edge);continue}
    const key=JSON.stringify([from,to,edge.relation_type,edge.direction,edge.aggregate?.asset_key,byId.get(edge.from_id)?.attributes.chain,byId.get(edge.to_id)?.attributes.chain,edge.aggregate?.asset,edge.aggregate?.contract,edge.aggregate?.asset_label]),rows=grouped.get(key)||[];rows.push(edge);grouped.set(key,rows)
  }
  for(const [key,rows]of grouped){const first=rows[0],from=mapped.get(first.from_id)!,to=mapped.get(first.to_id)!
    direct.push({...first,id:'far_edge_'+key,from_id:from,to_id:to,evidence_ids:[...new Set(rows.flatMap(edge=>edge.evidence_ids))],attributes:{...first.attributes,semantic_relation_count:rows.length},...(first.aggregate?{aggregate:{...first.aggregate,count:rows.reduce((sum,edge)=>sum+(edge.aggregate?.count||0),0),amount:addGraphAmounts(rows.map(edge=>edge.aggregate?.amount)),transaction_ids:[...new Set(rows.flatMap(edge=>edge.aggregate?.transaction_ids||[]))],known_amount_count:rows.reduce((sum,edge)=>sum+(edge.aggregate?.known_amount_count||0),0),unknown_amount_count:rows.reduce((sum,edge)=>sum+(edge.aggregate?.unknown_amount_count||0),0)}}:{})})
  }
  return {nodes:display,edges:direct,positions:located,clusters}
}
