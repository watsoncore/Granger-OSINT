import {describe,it,expect} from 'vitest'
import {CanvasEditorDrafts,MAX_EDITOR_DRAFTS} from './canvas-editor-drafts'
import {CanvasMutations} from './canvas-mutations'
const doc='a'.repeat(32)
describe('bounded unsaved canvas editor text',()=>{
  it('freezes new editor intake when its shutdown provider captures the last accepted text',()=>{
    const drafts=new CanvasEditorDrafts(),owner=doc+'|ent_a'
    drafts.set(owner,{label:'Последняя правка',note:'До закрытия',dirty:true})
    const captured=drafts.prepareShutdown()
    expect(drafts.set(owner,{label:'Поздняя',note:'Во время закрытия',dirty:true})).toBe(false)
    expect(drafts.shutdownPrepared).toBe(true);expect(drafts.intentions()).toEqual(captured)
  })
  it('refuses a new owner at capacity while retaining every existing dirty note and allowing its edit',()=>{
    const drafts=new CanvasEditorDrafts()
    for(let i=0;i<MAX_EDITOR_DRAFTS;i++)expect(drafts.set(doc+'|ent_'+i,{label:'Объект '+i,note:'Текст '+i,dirty:true})).toBe(true)
    expect(drafts.set(doc+'|new',{label:'Не потерять',note:'Новая',dirty:true})).toBe(false)
    expect(drafts.intentions()).toHaveLength(MAX_EDITOR_DRAFTS);expect(drafts.get(doc+'|ent_0')?.note).toBe('Текст 0');expect(drafts.get(doc+'|ent_299')?.note).toBe('Текст 299')
    expect(drafts.set(doc+'|ent_0',{label:'Объект 0',note:'Исправление',dirty:true})).toBe(true)
    expect(drafts.clearMatching(doc+'|ent_0',{label:'Объект 0',note:'Текст 0'})).toBe(false)
    expect(drafts.clearMatching(doc+'|ent_0',{label:'Объект 0',note:'Исправление'})).toBe(true)
    expect(drafts.set(doc+'|new',{label:'Новая',note:'Сохранённое место',dirty:true})).toBe(true)
  })
  it('does not clear failed/discarded or newer text, and retains the exact accepted create until its matching ACK',()=>{
    const drafts=new CanvasEditorDrafts(),owner=doc+'|',text={label:'Домен',note:'Моя аннотация'}
    drafts.set(owner,{...text,dirty:true})
    const creating={op:'edit',target:doc,payload:{operation:'node',arguments:{type:'domain',label:'Домен',markdown:text.note}}}
    drafts.markPending(owner,text,creating);expect(drafts.intentions()).toEqual([creating])
    expect(drafts.finishPending(owner,text,false)).toBe(false);expect(drafts.get(owner)?.note).toBe(text.note)
    expect(drafts.intentions()[0].payload.arguments).toEqual({type:'analyst_note',label:'Домен',markdown:text.note})
    drafts.markPending(owner,text,creating);drafts.set(owner,{label:'Домен',note:'Новый текст после нажатия',dirty:true})
    expect(drafts.finishPending(owner,text,true)).toBe(false);expect(drafts.get(owner)?.note).toContain('Новый текст')
  })
  it('uses one accepted create receipt instead of adding a second recovery note for the same text',()=>{
    const drafts=new CanvasEditorDrafts(),owner=doc+'|',text={label:'example.org',note:'Ручная пометка'}
    const payload={operation:'node',arguments:{type:'domain',label:text.label,markdown:text.note}}
    drafts.set(owner,{...text,dirty:true});drafts.markPending(owner,text,{op:'edit',target:doc,payload})
    const queue=new CanvasMutations(()=>new Promise(()=>{}));queue.observe({id:doc,revision:1});queue.registerDraftProvider(drafts.intentions);void queue.send('edit',payload)
    const snapshot=queue.prepareShutdown();expect(snapshot.intents).toHaveLength(1);expect(snapshot.intents[0].payload).toEqual(payload)
  })
})
