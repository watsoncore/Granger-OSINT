// Benchmark the actual frontend algorithms, explicitly not native UI/FPS.
import {build} from '../frontend/node_modules/vite/dist/node/index.js'
import {mkdir,writeFile,access} from 'node:fs/promises'
import {resolve,join} from 'node:path'
import {pathToFileURL,fileURLToPath} from 'node:url'
const root=resolve(fileURLToPath(new URL('..',import.meta.url)))
const output=resolve(process.argv[2]||'output/investigation-workspace-v1/layout-benchmark')
try{await access(output);throw Error('Use a fresh benchmark directory')}catch(error){if(error.code!=='ENOENT')throw error}
await mkdir(output,{recursive:true})
await build({configFile:false,root:join(root,'frontend'),logLevel:'error',build:{outDir:output,emptyOutDir:false,minify:false,lib:{entry:join(root,'frontend/src/research-layout.ts'),formats:['es'],fileName:()=> 'layout.mjs'}}})
const {researchLayout}=await import(pathToFileURL(join(output,'layout.mjs')))
const report={origin:'source-algorithm-node',native:false,fps_measured:false,cases:[]}
for(const count of [50,100,500,1000,5000]){
  const nodes=Array.from({length:count},(_,i)=>({id:'n'+i,type:['person','image','blockchain_address','domain','entity_group'][i%5],label:'Synthetic '+i,attributes:{timestamp:i%4?'2026-11-03T00:00:00Z':null},evidence_ids:[]}))
  const edges=nodes.slice(1).map((node,i)=>({id:'e'+i,from_id:'n'+Math.floor(i/3),to_id:node.id,relation_type:'potentially_related',verification_status:'inferred',evidence_ids:[]}))
  const row={nodes:count,edges:edges.length,layouts:{}}
  for(const mode of ['hierarchical','radial','types','communities','timeline']){
    const samples=[]
    for(let i=0;i<5;i++){
      const started=performance.now(),result=researchLayout(nodes,edges,'n0',{n0:{x:-900,y:-800,pinned:true}},mode)
      samples.push(performance.now()-started)
      if(Object.keys(result).length!==count||result.n0.x!==-900||Object.values(result).some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y)))throw Error('Invalid layout')
    }
    samples.sort((a,b)=>a-b);row.layouts[mode]={median_ms:Number(samples[2].toFixed(3)),max_ms:Number(samples[4].toFixed(3))}
  }
  report.cases.push(row)
}
await writeFile(join(output,'benchmark.json'),JSON.stringify(report,null,2),'utf8')
console.log(JSON.stringify(report))
