import {act,fireEvent,render,screen} from '@testing-library/react'
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest'
import {InvestigationCanvas} from './components/InvestigationCanvas'
import type {GraphEntity,GraphPoint,GraphViewport} from './types'

const node:GraphEntity={id:'root',type:'blockchain_address',label:'UQ fixture wallet',attributes:{chain:'ton'},evidence_ids:[]}
let callbacks:Map<number,FrameRequestCallback>,nextFrame:number
const flush=()=>act(()=>{const batch=[...callbacks.values()];callbacks.clear();batch.forEach(callback=>callback(performance.now()))})

beforeEach(()=>{
  callbacks=new Map();nextFrame=0
  vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{callbacks.set(++nextFrame,callback);return nextFrame})
  vi.stubGlobal('cancelAnimationFrame',(id:number)=>callbacks.delete(id))
  vi.stubGlobal('PointerEvent',MouseEvent)
  const context=new Proxy({measureText:(value:string)=>({width:value.length*6})} as unknown as CanvasRenderingContext2D,{get(target,key){return Reflect.get(target,key)??(()=>{})}})
  vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue(context)
})
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals()})

describe('canvas asynchronous updates while interacting',()=>{
  const initial:GraphViewport={x:0,y:0,scale:1},positions:Record<string,GraphPoint>={root:{x:200,y:150}}
  const base={scopeKey:'document1',nodes:[node],edges:[],positions,viewport:initial,root:'root',selected:'',second:'',selectedEdge:'',onSelect:vi.fn(),onEdge:vi.fn(),onCommitPositions:vi.fn(),onViewport:vi.fn(),onResize:vi.fn()}
  it('does not let selection or evidence renders rewind an unacknowledged camera command',()=>{
    const {rerender}=render(<InvestigationCanvas {...base}/>);flush()
    const canvas=screen.getByRole('application')
    fireEvent.keyDown(canvas,{key:'ArrowRight'});flush();expect(canvas.dataset.panX).toBe('-40')
    rerender(<InvestigationCanvas {...base} selected="root" nodes={[{...node,attributes:{...node.attributes,media:{state:'ready'}}}]} edges={[]}/>);flush()
    expect(canvas.dataset.panX).toBe('-40')
    rerender(<InvestigationCanvas {...base} viewport={{x:-40,y:0,scale:1}}/>);flush()
    fireEvent.keyDown(canvas,{key:'ArrowRight'});flush()
    rerender(<InvestigationCanvas {...base} viewport={{x:-40,y:0,scale:1}} positions={{...positions}}/>);flush()
    expect(canvas.dataset.panX).toBe('-80')
    expect(JSON.parse(canvas.dataset.qaCameraFrames!).some((frame:{x:number;event:string})=>frame.x===-80&&frame.event==='commit')).toBe(true)
  })
  it('opens media on two ordinary pointer clicks while preserving the saved coordinates',()=>{
    const photo={...node,type:'image',attributes:{media:{id:'fixture',width:800,height:600}}}
    const saved={root:{x:240,y:180}},onOpenMedia=vi.fn(),onCreate=vi.fn()
    render(<InvestigationCanvas {...base} nodes={[photo]} positions={saved} onOpenMedia={onOpenMedia} onCreate={onCreate}/>)
    flush()
    const canvas=screen.getByRole('application')
    for(let index=0;index<2;index++){
      fireEvent.pointerDown(canvas,{button:0,clientX:240,clientY:180})
      fireEvent.pointerUp(canvas,{button:0,clientX:240,clientY:180})
    }
    expect(onOpenMedia).toHaveBeenCalledOnce()
    expect(onCreate).not.toHaveBeenCalled()
    expect(saved).toEqual({root:{x:240,y:180}})
  })
  it('preserves a local node drag through old position ACKs and accepts its saved position',()=>{
    const committed=vi.fn(),{rerender}=render(<InvestigationCanvas {...base} onCommitPositions={committed}/>);flush()
    const canvas=screen.getByRole('application')
    fireEvent.pointerDown(canvas,{button:0,clientX:200,clientY:150,pointerId:1})
    fireEvent.pointerMove(canvas,{clientX:260,clientY:190,pointerId:1});flush()
    rerender(<InvestigationCanvas {...base} onCommitPositions={committed} positions={{...positions}} selected="root"/>);flush()
    fireEvent.pointerUp(canvas,{clientX:260,clientY:190,pointerId:1});flush()
    expect(committed.mock.calls[0][0].root).toEqual({x:260,y:190,pinned:true})
    rerender(<InvestigationCanvas {...base} onCommitPositions={committed} positions={{root:{x:200,y:150}}}/>);flush()
    expect(JSON.parse(canvas.dataset.qaNodes!)[0]).toMatchObject({x:260,y:190})
    rerender(<InvestigationCanvas {...base} onCommitPositions={committed} positions={{root:{x:260,y:190,pinned:true}}}/>);flush()
    expect(JSON.parse(canvas.dataset.qaNodes!)[0]).toMatchObject({x:260,y:190})
  })
  it('draws a named glyph at 18 percent and resets local navigation only for a new document',()=>{
    const {rerender}=render(<InvestigationCanvas {...base} viewport={{x:100,y:100,scale:.18}}/>);flush()
    const canvas=screen.getByRole('application')
    expect(canvas.dataset.semanticZoom).toBe('far');expect(Number(canvas.dataset.drawnLabels)).toBe(1)
    expect(JSON.parse(canvas.dataset.qaNodes!)[0]).toMatchObject({width:110,height:42,label:'UQ fixture wallet'})
    fireEvent.keyDown(canvas,{key:'ArrowRight'});flush()
    rerender(<InvestigationCanvas {...base} scopeKey="document2"/>);flush()
    expect(canvas.dataset.panX).toBe('0');expect(canvas.dataset.zoom).toBe('1')
  })
  it('zooms a distant group into its original members instead of creating or editing a fake entity',()=>{
    const peers=[{...node,id:'peer1',label:'First peer'},{...node,id:'peer2',label:'Second peer'}],onViewport=vi.fn(),onSelect=vi.fn()
    render(<InvestigationCanvas {...base} nodes={[node,...peers]} positions={{root:{x:0,y:0},peer1:{x:900,y:0},peer2:{x:920,y:10}}} viewport={{x:100,y:100,scale:.18}} onViewport={onViewport} onSelect={onSelect}/>);flush()
    const canvas=screen.getByRole('application'),cluster=JSON.parse(canvas.dataset.qaFarClusters!)[0]
    expect(cluster.count).toBe(2)
    fireEvent.pointerDown(canvas,{button:0,clientX:cluster.x,clientY:cluster.y,pointerId:1});flush()
    expect(onViewport).toHaveBeenCalled();expect(Number(canvas.dataset.zoom)).toBeGreaterThanOrEqual(.62)
    expect(canvas.dataset.semanticZoom).not.toBe('far');expect(canvas.dataset.modelNodes).toBe('3');expect(onSelect).not.toHaveBeenCalled()
  })
})
