import {researchLayout} from './research-layout'
import type {GraphEntity,GraphPoint,GraphRelation} from './types'
self.onmessage=(event:MessageEvent<{nodes:GraphEntity[];edges:GraphRelation[];root:string;saved:Record<string,GraphPoint>;mode:string}>)=>{
  const p=event.data,start=performance.now()
  self.postMessage({positions:researchLayout(p.nodes,p.edges,p.root,p.saved,p.mode),duration_ms:performance.now()-start})
}
