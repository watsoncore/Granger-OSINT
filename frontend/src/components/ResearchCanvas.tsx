import {useEffect,useMemo,useRef,useState} from 'react'
import {Plus,Undo2,Redo2,FolderOpen,Network,ImagePlus,Download,Upload,Copy,Link,Search,Pin,PanelRightClose,PanelRightOpen,Expand,Minus,X,List,MousePointer2,LayoutGrid,Maximize2,Layers,SlidersHorizontal} from 'lucide-react'
import {act,notify} from '../bridge'
import {useCanvasMutations,registerCanvasDraftProvider} from '../useCanvasMutations'
import {CanvasEditorDrafts,MAX_EDITOR_DRAFTS} from '../canvas-editor-drafts'
import type {DesktopState,GraphEntity,GraphPoint,GraphRelation,GraphView,Source,Verification} from '../types'
import {entityLabel,indexGraph,typeLabels,verificationLabels,visibleGraph,counterpartySummary} from '../graph-model'
import {cardSize,mediaCardSize,withCardPresentation} from '../graph-cards'
import {InvestigationCanvas,type GraphCanvasHandle} from './InvestigationCanvas'
import {StructuredToolFields,parseToolArguments} from './StructuredToolFields'
import {GansarFields,type CryptoCapability} from './GansarFields'
import {EntityActions} from './EntityActions'
import {EntityComposer} from './EntityComposer'
import {ResearchResults} from './ResearchResults'
import {RelationComposer} from './RelationComposer'
import {WorkspaceLayer} from './WorkspaceLayer'
import {SearchableSelect} from './SearchableSelect'
import {MaigretFields} from './MaigretFields'
import {MediaViewer,NodeMedia} from './MediaViewer'
import {MediaImport} from './MediaImport'
import type {SearchDestination} from './WorkspaceNavigation'
import {linkedMedia,loadThumbnail,prepareImage,type ImageInput} from '../canvas-media'
import {Button,Badge} from './ui'
import {Markdown} from './Markdown'
import {GraphOverview,GraphAnalyticalIndex,CounterpartyFlows,FlowTransactions} from './GraphAnalyticalIndex'
import {researchLayout} from '../research-layout'
import '../research-canvas.css'

const analyticalModes=new Set(['wallet','flow','counterparties','paths'])
const labels:Record<string,string>={...typeLabels,person:'Личность (утверждение)',analyst_note:'Заметка',hypothesis:'Гипотеза',custom_entity:'Свой объект',document:'Документ',contract:'Контракт',nft:'NFT',collection:'Коллекция',token:'Токен',infrastructure_asset:'IP / сеть',blockchain_address:'Криптокошелёк'}
const graphModes={wallet:'Кошельки и потоки',assets:'NFT и активы',flow:'Движение средств',counterparties:'Контрагенты',transactions:'Транзакции',paths:'Исследование связей',socmint:'Публичные профили',manual:'Все объекты'}
const propertyNames:Record<string,string>={address:'Адрес',chain:'Сеть',value:'Значение',url:'Публичная ссылка',username:'Идентификатор',tx_hash:'Хеш транзакции',from_address:'Отправитель',to_address:'Получатель',status:'Статус источника',amount:'Сумма',asset:'Актив',timestamp:'Время',transaction_count:'Операции по данным источника',counterparty_count:'Контрагенты по данным источника',first_seen:'Начало периода',last_seen:'Конец периода',member_count:'Объектов',description:'Описание',labels:'Метки источников',organization:'Организация',country:'Страна',latitude:'Широта',longitude:'Долгота'}
const valueText=(value:unknown)=>typeof value==='object'?JSON.stringify(value):String(value??'')
const editorDrafts=new CanvasEditorDrafts()
registerCanvasDraftProvider(editorDrafts.prepareShutdown)

