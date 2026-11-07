import {expect,it} from 'vitest'
import {fitViewportWithin,nodeBox} from './graph-model'
import type {GraphEntity} from './types'

it('fits card bounds inside the area remaining below headers and beside docks',()=>{
  const nodes=[{id:'a',type:'username',label:'Тест',attributes:{}},{id:'b',type:'person',label:'Тест 2',attributes:{}}] as GraphEntity[]
  const points={a:{x:-200,y:-300},b:{x:600,y:700}}
  const insets={left:230,right:370,top:190,bottom:100}
  const view=fitViewportWithin(points,1280,800,nodes,insets)
  for(const node of nodes){
    const p=points[node.id as 'a'|'b'],box=nodeBox(node,view.scale)
    expect(p.x*view.scale+view.x-box.width/2).toBeGreaterThanOrEqual(insets.left)
    expect(p.x*view.scale+view.x+box.width/2).toBeLessThanOrEqual(1280-insets.right)
    expect(p.y*view.scale+view.y-box.height/2).toBeGreaterThanOrEqual(insets.top)
    expect(p.y*view.scale+view.y+box.height/2).toBeLessThanOrEqual(800-insets.bottom)
  }
})
