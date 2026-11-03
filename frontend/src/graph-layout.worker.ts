import { layoutGraph } from './graph-model'
import { researchLayout } from './research-layout'
import type { GraphEntity,GraphRelation,GraphPoint } from './types'
self.onmessage=(event:MessageEvent<{id:number;nodes:GraphEntity[];edges:GraphRelation[];root:string;mode:'tree'|'graph';saved:Record<string,GraphPoint>;preserve:boolean;layout_mode?:string}>)=>{
  const started=performance.now(), value=event.data
  const positions=value.mode==='graph'&&value.layout_mode&&value.layout_mode!=='semantic'?
    researchLayout(value.nodes,value.edges,value.root,value.saved,value.layout_mode):layoutGraph(value.nodes,value.edges,value.root,value.mode,value.saved,value.preserve)
  self.postMessage({id:value.id,positions,duration_ms:performance.now()-started})
}
