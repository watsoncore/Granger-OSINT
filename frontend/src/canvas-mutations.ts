/** Acknowledged, document-bound writes. A failed intent stays available for retry. */
export type CanvasDocument = {id:string;revision:number}
type Transport=(action:string,payload:Record<string,unknown>)=>Promise<unknown>
type Ack={canvas_id?:string;revision?:number}
type Intent={op:string;payload:Record<string,unknown>;target?:string;token:string;waiters:Array<(value:unknown,retained?:boolean)=>void>}
export type CanvasDraftIntent=Pick<Intent,'op'|'payload'|'target'>
type DraftProvider=()=>CanvasDraftIntent[]
export type PendingDraft={draft_id?:string;intents:Array<Omit<Intent,'waiters'>>;current?:CanvasDocument;error?:string}
export type MutationState={pending:number;error:string}
const unbound=new Set(['new','open','list','import'])
const token=()=>crypto.randomUUID().replaceAll('-','')
const intentKey=(value:CanvasDraftIntent)=>JSON.stringify({op:value.op,target:value.target,payload:value.payload},(_,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item)

export class CanvasMutations {
  private queue:Intent[]=[]
  private running=false
  private failed:Error & {code?:string}|undefined
  private validationError=''
  private current:CanvasDocument|undefined
  private awaitingId:string|undefined
  private revisions=new Map<string,number>()
  private listeners=new Set<()=>void>()
  private snapshot:MutationState={pending:0,error:''}
  private accepting=true
  private prepared=false
  private draftProviders=new Set<DraftProvider>()
  private shutdownDrafts:Array<Omit<Intent,'waiters'>>=[]
  private shutdownAcknowledged=new Set<string>()
  private recoveredIntents=new WeakSet<Intent>()
  constructor(private transport:Transport){}
  subscribe=(listener:()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener)}}
  getSnapshot=()=>this.snapshot
  registerDraftProvider=(provider:DraftProvider)=>{this.draftProviders.add(provider);return()=>{this.draftProviders.delete(provider)}}
  exportPending=():PendingDraft=>{
    const intents=this.queue.map(({waiters:_,...intent})=>structuredClone(intent))
    if(this.prepared){const queued=new Set(intents.map(intent=>intent.token));for(const draft of this.shutdownDrafts)if(!queued.has(draft.token)&&!this.shutdownAcknowledged.has(draft.token)){intents.push(structuredClone(draft));queued.add(draft.token)}}
    return {intents,current:this.current,error:this.failed?.message||''}
  }
  prepareShutdown=()=>{
    if(!this.prepared){
      this.accepting=false;this.prepared=true
      const tokens=new Map(this.queue.map(intent=>[intentKey(intent),intent.token]))
      // Capture editor text once, without submitting it as an accepted mutation.
      for(const provider of this.draftProviders)for(const draft of provider()){
        const key=intentKey(draft),existing=tokens.get(key),identifier=existing||token()
        if(!existing){tokens.set(key,identifier);this.shutdownDrafts.push({...structuredClone(draft),token:identifier})}
        else if(!this.shutdownDrafts.some(saved=>saved.token===identifier))this.shutdownDrafts.push({...structuredClone(draft),token:identifier})
      }
    }
    void this.drain();return this.exportPending()
  }
  restore=(draft:PendingDraft)=>{
    if(this.queue.length||!Array.isArray(draft.intents)||!draft.intents.length)return false
    this.queue=draft.intents.map(intent=>({...intent,waiters:[]}))
    for(const intent of this.queue)this.recoveredIntents.add(intent)
    if(draft.current)this.observe(draft.current)
    this.failed=Object.assign(new Error('Восстановлены несохранённые действия. Загрузите актуальную версию и повторите после проверки.'),{code:'canvas_recovered'})
    this.publish();return true
  }
  private publish(){this.snapshot={pending:this.queue.length,error:this.failed?.message||this.validationError};this.listeners.forEach(f=>f())}
  observe(doc?:CanvasDocument){
    if(!doc)return
    this.revisions.set(doc.id,Math.max(doc.revision,this.revisions.get(doc.id)||0))
    // State snapshots are coalesced, and can arrive behind a completed open/new.
    if(this.awaitingId&&doc.id!==this.awaitingId)return
    if(this.awaitingId===doc.id)this.awaitingId=undefined
    this.current={id:doc.id,revision:this.revisions.get(doc.id)!}
  }
  send=(op:string,payload:Record<string,unknown>={},options:{rejectValidation?:boolean;rejectRetained?:boolean}={}):Promise<unknown>=>{
    if(!this.accepting)return Promise.resolve(null)
    const target=unbound.has(op)?undefined:String(payload.id||this.current?.id||'')
    if(!unbound.has(op)&&!target)return Promise.resolve(null)
    this.validationError=''
    return new Promise((resolve,reject)=>{
      const settle=(value:unknown,retained=false)=>{
        if(retained&&!options.rejectRetained)return
        if(value instanceof Error){
          if(options.rejectValidation||retained&&options.rejectRetained)reject(value)
          else resolve(null)
        }else resolve(value)
      }
      const last=this.queue.at(-1)
      // Merge only unsent position/view deltas, never text, evidence, tools or undo.
      const mergeable=op==='edit'&&['positions','view'].includes(String(payload.operation))
      if(mergeable&&last&&last!==this.queue[0]&&last.op===op&&last.target===target&&last.payload.operation===payload.operation){
        const key=payload.operation==='positions'?'positions':'view'
        const prev=last.payload.arguments as Record<string,Record<string,unknown>>
        const next=payload.arguments as Record<string,Record<string,unknown>>
        const merged={...prev?.[key],...next?.[key]}
        if(key==='view'&&(prev?.view?.ui||next?.view?.ui))merged.ui={...(prev?.view?.ui as object),...(next?.view?.ui as object)}
        if(key==='view'&&(prev?.view?.card_sizes||next?.view?.card_sizes))merged.card_sizes={...(prev?.view?.card_sizes as object),...(next?.view?.card_sizes as object)}
        last.payload={...last.payload,arguments:{...prev,...next,[key]:merged}}
        last.waiters.push(settle)
      }else this.queue.push({op,payload:{...payload},target,token:token(),waiters:[settle]})
      this.publish();void this.drain()
    })
  }
  edit=(operation:string,args:Record<string,unknown>,options:{rejectValidation?:boolean;rejectRetained?:boolean}={})=>this.send('edit',{operation,arguments:args},options)
  private async drain(){
    if(this.running||this.failed)return
    this.running=true
    while(this.queue.length&&!this.failed){
      const intent=this.queue[0]
      try{
        if(intent.target&&intent.target!==this.current?.id)throw Object.assign(new Error('Изменение относится к другому расследованию. Откройте его перед повторением.'),{code:'canvas_target_changed'})
        const payload={...intent.payload,await_commit:true,mutation_id:intent.token,...(intent.target?{id:intent.target,revision:this.revisions.get(intent.target)||0}:{})}
        const value=await this.transport('research_canvas_'+intent.op,payload)
        const ack=value as Ack|null
        if(ack?.canvas_id&&typeof ack.revision==='number'){
          this.revisions.set(ack.canvas_id,Math.max(ack.revision,this.revisions.get(ack.canvas_id)||0))
          this.current={id:ack.canvas_id,revision:this.revisions.get(ack.canvas_id)!}
          if(!intent.target)this.awaitingId=ack.canvas_id
        }
        if(this.prepared)this.shutdownAcknowledged.add(intent.token)
        this.queue.shift();intent.waiters.forEach(f=>f(value));this.publish()
      }catch(error){
        const failure=error instanceof Error?error:new Error('Не удалось сохранить изменение.')
        if(['canvas_validation_failed','invalid_request','analyst_canvas_invalid_operation','payload_too_large']
          .includes((failure as Error&{code?:string}).code||'')&&!this.recoveredIntents.has(intent)){
          this.queue.shift()
          this.validationError=failure.message
          intent.waiters.forEach(settle=>settle(failure))
        }else{
          this.failed=failure
          intent.waiters.forEach(settle=>settle(failure,true))
        }
        this.publish()
      }
    }
    this.running=false
  }
  retry=async()=>{
    if(this.running||!this.failed||!this.queue.length)return
    const intent=this.queue[0]
    if(['analyst_canvas_revision_conflict','canvas_recovered','canvas_target_changed'].includes(this.failed.code||'')){
      // Only the explicit retry button permits rebasing a retained semantic delta.
      this.running=true
      try{
        if(!intent.target)throw new Error('Откройте нужное расследование; неповторённое действие можно убрать из очереди.')
        const ack=await this.transport('research_canvas_open',{id:intent.target,await_commit:true,mutation_id:token()}) as Ack
        if(!ack?.canvas_id||typeof ack.revision!=='number')throw new Error('Актуальная версия не загружена.')
        this.current={id:ack.canvas_id,revision:ack.revision};this.revisions.set(ack.canvas_id,ack.revision);this.awaitingId=ack.canvas_id
        // A real failed CAS reply is cached by the live bridge. Recovered or
        // unsent cross-project intentions retain their original receipt token.
        if(this.failed.code==='analyst_canvas_revision_conflict')intent.token=token()
      }catch(error){this.failed=error instanceof Error?error:new Error('Не удалось загрузить версию.');this.publish();return}
      finally{this.running=false}
    }
    this.failed=undefined;this.publish();void this.drain()
  }
  discard=()=>{
    if(this.running||!this.failed)return
    const intent=this.queue.shift();intent?.waiters.forEach(f=>f(null));this.failed=undefined;this.publish();void this.drain()
  }
}