export function ResearchCanvas({state,onSource,active=false,destination,onDestinationHandled}:{
  state:DesktopState;onSource(source:Source):void;active?:boolean
  destination?:SearchDestination;onDestinationHandled?(destination:SearchDestination):void
}){
  const [pendingPosition,setPendingPosition]=useState<GraphPoint>(),[menu,setMenu]=useState<{id:string;x:number;y:number}|null>(null)
  const [expanded,setExpanded]=useState(false),[editorVisible,setEditorVisible]=useState(false),[tab,setTab]=useState<'details'|'evidence'|'actions'>('details')
  const [open,setOpen]=useState(active),[selection,setSelection]=useState<string[]>([]),[edgeId,setEdgeId]=useState('')
  const [label,setLabel]=useState(''),[description,setDescription]=useState(''),[note,setNote]=useState(''),[dirty,setDirty]=useState(false)
  const [composerVersion,setComposerVersion]=useState(0)
  const [draftNotice,setDraftNotice]=useState('')
  const [edgeType,setEdgeType]=useState('potentially_related'),[filter,setFilter]=useState(''),[typeFilter,setTypeFilter]=useState(''),[statusFilter,setStatusFilter]=useState(''),[sourceFilter,setSourceFilter]=useState(''),[showSources,setShowSources]=useState(false)
  const [tool,setTool]=useState(''),[draft,setDraft]=useState<Record<string,string>>({}),[toolError,setToolError]=useState(''),[capability,setCapability]=useState<CryptoCapability>()
  const [limit,setLimit]=useState(100),[mediaNode,setMediaNode]=useState<GraphEntity|null>(null),[size,setSize]=useState({width:800,height:500})
  const [importTarget,setImportTarget]=useState<GraphEntity|null|undefined>(undefined)
  const [importBusy,setImportBusy]=useState(false),[importError,setImportError]=useState('')
  const importing=useRef(false)
  const [fitTick,setFitTick]=useState(0)
  const [dismissedInsertion,setDismissedInsertion]=useState('')
  const [analyticalIds,setAnalyticalIds]=useState<string[]>([]),[indexOpen,setIndexOpen]=useState(false)
  const [overviewOpen,setOverviewOpen]=useState(false),[controlsOpen,setControlsOpen]=useState(false)
  const [connection,setConnection]=useState<{from:string;to:string;relation?:GraphRelation}|null>(null)
  const initialLayout=useRef('')
  const pendingFit=useRef<{owner:string;revision:number;generation:number}|undefined>(undefined)
  const canvas=useRef<GraphCanvasHandle>(null),worker=useRef<Worker|undefined>(undefined),clipboard=useRef<string[]>([]),generation=useRef(0),pendingLayout=useRef(''),resize=useRef<{x:number;width:number}|undefined>(undefined)
  const current=state.research_canvas,doc=current?.document,busy=!!current?.busy
  const {send,edit,pending,error,retry,discard}=useCanvasMutations(current)
  const latest=useRef(doc);latest.current=doc
  async function importImage(input:ImageInput,target?:string,position?:GraphPoint,fromDialog=false){
    const id=latest.current?.id
    if(!id||importing.current)return
    importing.current=true
    setImportBusy(true);setImportError('')
    try{
      const image=await prepareImage(input)
      if(!image)return
      if(latest.current?.id!==id)throw new Error('Исходное расследование закрыто. Откройте его и повторите добавление.')
      const anchor=position||(!target?canvas.current?.insertPoint?.(mediaCardSize(image.width,image.height)):undefined)
      if(fromDialog)setImportTarget(undefined)
      void send('attach',{id,attachment_id:image.id,entity_id:target,position:anchor,provenance:image.provenance})
    }catch(reason){
      const error=reason as Error & {code?:string}
      if(input.mode==='clipboard'&&!fromDialog&&error.code==='canvas_clipboard_empty'&&clipboard.current.length){
        void send('edit',{id,operation:'duplicate_nodes',arguments:{ids:clipboard.current}})
      }else if(fromDialog)setImportError(error.message)
      else notify(error.message)
    }finally{importing.current=false;setImportBusy(false)}
  }
  const dirtyRef=useRef(false),draftOwner=useRef('');dirtyRef.current=dirty
  useEffect(()=>{if(active)setOpen(true)},[active])
  useEffect(()=>{
    if(!destination||!active||busy)return
    onDestinationHandled?.(destination)
    if(destination.create)void send('new',{title:'Новое расследование'})
    else if(destination.id&&destination.id!==doc?.id)void send('open',{id:destination.id})
  },[destination,active,busy,doc?.id,onDestinationHandled,send])
  useEffect(()=>{if(open&&!current)void send('list')},[open,current])
  useEffect(()=>{pendingFit.current=undefined;pendingLayout.current='';setSelection([]);setEdgeId('');setDirty(false);setMediaNode(null);setEditorVisible(false);setIndexOpen(false);setOverviewOpen(false);setConnection(null);setTab(doc?.view.ui?.inspector_tab||'details');generation.current++;worker.current?.terminate()},[doc?.id])
  useEffect(()=>()=>worker.current?.terminate(),[])
  const allNodes=useMemo<GraphEntity[]>(()=>{
    if(!doc)return []
    const nodes=new Map(doc.entities.map(n=>[n.id,n]))
    return [...doc.entities.map(node=>node.type==='entity_group'&&doc.view.collapsed.includes(node.id)?{...node,attributes:{...node.attributes,_collapsed:true}}:node),...Object.entries(doc.view.instances||{}).flatMap(([id,v])=>{const node=nodes.get(v.entity_id);return node?[{...node,id,attributes:{...node.attributes,visual_instance_of:v.entity_id,parent_group_id:v.parent_group_id}}]:[]})]
  },[doc?.entities,doc?.view.instances,doc?.view.collapsed])
  const positions=useMemo(()=>({...doc?.view.positions,...Object.fromEntries(Object.entries(doc?.view.instances||{}).map(([id,v])=>[id,v.position]))}),[doc?.view.positions,doc?.view.instances])
  const edges=useMemo(()=>doc?.relations.map(e=>({...e,from_id:String(e.attributes?.visual_from_id||e.from_id),to_id:String(e.attributes?.visual_to_id||e.to_id)}))||[],[doc?.relations])
  const index=useMemo(()=>indexGraph(allNodes,edges),[allNodes,edges]),selected=index.byId.get(selection[0]),relation=doc?.relations.find(e=>e.id===edgeId)
  const primary=allNodes.find(n=>n.id===(doc?.view.ui?.graph_mode==='socmint'?doc?.view.ui?.username_root_id:doc?.view.ui?.crypto_root_id))||allNodes.find(n=>n.attributes.is_root===true)||allNodes[0],root=primary?.id||''
  const cryptoInvestigation=primary?.type==='blockchain_address'&&(primary.evidence_ids.length>0||edges.some(edge=>!!edge.aggregate))
  const graphMode=doc?.view.ui?.graph_mode||(cryptoInvestigation?'wallet':'manual'),cardMode=doc?.view.ui?.card_mode||'auto'
  const analytical=graphMode==='socmint'||['wallet','flow','counterparties'].includes(graphMode)
  const selectedCounterparty=useMemo(()=>selected?counterpartySummary(allNodes,edges,root,selected.id):undefined,[allNodes,edges,root,selected?.id])
  useEffect(()=>{setLimit(5000);initialLayout.current=''},[doc?.id,graphMode])
  useEffect(()=>{
    const fit=pendingFit.current
    if(!fit||doc?.id!==fit.owner||doc.revision<fit.revision)return
    pendingFit.current=undefined
    requestAnimationFrame(()=>{if(generation.current===fit.generation&&latest.current?.id===fit.owner)canvas.current?.fit()})
  },[doc?.revision,doc?.id,fitTick])
  const ui=(patch:NonNullable<NonNullable<typeof doc>['view']['ui']>)=>void edit('view',{view:{ui:patch}})
  const showTab=(next:typeof tab)=>{setTab(next);setEditorVisible(true);ui({inspector_tab:next,inspector_open:true})}
  const showInspector=(value:boolean)=>{setEditorVisible(value);ui({inspector_open:value})}
  useEffect(()=>{
    const owner=(doc?.id||'')+'|'+(selection[0]||'')
    if(draftOwner.current!==owner||!dirtyRef.current){const saved=editorDrafts.get(owner);setNote(saved?.dirty?saved.note:doc?.annotations[selection[0]]?.markdown||String(selected?.attributes.markdown||''));setLabel(saved?.dirty?saved.label:doc?.annotations[selection[0]]?.label||selected?.label||'');setDirty(!!saved?.dirty);draftOwner.current=owner}
  },[selection[0],doc?.id,doc?.revision])
  const changeDraft=(patch:{label?:string;note?:string})=>{const next={label:patch.label??label,note:patch.note??note,dirty:true};if(!editorDrafts.set((doc?.id||'')+'|'+(selection[0]||''),next)){setDraftNotice(editorDrafts.shutdownPrepared?'Приложение закрывается. Новые правки больше не принимаются; принятый текст сохранён для защищённого восстановления.':`Достигнут лимит ${MAX_EDITOR_DRAFTS} несохранённых заметок. Сохраните существующую заметку перед редактированием нового объекта. Все прежние черновики оставлены без изменений.`);return}setDraftNotice('');setLabel(next.label);setNote(next.note);setDirty(true)}
  const saveEditor=(operation:string,args:Record<string,unknown>)=>{const owner=(doc?.id||'')+'|'+(selection[0]||''),snapshot={label,note};editorDrafts.markPending(owner,snapshot,{op:'edit',target:doc?.id,payload:{operation,arguments:args}});void edit(operation,args).then(value=>{if(editorDrafts.finishPending(owner,snapshot,!!value)&&draftOwner.current===owner){setDirty(false);setDraftNotice('')}})}
  const saveNote=()=>selected?saveEditor('annotate',{entity_id:selected.id,annotation:{label,markdown:note}}):saveEditor('node',{type:'analyst_note',label:label||'Заметка',markdown:note})
  const options=state.tools.find(t=>t.id===tool),schema=options?.manifest?.input_schema
  const targetKey=JSON.stringify([doc?.id,selected?.id,selected?.type,...['username','address','value','url','attachment_id','chain','network','platform','asset_type','contract','collection','asset_id','latitude','longitude','coordinates','profile','target','email','phone','domain','place'].map(key=>selected?.attributes[key])])
  const toolReadiness=JSON.stringify(state.tools.map(item=>[item.id,item.available,item.state,item.reason]))
  const targetOwner=useRef(targetKey)
  useEffect(()=>{targetOwner.current=targetKey;setTool('');setDraft({});setCapability(undefined);setToolError('')},[targetKey])
  useEffect(()=>{
    setCapability(undefined);if(!selected||!doc)return
    let alive=true
    const owner=targetKey
    void act('research_canvas_capability',{id:doc.id,entity_id:selected.id,chain:draft.chain||'auto'}).then(value=>{
      if(!alive||targetOwner.current!==owner)return
      if(!value||typeof value!=='object'){setCapability({reason:'Проверка совместимости недоступна. Выберите объект повторно.',tools:[]});return}
      const cap=value as CryptoCapability;setCapability(cap)
      setTool(previous=>cap.tools?.some(item=>item.id===previous&&item.compatible&&item.available!==false)?previous:'')
    }).catch(()=>{if(alive)setCapability({reason:'Проверка совместимости недоступна.',tools:[]})})
    return()=>{alive=false}
  },[targetKey,draft.chain,toolReadiness])
  const chooseTool=(id:string)=>{
    const item=capability?.tools?.find(item=>item.id===id)
    if(!item?.compatible||item.available===false)return
    setTool(id);setDraft(Object.fromEntries(Object.entries(item.arguments||{}).map(([key,value])=>[key,String(value)])));setToolError('')
  }
  const display=useMemo(()=>{
    if(!doc)return {nodes:[] as GraphEntity[],edges:[] as GraphRelation[],all:0,hiddenRelations:0}
    const hidden=new Set([...doc.view.hidden,...doc.view.removed]),collapsed=new Set(doc.view.collapsed)
    const candidates=allNodes.filter(node=>{if(hidden.has(node.id))return false;let parent=String(node.attributes.parent_group_id||'');const visited=new Set<string>();while(parent&&!visited.has(parent)){visited.add(parent);if(hidden.has(parent)||collapsed.has(parent))return false;parent=String(index.byId.get(parent)?.attributes.parent_group_id||'')}return true})
    const view:GraphView={version:1,mode:'graph',projection_mode:graphMode,selected_id:selection[0],selected_relation:edgeId,query:filter,expanded:Array.from(new Set([...(doc.view.expanded||[]),...candidates.filter(node=>node.type==='entity_group'&&!collapsed.has(node.id)&&(graphMode==='manual'||node.attributes.origin==='analyst')).map(node=>node.id)])),expanded_relations:doc.view.expanded_relations||[],collapsed:[],filters:{types:typeFilter?[typeFilter]:undefined,statuses:statusFilter?[statusFilter as Verification]:undefined,sources:sourceFilter?[sourceFilter]:undefined,show_sources:showSources||graphMode==='manual',show_transactions:graphMode==='transactions'||graphMode==='manual',include_background:graphMode==='manual',...(analytical&&indexOpen?graphMode==='socmint'?{profile_ids:analyticalIds}:{peer_ids:analyticalIds}:{})}}
    const projected=visibleGraph(candidates,edges,root,view,limit)
    const visible=new Set(projected.nodes.map(node=>node.id))
    const photographs=analytical&&!filter&&!typeFilter&&!statusFilter&&!sourceFilter?candidates.filter(node=>
      node.type==='image'&&node.attributes.original_image===true&&!visible.has(node.id)):[]
    return {nodes:[...projected.nodes,...photographs].map(node=>{const a=doc.annotations[node.id];return a?{...node,label:a.label||node.label,attributes:{...node.attributes,markdown:a.markdown||node.attributes.markdown,analyst_color:a.color}}:node}),edges:projected.edges,all:projected.available+photographs.length,hiddenRelations:projected.hiddenRelations}
  },[doc?.annotations,doc?.view.hidden,doc?.view.removed,doc?.view.collapsed,doc?.view.expanded,doc?.view.expanded_relations,allNodes,edges,index,filter,typeFilter,statusFilter,sourceFilter,limit,selection[0],edgeId,root,graphMode,showSources,analyticalIds,analytical,indexOpen])
  const renderPositions=useMemo(()=>{
    if(!analytical||!indexOpen||!doc||doc.view.layout==='manual'||!analyticalIds.length)return positions
    const pageIds=new Set([root,...analyticalIds])
    const pageNodes=withCardPresentation(display.nodes.filter(node=>pageIds.has(node.id)),doc.view.card_sizes,cardMode)
    const pageEdges=display.edges.filter(edge=>pageIds.has(edge.from_id)&&pageIds.has(edge.to_id))
    // Page and address filters change presentation only. A typed address must
    // not enqueue new encrypted revisions, camera fits or worker jobs.
    const pagePositions=researchLayout(pageNodes,pageEdges,root,positions,doc.view.layout)
    const projected={...positions,...pagePositions}
    const transactions=withCardPresentation(display.nodes.filter(node=>node.type==='transaction'&&!positions[node.id]?.pinned),doc.view.card_sizes,cardMode)
      .sort((a,b)=>a.id.localeCompare(b.id))
    if(transactions.length){
      const right=Math.max(...pageNodes.map(node=>(projected[node.id]?.x||0)+cardSize(node).width/2),0)
      const width=Math.max(...transactions.map(node=>cardSize(node).width))
      const height=Math.max(...transactions.map(node=>cardSize(node).height))
      const rows=Math.min(4,transactions.length)
      const centerY=projected[root]?.y||0
      transactions.forEach((node,index)=>{
        projected[node.id]={
          x:right+72+width/2+Math.floor(index/rows)*(width+55),
          y:centerY+(index%rows-(rows-1)/2)*(height+42),
        }
      })
    }
    return projected
  },[analytical,indexOpen,analyticalIds,root,doc?.view.layout,doc?.view.card_sizes,display.nodes,display.edges,positions,cardMode])
  const attempted=useRef(new Set<string>())
  useEffect(()=>{if(!doc)return;const node=display.nodes.filter(n=>n.attributes.media).slice(0,8).find(n=>{const m=n.attributes.media as Record<string,unknown>;return m.id&&m.kind!=='local_attachment'&&!['ready','loading','unavailable'].includes(String(m.state))&&!attempted.current.has(doc.id+'|'+n.id)});if(node){attempted.current.add(doc.id+'|'+node.id);void send('media',{entity_id:node.id})}},[doc?.id,display.nodes])
  const create=async(args:Record<string,unknown>)=>{const accepted=await edit('node',{...args,...(pendingPosition?{position:pendingPosition}:{})});if(!accepted)throw new Error('Сохранение не подтверждено. Проверьте сообщение над полотном; введённые значения оставлены в форме.');setPendingPosition(undefined);return accepted}
  const uiCollapsed=(id:string)=>void edit('view',{view:{collapsed:doc?.view.collapsed.includes(id)?doc.view.collapsed.filter(value=>value!==id):[...(doc?.view.collapsed||[]),id]}})
  const connect=(a:string,b:string)=>{if(a!==b)setConnection({from:a,to:b})}
  const expandNode=(id:string)=>{const d=latest.current;if(d)void edit('view',{view:{expanded:Array.from(new Set([...(d.view.expanded||[]),id])),collapsed:d.view.collapsed.filter(value=>value!==id)}})}
  const newNode=(position?:GraphPoint)=>{setPendingPosition(position);setComposerVersion(value=>value+1);setSelection([]);setEdgeId('');setLabel('');setNote('');setDirty(false);showTab('details');setTimeout(()=>document.querySelector<HTMLInputElement>('[data-entity-input]')?.focus(),0)}
  const layout=(mode:string,force=false)=>{
    if(!doc)return
    worker.current?.terminate()
    const token=++generation.current,owner=doc.id
    pendingFit.current=undefined
    if(mode==='manual'||!force&&doc.view.layout_positions?.[mode]){void edit('layout',{mode,positions:{},reuse_saved:true});return}
    const instance=new Worker(new URL('../research-layout.worker.ts',import.meta.url),{type:'module'});worker.current=instance
    const currentRequest=()=>latest.current?.id===owner&&token===generation.current
    instance.onmessage=event=>{
      if(currentRequest())void edit('layout',{mode,positions:event.data.positions}).then(value=>{
        const ack=value as {revision?:number}|null
        if(ack?.revision&&currentRequest()){
          pendingFit.current={owner,revision:ack.revision,generation:token}
          setFitTick(n=>n+1)
        }
      })
      instance.terminate()
    }
    const presented=withCardPresentation(display.nodes,doc.view.card_sizes,cardMode)
    instance.postMessage({nodes:presented.map(n=>({...n,attributes:{display_type:n.attributes.display_type,parent_group_id:n.attributes.parent_group_id,chain:n.attributes.chain,timestamp:n.attributes.timestamp,first_seen:n.attributes.first_seen,_card_size:n.attributes._card_size,_card_mode:n.attributes._card_mode,media:n.attributes.media?{width:(n.attributes.media as Record<string,unknown>).width,height:(n.attributes.media as Record<string,unknown>).height}:undefined},evidence_ids:[]})),edges:display.edges.map(e=>({...e,attributes:{},evidence_ids:[],aggregate:undefined})),root:analyticalModes.has(mode)?root:selection[0]||root,saved:positions,mode})
  }
  useEffect(()=>{if(pendingLayout.current&&doc?.view.ui?.graph_mode===graphMode){const mode=pendingLayout.current;pendingLayout.current='';layout(mode)}},[doc?.view.ui?.graph_mode])
  useEffect(()=>{const mode=doc?.view.ui?.initial_layout,key=doc?.id+'|'+mode;if(mode&&initialLayout.current!==key&&display.nodes.length){initialLayout.current=key;layout(mode,true)}},[doc?.view.ui?.initial_layout,doc?.id,display.nodes.length])
  const toolCapability=capability?.tools?.find(item=>item.id===tool),compatible=!!toolCapability?.compatible&&toolCapability.available!==false
  const run=()=>{if(!selected||!compatible||!tool)return;try{const args=schema?parseToolArguments(schema,draft):undefined;void send('tool',{entity_id:selected.id,tool,query:String(selected.attributes.attachment_id||selected.attributes.username||selected.attributes.address||selected.attributes.value||selected.attributes.url||''),...(args?{arguments:args}:{}),limit:10})}catch(e){setToolError(e instanceof Error?e.message:'Проверьте параметры')}}
  const canonical=String(selected?.attributes.address||selected?.attributes.value||selected?.attributes.url||selected?.label||''),sourceIds=selected?.evidence_ids||relation?.evidence_ids||[]
  const projectControls=<div className="research-project-bar"><input aria-label="Название расследования" value={description} onChange={e=>setDescription(e.target.value)} placeholder="Название нового расследования" maxLength={200}/><Button size="sm" disabled={busy} onClick={()=>void send('new',{title:description||'Новое расследование'})}><Plus size={14}/>Новое</Button><SearchableSelect label="Мои расследования" value={doc?.id||''} disabled={busy} placeholder="Открыть сохранённое…" options={(current?.choices||[]).map(c=>({value:c.id,label:c.title,description:`Версия ${c.revision}`}))} onChange={id=>void send('open',{id})}/><Button variant="ghost" size="sm" disabled={busy} onClick={()=>void send('import')}><Upload size={14}/>Импорт</Button></div>
  return <section className={`research-section ${active?'is-primary':''}`} aria-label="Самостоятельные расследования">
    {!active&&<div className="section-heading"><div><span className="eyebrow">СОБСТВЕННЫЕ ИССЛЕДОВАНИЯ</span><h2>Полотно расследования</h2></div><Button variant="secondary" onClick={()=>setOpen(!open)}><Network size={16}/>{open?'Свернуть полотно':'Мои расследования'}</Button></div>}
    {draftNotice&&<p role="alert" className="notice-inline notice-error">{draftNotice}</p>}
    {open&&<>{!doc&&projectControls}
      {(current?.error||error)&&<div role="alert" className="notice-inline notice-error">{error||current?.error}{error&&<><Button size="sm" variant="secondary" onClick={()=>retry()}>Загрузить актуальную версию и повторить действие</Button><Button size="sm" variant="ghost" onClick={()=>discard()}>Отменить ожидающее действие</Button></>}</div>}
      {doc&&<WorkspaceLayer expanded={expanded}><div className={`research-editor canvas-first ${expanded?'is-expanded':''}`} tabIndex={-1} data-canvas-id={doc.id} data-revision={doc.revision} onKeyDown={e=>{if((e.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"],[role="menu"]'))return;if(e.ctrlKey||e.metaKey){if(['z','y','c','v','d','f'].includes(e.key.toLowerCase()))e.preventDefault();if(e.key.toLowerCase()==='f'){setControlsOpen(true);requestAnimationFrame(()=>document.querySelector<HTMLInputElement>('[aria-label="Поиск на полотне"]')?.focus())};if(e.key.toLowerCase()==='z')void send(e.shiftKey?'redo':'undo');if(e.key.toLowerCase()==='y')void send('redo');if(e.key.toLowerCase()==='c')clipboard.current=selection;if(e.key.toLowerCase()==='v')void importImage({mode:'clipboard'});if(e.key.toLowerCase()==='d')void edit('duplicate_nodes',{ids:selection})}if(e.key==='Escape'){if(connection){setConnection(null);return}if(menu){setMenu(null);return}if(editorVisible){showInspector(false);return}setSelection([]);setEdgeId('');setOverviewOpen(false);setIndexOpen(false);setControlsOpen(false);if(expanded)setExpanded(false)}if(e.key.toLowerCase()==='n'&&!e.ctrlKey&&!e.metaKey)newNode();if(e.key.toLowerCase()==='g'&&(e.ctrlKey||e.metaKey)){e.preventDefault();if(selection.length)void edit('group',{ids:selection,label:'Группа'})}if(e.key==='Delete'&&selection.length){e.preventDefault();void edit('remove',{ids:selection})}}}>
        <header className="research-title"><div className="research-document-title"><h3>{doc.title}</h3><span role="status"><span className="save-dot"/>{busy||pending?'Сохранение…':`Сохранено · ${doc.revision}`}{dirty?' · заметка не сохранена':''}</span></div><Button size="sm" variant="ghost" aria-label="Отменить" disabled={!current?.can_undo} onClick={()=>void send('undo')}><Undo2 size={15}/></Button><Button size="sm" variant="ghost" aria-label="Повторить" disabled={!current?.can_redo} onClick={()=>void send('redo')}><Redo2 size={15}/></Button><Button size="sm" variant="ghost" onClick={()=>setExpanded(v=>!v)}><Expand size={14}/>{expanded?'Встроить':'Развернуть'}</Button><Button size="sm" variant="ghost" aria-label={editorVisible?'Скрыть редактор':'Показать редактор'} onClick={()=>showInspector(!editorVisible)}>{editorVisible?<PanelRightClose size={16}/>:<PanelRightOpen size={16}/>}</Button><Button size="sm" variant="ghost" aria-label="Добавить фото" onClick={()=>{setImportError('');setImportTarget(null)}}><ImagePlus size={15}/></Button><details className="research-project-menu"><summary>Проект</summary><div>{projectControls}<Button size="sm" variant="ghost" onClick={()=>void send('duplicate')}><Copy size={13}/>Копия</Button><Button size="sm" variant="ghost" onClick={()=>void send('export')}><Download size={13}/>Экспорт</Button><Button size="sm" variant="danger" onClick={()=>{if(window.confirm('Убрать расследование из списка? Зашифрованные ревизии сохранятся.'))void send('delete',{confirmed:true})}}>Убрать проект</Button><label>Название<input aria-label="Переименовать расследование" key={doc.id} defaultValue={doc.title} maxLength={200} onBlur={e=>{if(e.target.value!==latest.current?.title)void edit('rename',{title:e.target.value,description:latest.current?.description||''})}}/></label><label>Описание<textarea aria-label="Описание расследования" key={doc.id+'description'} defaultValue={doc.description} maxLength={10000} onBlur={e=>{if(e.target.value!==latest.current?.description)void edit('rename',{title:latest.current?.title,description:e.target.value})}}/></label></div></details></header>
        <div className={`research-toolbar ${controlsOpen?'is-open':''}`}><label className="research-search"><Search size={14}/><input aria-label="Поиск на полотне" value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Найти объект…"/></label><SearchableSelect label="Представление полотна" value={graphMode} options={Object.entries(graphModes).map(([value,label])=>({value,label,group:value==='manual'?'Рабочее полотно':'Аналитические представления'}))} onChange={value=>{pendingLayout.current=value==='transactions'?'timeline':['socmint','assets'].includes(value)?'hierarchical':value==='manual'?'manual':value;ui({graph_mode:value as NonNullable<GraphView['projection_mode']>});setLimit(100)}}/><details className="research-filters"><summary>Фильтры</summary><div><SearchableSelect label="Типы на полотне" value={typeFilter} options={[{value:'',label:'Все типы'},...Array.from(new Set(doc.entities.map(n=>n.type))).map(value=>({value,label:labels[value]||value}))]} onChange={setTypeFilter}/><SearchableSelect label="Статус на полотне" value={statusFilter} options={[{value:'',label:'Все статусы'},...Object.entries(verificationLabels).map(([value,label])=>({value,label}))]} onChange={setStatusFilter}/><SearchableSelect label="Источники на полотне" value={sourceFilter} options={[{value:'',label:'Все источники'},...Array.from(new Set(doc.entities.flatMap(n=>n.source||[]))).map(value=>({value,label:value}))]} onChange={setSourceFilter}/><label><input type="checkbox" checked={showSources} onChange={e=>setShowSources(e.target.checked)}/>Узлы источников</label><SearchableSelect label="Карточки полотна" value={cardMode} options={Object.entries({auto:'По масштабу',compact:'Компактные',standard:'Стандартные',expanded:'Подробные'}).map(([value,label])=>({value,label}))} onChange={value=>ui({card_mode:value as NonNullable<GraphView['card_mode']>})}/></div></details><SearchableSelect label="Раскладка полотна" value={doc.view.layout} options={Object.entries({wallet:'Вокруг кошелька',flow:'Входящие / исходящие',counterparties:'Кластеры контрагентов',paths:'Цепочка связей',manual:'Ручная',hierarchical:'Иерархия',radial:'От выбранного',types:'По типам',communities:'По связям',timeline:'По времени'}).map(([value,label])=>({value,label}))} onChange={value=>layout(value)}/><div className="research-zoom"><Button size="sm" variant="ghost" aria-label="Уменьшить масштаб полотна" onClick={()=>canvas.current?.zoom(.8)}><Minus size={14}/></Button><span>{Math.round(doc.view.viewport.scale*100)}%</span><Button size="sm" variant="ghost" aria-label="Увеличить масштаб полотна" onClick={()=>canvas.current?.zoom(1.25)}><Plus size={14}/></Button><Button size="sm" variant="ghost" aria-label="Вписать полотно" onClick={()=>canvas.current?.fit()}><Expand size={14}/></Button></div></div>
        {!analytical&&overviewOpen&&<section className="canvas-overview" aria-label="Обзор полотна"><header><h3>{doc.title}</h3><Button variant="ghost" size="sm" aria-label="Закрыть обзор" onClick={()=>setOverviewOpen(false)}><X size={15}/></Button></header><div><span><strong>{doc.entities.length}</strong>объектов</span><span><strong>{doc.relations.length}</strong>связей</span><span><strong>{doc.evidence.length}</strong>наблюдений</span></div><p>{doc.description||'Все объекты, источники и ручные гипотезы принадлежат этому расследованию. Представления используют одни и те же данные.'}</p></section>}
        {analytical&&overviewOpen&&<GraphOverview nodes={allNodes} edges={edges} root={root} social={graphMode==='socmint'} partial={!!doc.execution_summary?.some(row=>row.tool===(graphMode==='socmint'?'username_maigret':'blockchain_gansar')&&!['complete','completed','empty'].includes(row.status))} onIndex={()=>setIndexOpen(value=>!value)} onCenter={()=>canvas.current?.center(root)}/>}
        <nav className="canvas-tool-rail" aria-label="Инструменты полотна">
          <Button variant="ghost" aria-label="Новый объект" title="Новый объект · N" onClick={()=>newNode()}><Plus size={21}/></Button>
          <Button variant="ghost" aria-label="Добавить изображение" title="Добавить изображение" onClick={()=>{setImportError('');setImportTarget(null)}}><ImagePlus size={20}/></Button>
          <span/>
          <Button variant="ghost" aria-label="Список объектов" aria-pressed={indexOpen} title="Список объектов" onClick={()=>setIndexOpen(value=>!value)}><List size={20}/></Button>
          <Button variant="ghost" aria-label="Обзор расследования" aria-pressed={overviewOpen} title="Обзор расследования" onClick={()=>setOverviewOpen(value=>!value)}><LayoutGrid size={20}/></Button>
          <Button variant="ghost" aria-label="Настроить полотно" aria-pressed={controlsOpen} title="Поиск, фильтры и раскладка · Ctrl+F" onClick={()=>setControlsOpen(value=>!value)}><SlidersHorizontal size={20}/></Button>
        </nav>
        <nav className="canvas-view-switch" aria-label="Режим рабочего пространства">
          <button aria-pressed={graphMode==='manual'&&!overviewOpen} onClick={()=>{setOverviewOpen(false);ui({graph_mode:'manual'});layout('manual')}}><MousePointer2 size={15}/>Полотно</button>
          <button aria-pressed={graphMode!=='manual'&&!overviewOpen} onClick={()=>{setOverviewOpen(false);setControlsOpen(true)}}><Network size={15}/>Аналитика</button>
          <button aria-pressed={overviewOpen} onClick={()=>setOverviewOpen(value=>!value)}><LayoutGrid size={15}/>Обзор</button>
        </nav>
        <div className="canvas-corner-controls"><Button variant="ghost" size="sm" title="Полноэкранное окно Windows · F11" aria-label="Полноэкранное окно Windows" onClick={()=>void act('window',{mode:'fullscreen'})}><Maximize2 size={16}/></Button></div>
        <div className="canvas-bottom-controls"><Button variant="ghost" size="sm" aria-label="Масштаб минус" onClick={()=>canvas.current?.zoom(.8)}><Minus size={15}/></Button><span>{Math.round(doc.view.viewport.scale*100)}%</span><Button variant="ghost" size="sm" aria-label="Масштаб плюс" onClick={()=>canvas.current?.zoom(1.25)}><Plus size={15}/></Button><Button variant="ghost" size="sm" aria-label="Показать всё" onClick={()=>canvas.current?.fit()}><Expand size={16}/></Button></div>
        {(selection.length>0||relation)&&<nav className="canvas-selection-toolbar" aria-label="Действия с выбранным">
          <span>{relation?'Связь':selection.length>1?`Выбрано ${selection.length}`:selected?entityLabel(selected):'Объект'}</span>
          <Button size="sm" variant="ghost" onClick={()=>showTab('details')}>Сведения</Button><Button size="sm" variant="ghost" disabled={!selected} onClick={()=>showTab('actions')}>Исследовать</Button>
          {selection.length===2&&<Button size="sm" variant="ghost" onClick={()=>connect(selection[0],selection[1])}><Link size={15}/>Связать</Button>}
          {selection.length>1&&<Button size="sm" variant="ghost" onClick={()=>void edit('group',{ids:selection,label:'Группа'})}><Layers size={15}/>Группа</Button>}
          {selected?.type==='entity_group'&&<Button size="sm" variant="ghost" onClick={()=>uiCollapsed(selected.id)}>Свернуть / раскрыть</Button>}
          <Button size="sm" variant="ghost" aria-label="Снять выделение" onClick={()=>{setSelection([]);setEdgeId('')}}><X size={14}/></Button>
        </nav>}
        <div className={`research-body ${editorVisible?'with-inspector':''}`} style={{'--inspector-width':`${doc.view.ui?.inspector_width||360}px`} as import('react').CSSProperties}><div className={`research-plot ${analytical&&indexOpen?'has-analysis-index':''}`}>{indexOpen&&!analytical&&<aside className="graph-analysis-index manual-object-index"><header><strong>Объекты</strong><Button variant="ghost" size="sm" aria-label="Закрыть список" onClick={()=>setIndexOpen(false)}><X size={14}/></Button></header><input aria-label="Найти объект в списке" value={filter} onChange={event=>setFilter(event.target.value)}/><div>{display.nodes.slice(0,500).map(node=><button key={node.id} onClick={()=>{setSelection([node.id]);setEdgeId('');canvas.current?.center(node.id)}}><small>{entityLabel(node)}</small><strong>{node.label}</strong></button>)}</div></aside>}{analytical&&indexOpen&&<GraphAnalyticalIndex nodes={allNodes} edges={edges} root={root} social={graphMode==='socmint'} selected={selection[0]||''} onWindow={ids=>{setAnalyticalIds(previous=>{return previous.length===ids.length&&previous.every((id,i)=>id===ids[i])?previous:ids})}} onSelect={id=>{setEdgeId('');setSelection([id]);setEditorVisible(true);showTab('details');requestAnimationFrame(()=>canvas.current?.center(id))}}/>}<div className="research-renderer"><InvestigationCanvas scopeKey={doc.id+':'+doc.view.layout} key={doc.id} ref={canvas} nodes={display.nodes} edges={display.edges} positions={renderPositions} viewport={doc.view.viewport} cardSizes={doc.view.card_sizes} cardMode={cardMode} selected={selection[0]||''} second={selection[1]||''} selection={selection} selectedEdge={edgeId} root={root} theme={state.settings.ui_theme} onResize={(width,height)=>setSize({width,height})} onSelect={(id,multi)=>{setEdgeId('');setSelection(ids=>multi?(ids.includes(id)?ids.filter(x=>x!==id):[...ids,id]):[id])}} onEdge={id=>{setSelection([]);setEdgeId(id)}} onCommitPositions={value=>void edit('positions',{positions:Object.fromEntries(Object.entries(value).filter(([id,p])=>JSON.stringify(p)!==JSON.stringify(renderPositions[id])))})} onViewport={viewport=>void edit('view',{view:{viewport}})} onCardResize={(id,value)=>void edit('view',{view:{card_sizes:{[id]:value}}})} onOpenMedia={setMediaNode} loadImage={(node,media)=>loadThumbnail({canvas_id:doc.id},node,media)} onDropImage={(file,position)=>void importImage({mode:'file',file},undefined,position)} onNativeDrop={(token,position)=>void importImage({mode:'native_drop',token},undefined,position)} onExpand={expandNode} onCreate={newNode} onConnect={connect} onSelection={setSelection} onContext={(id,p)=>{if(id)setSelection([id]);setMenu({id,x:p.x*doc.view.viewport.scale+doc.view.viewport.x,y:p.y*doc.view.viewport.scale+doc.view.viewport.y})}}/>
          {menu&&<div className="research-context" role="menu" style={{left:Math.max(4,Math.min(menu.x,size.width-225)),top:Math.max(4,Math.min(menu.y,size.height-260))}}><button role="menuitem" onClick={()=>{newNode({x:(menu.x-doc.view.viewport.x)/doc.view.viewport.scale,y:(menu.y-doc.view.viewport.y)/doc.view.viewport.scale});setMenu(null)}}>Новый объект здесь</button>{menu.id&&<><button role="menuitem"  onClick={()=>{showTab('actions');setMenu(null)}}>Исследовать объект…</button><button role="menuitem" onClick={()=>{expandNode(menu.id);setMenu(null)}}>Раскрыть соседей</button><button role="menuitem" onClick={()=>{void edit('hide',{ids:[menu.id]});setMenu(null)}}>Скрыть из представления</button><button role="menuitem" onClick={()=>{clipboard.current=selection;setMenu(null)}}>Копировать выбранное</button><button role="menuitem" onClick={()=>{void edit('duplicate_nodes',{ids:selection});setMenu(null)}}>Дублировать</button></>}<button role="menuitem" onClick={()=>setMenu(null)}>Закрыть меню</button></div>}{!doc.entities.length&&<div className="research-empty"><FolderOpen size={26}/><strong>Начните с объекта</strong><span>Двойной клик по фону или «+» слева. Нажмите N, чтобы добавить объект.</span></div>}
        </div></div>{editorVisible&&<><div className="graph-inspector-resizer" role="separator" aria-label="Ширина редактора полотна" aria-orientation="vertical" tabIndex={0} onPointerDown={e=>{resize.current={x:e.clientX,width:doc.view.ui?.inspector_width||300};e.currentTarget.setPointerCapture(e.pointerId)}} onPointerMove={e=>{if(resize.current)e.currentTarget.parentElement!.style.setProperty('--inspector-width',`${Math.max(280,Math.min(480,resize.current.width+resize.current.x-e.clientX))}px`)}} onPointerUp={e=>{if(resize.current){ui({inspector_width:Math.max(260,Math.min(480,resize.current.width+resize.current.x-e.clientX))});resize.current=undefined}}} onKeyDown={e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();ui({inspector_width:Math.max(260,Math.min(480,(doc.view.ui?.inspector_width||300)+(e.key==='ArrowLeft'?20:-20)))})}}}/><aside className="research-inspector" aria-label="Редактор полотна"><header><div><span className="eyebrow">{selected?entityLabel(selected):relation?'Связь':'Новый объект'}</span><h4>{selected?.label||relation?.relation_type||'Добавить в расследование'}</h4></div><Button variant="ghost" size="sm" aria-label="Закрыть редактор" onClick={()=>showInspector(false)}><X size={14}/></Button></header><nav className="inspector-tabs" aria-label="Раздел инспектора">{Object.entries({details:'Сведения',evidence:`Основания · ${sourceIds.length}`,actions:'Действия'}).map(([id,name])=><button key={id} aria-pressed={tab===id} onClick={()=>showTab(id as typeof tab)}>{name}</button>)}</nav><div className="inspector-content">
          {tab==='details'&&<>{selectedCounterparty&&<CounterpartyFlows peer={selectedCounterparty} onFlow={id=>{setSelection([]);setEdgeId(id)}}/>}{selected&&<><NodeMedia node={selected} context={{canvas_id:doc.id}} onOpen={()=>setMediaNode(selected)}/>
          <div className="media-binding-actions">
            <Button size="sm" variant="secondary" onClick={()=>{setImportError('');setImportTarget(selected)}}><ImagePlus size={14}/>Прикрепить фото</Button>
            {!!(selected.attributes.media as {url?:string}|undefined)?.url&&
              <Button size="sm" variant="ghost" disabled={importBusy} onClick={()=>void importImage({mode:'evidence',canvas_id:doc.id,entity_id:selected.id})}>Сохранить фото на полотно</Button>}
          </div>
          {selected.type==='image'&&<label className="media-fit-label">Отображение фотографии
            <select aria-label="Отображение фотографии" value={selected.attributes.image_fit==='cover'?'cover':'contain'}
              onChange={event=>void edit('image_fit',{entity_id:selected.id,mode:event.target.value})}>
              <option value="contain">Вписать целиком</option><option value="cover">Заполнить карточку</option>
            </select>
          </label>}
          {linkedMedia(selected).map(image=><div className="media-binding" key={image.id}>
            <span title={image.name}>{image.name||'Изображение'}</span>
            <Button size="sm" variant="ghost" aria-label={'Отвязать '+(image.name||'изображение')}
              onClick={()=>void edit('detach_image',{entity_id:selected.id,attachment_id:image.id})}><X size={13}/></Button>
          </div>)}<Badge>{verificationLabels[selected.verification_status||'unverified']}</Badge><div className="inspector-value"><span className="monospace">{canonical}</span><Button size="sm" variant="ghost" aria-label="Копировать значение" onClick={()=>void act('copy',{text:canonical})}><Copy size={13}/></Button></div><dl className="graph-properties">{Object.entries(selected.attributes).filter(([k,v])=>propertyNames[k]&&v!=null).map(([k,v])=><div key={k}><dt>{propertyNames[k]}</dt><dd className={['address','url','value'].includes(k)?'monospace':''}>{valueText(v)}</dd></div>)}</dl><details><summary>Технические свойства</summary><div className="research-properties">{Object.entries(selected.attributes).filter(([k])=>!['media','preview','markdown'].includes(k)&&!k.startsWith('_')).map(([k,v])=><div key={k}><small>{k}</small><span>{valueText(v)}</span></div>)}</div></details></>}
            {!selected&&!relation&&<EntityComposer key={doc.id+':'+composerVersion} jurisdictions={current?.company_jurisdictions} busy={busy||pending>0} onCreate={create}/>}
            {selected&&!relation&&<><label>Подпись аннотации<input aria-label="Название узла" value={label} onChange={e=>changeDraft({label:e.target.value})} maxLength={300}/></label><label>Заметка<textarea aria-label="Заметка узла" value={note} onChange={e=>changeDraft({note:e.target.value})} maxLength={20000}/></label><Button size="sm" variant="secondary" onClick={saveNote}>Сохранить заметку</Button>{note&&<details className="research-note"><summary>Предпросмотр Markdown</summary><Markdown text={note}/></details>}</>}
            {relation&&<><Button size="sm" variant="secondary" disabled={relation.claim_kind!=='analyst_assertion'} onClick={()=>setConnection({from:relation.from_id,to:relation.to_id,relation})}>Изменить связь</Button><Badge>{verificationLabels[relation.verification_status]}</Badge><p className="graph-relation-path">{index.byId.get(relation.from_id)?.label} {relation.direction==='undirected'?'—':'→'} {index.byId.get(relation.to_id)?.label}</p>{relation.aggregate&&<div className="graph-transfer-summary"><strong>{relation.aggregate.count} операций</strong><p>{relation.aggregate.amount??'Сумма неизвестна'} {relation.aggregate.asset_label||relation.aggregate.asset}</p><small>{relation.aggregate.first_seen||'—'} — {relation.aggregate.last_seen||'—'}</small><Button size="sm" variant="secondary" onClick={()=>{const ids=doc.view.expanded_relations||[];void edit('view',{view:{expanded_relations:ids.includes(edgeId)?ids.filter(id=>id!==edgeId):[...ids,edgeId]}})}}>{doc.view.expanded_relations?.includes(edgeId)?'Свернуть транзакции':'Показать транзакции'}</Button></div>}{relation.aggregate&&<FlowTransactions relation={relation} nodes={allNodes} onSelect={id=>{setEdgeId('');setSelection([id]);void edit('view',{view:{expanded_relations:Array.from(new Set([...(doc.view.expanded_relations||[]),relation.id]))}});requestAnimationFrame(()=>canvas.current?.center(id))}}/>}<details><summary>Происхождение связи</summary>{relation.provenance?.map((p,i)=><p key={i}>{p.observed_text_or_field}<small>{p.source_url} · {p.extraction_method}</small></p>)}</details></>}
          </>}
          {tab==='evidence'&&<>{sourceIds.length?sourceIds.map(id=>{const source=doc.evidence.find(e=>e.evidence_id===id||e.related_evidence_ids?.includes(id));return source?<button key={id} className="graph-source-link" onClick={()=>onSource(source)}>{source.title}<small>{source.url||source.kind}</small></button>:<p key={id}>{id}</p>}):<p className="field-hint">У ручного объекта нет внешнего доказательства. Аннотации не меняют исходные факты и статус источников.</p>}<Button size="sm" variant="secondary" disabled={!state.search.investigation_id} onClick={()=>void send('from_search',{investigation_id:state.search.investigation_id})}>Результаты поиска → просмотр</Button></>}
          {tab==='actions'&&<>{selected&&<div className="research-quick-actions"><Button size="sm" variant="secondary" onClick={()=>expandNode(selected.id)}>Соседи · {index.neighbors.get(selected.id)?.size||0}</Button><Button size="sm" variant="ghost" onClick={()=>canvas.current?.center(selected.id)}>В центр</Button><Button size="sm" variant="ghost" onClick={()=>void edit('positions',{positions:{[selected.id]:{...positions[selected.id],pinned:!positions[selected.id]?.pinned}}})}><Pin size={13}/>{positions[selected.id]?.pinned?'Отпустить':'Закрепить'}</Button>{typeof selected.attributes.url==='string'&&<Button size="sm" variant="ghost" onClick={()=>void act('open_url',{url:selected.attributes.url})}>Открыть источник</Button>}</div>}
            <h4 id="research-node-tool">Исследовать объект</h4>{selected&&capability&&<EntityActions node={selected} capability={capability} disabled={state.search.busy} onChoose={chooseTool}/>}{selected&&capability&&!capability.tools?.length&&<p role="alert">{capability.reason||'Нет подходящих инструментов для выбранного значения.'}</p>}<details className="advanced-source-choice"><summary>Отдельные и дополнительные инструменты</summary><SearchableSelect label="Инструмент узла" value={tool} options={state.tools.map(item=>{const c=capability?.tools?.find(t=>t.id===item.id);return {value:item.id,label:item.name,description:c?.reason,disabled:!item.available||!c?.compatible||c.available===false,group:c?.compatible?'Подходит объекту':'Другие инструменты'}})} onChange={chooseTool} disabled={!selected||!capability} placeholder={selected?'Выберите подходящий инструмент…':'Сначала выберите объект'}/></details>{schema&&(tool==='blockchain_gansar'?<GansarFields schema={schema} draft={draft} onChange={(name,value)=>setDraft(old=>({...old,[name]:value}))} capability={capability} disabled={state.search.busy}/>:tool==='username_maigret'?<MaigretFields schema={schema} draft={draft} disabled={state.search.busy} onChange={(name,value)=>setDraft(previous=>({...previous,[name]:value}))}/>:<StructuredToolFields schema={schema} draft={draft} onChange={(name,value)=>setDraft(old=>({...old,[name]:value}))} disabled={state.search.busy}/>)}{toolCapability?.reason&&!compatible&&<p className="field-hint">{toolCapability.reason}</p>}<Button size="sm" disabled={!selected||!tool||!compatible||state.search.busy||state.busy||tool==='blockchain_gansar'&&(!capability?.valid||!!capability.requires_network)} onClick={run}><Search size={13}/>Выполнить → просмотр</Button>{state.search.busy&&<p role="status" className="field-hint">Выполняется {options?.name||tool}. {tool==='username_maigret'&&state.search.maigret_progress?`Проверено ${state.search.maigret_progress.checked||0} / ${state.search.maigret_progress.scheduled||0}, найдено ${state.search.maigret_progress.found||0}`:'Результаты будут показаны перед добавлением в граф.'}</p>}{state.search.busy&&<Button size="sm" variant="danger" onClick={()=>void act('search_stop')}>Остановить инструмент</Button>}{toolError&&<p role="alert">{toolError}</p>}
            {selected&&<><h4>Гермиона</h4><SearchableSelect label="Действие Гермионы" value="" placeholder="Выберите действие…" disabled={state.busy||!state.connection.canSend} options={Object.entries({explain:'Объяснить происхождение',investigate:'Исследовать узел',connections:'Найти публичные связи',compare:'Сравнить два узла',hypothesis:'Проверить гипотезу',next:'Следующий шаг',report:'Краткий отчёт'}).map(([value,label])=>({value,label,disabled:value==='compare'&&selection.length!==2}))} onChange={intent=>void send('analyze',{ids:selection,intent})}/></>}
            <details className="inspector-edit-actions"><summary>Организовать полотно</summary><label>Тип ручной связи<input aria-label="Тип связи" value={edgeType} onChange={e=>setEdgeType(e.target.value)}/></label><Button size="sm" disabled={selection.length!==2} onClick={()=>connect(selection[0],selection[1])}><Link size={13}/>Связать выбранные</Button><div className="research-selection-actions"><Button size="sm" disabled={!selection.length} onClick={()=>void edit('group',{ids:selection,label:label||'Группа'})}>Группировать</Button><Button size="sm" variant="ghost" disabled={!selection.length} onClick={()=>void edit('view',{view:{collapsed:doc.view.collapsed.includes(selection[0])?doc.view.collapsed.filter(i=>i!==selection[0]):[...doc.view.collapsed,selection[0]]}})}>Свернуть / раскрыть</Button><Button size="sm" variant="ghost" disabled={!selection.length} onClick={()=>void edit('hide',{ids:selection})}>Скрыть</Button><Button size="sm" variant="ghost" disabled={!selection.length} onClick={()=>void edit('remove',{ids:selection})}>Убрать с полотна</Button><Button size="sm" variant="ghost" onClick={()=>void edit('restore',{ids:[...doc.view.hidden,...doc.view.removed]})}>Вернуть скрытые</Button>{selected&&<label>Цвет аннотации<input type="color" aria-label="Цвет узла" value={doc.annotations[selected.id]?.color||'#8e7c60'} onChange={e=>void edit('annotate',{entity_id:selected.id,annotation:{color:e.target.value}})}/></label>}<Button size="sm" variant="danger" disabled={!selection.length} onClick={()=>{if(window.confirm('Удалить выбранные сущности и связи? Исходные evidence останутся.'))void edit('delete_entity',{ids:selection})}}>Удалить сущность</Button></div></details>
          </>}
          <div className="inspector-add"><Button size="sm" variant="secondary" onClick={()=>newNode()}><Plus size={13}/>Объект</Button><Button size="sm" variant="ghost" onClick={()=>{setImportError('');setImportTarget(null)}}><ImagePlus size={13}/>Изображение</Button></div>
        </div></aside></>}</div>
        {connection&&index.byId.has(connection.from)&&index.byId.has(connection.to)&&<RelationComposer key={connection.from+'|'+connection.to} from={index.byId.get(connection.from)!} to={index.byId.get(connection.to)!} relation={connection.relation} evidence={doc.evidence} onClose={()=>setConnection(null)} onSave={args=>edit(connection.relation?'edge_edit':'edge',args)}/>}
        <footer className="research-footer"><span>{display.nodes.length} / {allNodes.length} объектов · {display.edges.length} связей · выделено {selection.length}</span>{display.all>display.nodes.length&&<div className="research-selection-actions"><Button size="sm" onClick={()=>setLimit(n=>Math.min(5000,n+100))}>Раскрыть ещё 100</Button><Button size="sm" variant="ghost" onClick={()=>setLimit(5000)}>Показать все на полотне</Button></div>}<span>{graphMode!=='manual'?'Источники и отдельные операции — в основаниях и раскрытии.':'Shift + рамка · Ctrl + выбор · порты → связь · Ctrl+Z/Y'}</span></footer>
        {current?.insertion?.canvas_id===doc.id&&current.insertion.insertion_id!==dismissedInsertion&&<div className="research-insertion-result" role="status">
          <div><strong>Находки добавлены в расследование</strong><span>Новых объектов: {current.insertion.added_nodes} · связей: {current.insertion.added_relations} · ранее сохранённых записей: {current.insertion.existing_records}</span>
            {!!current.insertion.unprojected_records&&<small>Без отдельной карточки: {current.insertion.unprojected_records}. Исходные наблюдения сохранены.</small>}</div>
          <Button size="sm" variant="secondary" disabled={!current.insertion.added_node_ids.length} onClick={()=>{const ids=current.insertion!.added_node_ids;setFilter('');setTypeFilter('');setStatusFilter('');setSourceFilter('');setSelection(ids);requestAnimationFrame(()=>canvas.current?.fit(ids))}}>Показать новые объекты</Button>
          <Button size="sm" variant="ghost" aria-label="Скрыть итог добавления" onClick={()=>setDismissedInsertion(current.insertion!.insertion_id)}><X size={14}/></Button>
        </div>}
        {current?.preview&&current.preview.canvas_id===doc.id&&<ResearchResults preview={current.preview} evidenceIds={doc.evidence.map(row=>row.evidence_id)} onSource={onSource} onInsert={ids=>send('insert',{token:current.preview!.token,evidence_ids:ids})}/> }
      </div></WorkspaceLayer>}{!doc&&<p className="research-start-hint">Создайте расследование или откройте сохранённое. Результаты поиска добавляются после выбора доказательств.</p>}
    </>}
    <MediaImport open={importTarget!==undefined} target={importTarget?.label||''} busy={importBusy} error={importError}
      onClose={()=>{if(!importBusy)setImportTarget(undefined)}} onImport={input=>void importImage(input,importTarget?.id,undefined,true)}/>
    <MediaViewer node={mediaNode} context={{canvas_id:doc?.id}} onClose={()=>setMediaNode(null)} onEvidence={id=>{
      const source=doc?.evidence.find(item=>item.evidence_id===id)
      if(source){setMediaNode(null);onSource(source)}
    }}/>
  </section>
}
