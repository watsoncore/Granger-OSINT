import {useEffect,useSyncExternalStore} from 'react'
import {request,useDesktop,notify} from './bridge'
import {CanvasMutations,type PendingDraft} from './canvas-mutations'
import type {ResearchCanvasState} from './types'

// Keeps acknowledged writes and failed drafts alive when another Search view mounts.
const mutations=new CanvasMutations(request)
export const registerCanvasDraftProvider=mutations.registerDraftProvider
declare global {interface Window {grangerCanvasQueue?:{prepareShutdown:typeof mutations.prepareShutdown;snapshot:typeof mutations.exportPending}}}
window.grangerCanvasQueue={prepareShutdown:mutations.prepareShutdown,snapshot:mutations.exportPending}
let recoveryRequested=false
let recoveredDraftId=''
mutations.subscribe(()=>{
  if(recoveredDraftId&&mutations.getSnapshot().pending===0){
    const draft_id=recoveredDraftId;recoveredDraftId=''
    void request('research_canvas_queue_clear',{draft_id}).catch(()=>{recoveredDraftId=draft_id})
  }
})
export function useCanvasMutations(current?:ResearchCanvasState){
  const {connected}=useDesktop()
  useEffect(()=>{
    if(!connected||recoveryRequested)return
    recoveryRequested=true
    void request('research_canvas_queue_recovery').then(value=>{
      const draft=value as PendingDraft|null
      if(draft?.draft_id){
        if(mutations.restore(draft))recoveredDraftId=draft.draft_id
        else if(!draft.intents.length)void request('research_canvas_queue_clear',{draft_id:draft.draft_id})
        else notify('Сохранённая очередь предыдущего запуска оставлена в защищённом хранилище. Откройте приложение повторно, чтобы восстановить её перед новыми правками.')
      }
    }).catch(()=>{recoveryRequested=false})
  },[connected])
  useEffect(()=>mutations.observe(current?.document),[current?.document?.id,current?.document?.revision])
  const state=useSyncExternalStore(mutations.subscribe,mutations.getSnapshot)
  return {...state,send:mutations.send,edit:mutations.edit,retry:mutations.retry,discard:mutations.discard}
}
