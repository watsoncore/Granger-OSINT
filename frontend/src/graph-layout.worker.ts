import { layoutGraph } from './graph-model'
import type { GraphEntity,GraphRelation,GraphPoint } from './types'
self.onmessage=(event:MessageEvent<{id:number;nodes:GraphEntity[];edges:GraphRelation[];root:string;mode:'tree'|'graph';saved:Record<string,GraphPoint>;preserve:boolean}>)=>{
  const started=performance.now(), value=event.data
  const positions=layoutGraph(value.nodes,value.edges,value.root,value.mode,value.saved,value.preserve)
  self.postMessage({id:value.id,positions,duration_ms:performance.now()-started})
}
