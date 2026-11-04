import type {CanvasDraftIntent} from './canvas-mutations'
export interface CanvasEditorDraft {label:string;note:string;dirty:boolean}
export const MAX_EDITOR_DRAFTS=300
/** Unsaved user text stays in memory until explicit save or encrypted shutdown recovery. */
export class CanvasEditorDrafts {
  private values=new Map<string,CanvasEditorDraft>()
  private pending=new Map<string,{text:Pick<CanvasEditorDraft,'label'|'note'>;intent:CanvasDraftIntent}>()
  private closed=false
  get shutdownPrepared(){return this.closed}
  get(owner:string){return this.values.get(owner)}
  set(owner:string,draft:CanvasEditorDraft){
    if(this.closed||!this.values.has(owner)&&this.values.size>=MAX_EDITOR_DRAFTS)return false
    this.values.set(owner,draft);return true
  }
  clearMatching(owner:string,expected:Pick<CanvasEditorDraft,'label'|'note'>){
    const saved=this.values.get(owner)
    if(saved&&(saved.label!==expected.label||saved.note!==expected.note))return false
    this.values.delete(owner);this.pending.delete(owner);return true
  }
  markPending(owner:string,text:Pick<CanvasEditorDraft,'label'|'note'>,intent:CanvasDraftIntent){this.pending.set(owner,{text:{...text},intent})}
  finishPending(owner:string,text:Pick<CanvasEditorDraft,'label'|'note'>,committed:boolean){
    const pending=this.pending.get(owner)
    if(pending?.text.label===text.label&&pending?.text.note===text.note)this.pending.delete(owner)
    return committed&&this.clearMatching(owner,text)
  }
  intentions=():CanvasDraftIntent[]=>{
    const result:CanvasDraftIntent[]=[]
    for(const [owner,draft]of this.values){
      if(!draft.dirty)continue
      const separator=owner.indexOf('|'),target=owner.slice(0,separator),entity_id=owner.slice(separator+1)
      if(separator<0||!/^[a-f0-9]{32}$/.test(target))continue
      const pending=this.pending.get(owner)
      if(pending?.text.label===draft.label&&pending.text.note===draft.note){result.push(pending.intent);continue}
      if(entity_id)result.push({op:'edit',target,payload:{operation:'annotate',arguments:{entity_id,annotation:{label:draft.label,markdown:draft.note}}}})
      else if(draft.label||draft.note)result.push({op:'edit',target,payload:{operation:'node',arguments:{type:'analyst_note',label:draft.label||'Восстановленная заметка',markdown:draft.note}}})
    }
    return result
  }
  prepareShutdown=()=>{this.closed=true;return this.intentions()}
}
