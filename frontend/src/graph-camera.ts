import type {GraphViewport} from './types'

export const sameViewport=(a:GraphViewport,b:GraphViewport)=>Math.abs(a.x-b.x)<.01&&Math.abs(a.y-b.y)<.01&&Math.abs(a.scale-b.scale)<.00001

/** Keep an interactive camera local until its asynchronous save is acknowledged.
 * Older ACKs and unrelated selection/evidence renders cannot rewind a gesture.
 * An explicit scope change creates a fresh controller in the renderer.
 */
export class GraphCamera {
  value:GraphViewport
  private pending:GraphViewport[]=[]
  private older:GraphViewport[]=[]
  private received:GraphViewport
  active=false
  constructor(initial:GraphViewport){this.value={...initial};this.received={...initial}}
  move(next:GraphViewport){this.value={...next}}
  commit(next=this.value){
    this.value={...next}
    if(!this.pending.some(row=>sameViewport(row,next)))this.pending.push({...next})
    if(this.pending.length>32)this.pending.shift()
    return {...this.value}
  }
  receive(incoming:GraphViewport){
    const repeated=sameViewport(incoming,this.received)
    this.received={...incoming}
    const index=this.pending.findIndex(row=>sameViewport(row,incoming))
    if(index>=0){
      this.older.push(...this.pending.splice(0,index+1))
      if(this.older.length>32)this.older.splice(0,this.older.length-32)
      if(!this.pending.length&&!this.active)this.value={...incoming}
      return
    }
    if(this.active||repeated||this.pending.length&&this.older.some(row=>sameViewport(row,incoming)))return
    // A previously committed snapshot is stale while a newer save is pending.
    if(this.pending.length)return
    this.value={...incoming}
  }
}
