import {describe,expect,it} from 'vitest'
import {CardIndex,nodeBox} from './graph-geometry'
import type {GraphEntity,GraphPoint,GraphViewport} from './types'

const nodes:GraphEntity[]=Array.from({length:1200},(_,index)=>({
  id:String(index),type:index%8?'blockchain_address':'image',label:'Object '+index,
  attributes:index%8?{}:{_card_size:{width:720,height:640}},evidence_ids:[],
}))
const positions:Record<string,GraphPoint>=Object.fromEntries(nodes.map((node,index)=>[
  node.id,{x:index%40*470-6000,y:Math.floor(index/40)*390-4500},
]))

describe('graph world index',()=>{
  it('retains every intersecting large card across zoom and translated cameras in paint order',()=>{
    const index=new CardIndex(nodes,positions),rect={left:0,top:0,right:920,bottom:630}
    const views:GraphViewport[]=[{x:0,y:0,scale:1},{x:420,y:-800,scale:2},{x:-1650,y:312,scale:.4},{x:300,y:200,scale:.03}]
    for(const view of views){
      const candidates=index.query(view,rect),ids=new Set(candidates.map(node=>node.id))
      const visible=nodes.filter(node=>{
        const point=positions[node.id],box=nodeBox(node,view.scale)
        const x=point.x*view.scale+view.x,y=point.y*view.scale+view.y
        return x+box.width/2>=0&&x-box.width/2<=rect.right&&y+box.height/2>=0&&y-box.height/2<=rect.bottom
      })
      for(const node of visible)expect(ids.has(node.id)).toBe(true)
      expect(candidates.map(node=>Number(node.id))).toEqual([...candidates].map(node=>Number(node.id)).sort((a,b)=>a-b))
    }
    expect(index.query(views[0],rect).length).toBeLessThan(nodes.length/4)
  })

  it('keeps an actively moved node pickable after it crosses world cells',()=>{
    const index=new CardIndex(nodes,positions),view={x:0,y:0,scale:1},point={left:150,top:150,right:150,bottom:150}
    positions['0']={x:150,y:150}
    expect(index.query(view,point,{'0':positions['0']}).some(node=>node.id==='0')).toBe(true)
  })
})
