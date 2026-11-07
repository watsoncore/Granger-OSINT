import {Select} from './ui'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Copy, ImagePlus, RotateCcw, Save } from 'lucide-react'
import { request } from '../bridge'
import { themes } from '../themes'
import {
  applyAppearance, colorFields, colorFor, defaults, defaultWallpaper, edgeStyles, fits,
  savedAppearance, wallpaperSources, wallpaperQualities, workspacePreset, type Appearance, type ColorField, type Wallpaper,
  graphAppearance, graphSkinKeys, updateGraphSkin, type GraphSkin,
} from '../appearance'
import type { DesktopState } from '../types'
import { WallpaperLayer, waitForWallpaperPreview } from './WallpaperLayer'
import { Button, Disclosure, Toggle } from './ui'

const controls = [
  ['glow','Интенсивность свечения',0,36],['border','Контраст границ',30,100],
  ['selectionBorder','Толщина выбранной границы',1,3],['hoverGlow','Свечение при наведении',0,16],
  ['edgeHighlight','Подсветка связей',0,100],
  ['cardRadius','Скругление карточек',0,24],['panelRadius','Скругление панелей',0,30],
  ['surface','Непрозрачность панелей',75,100],['frost','Матовость стекла',0,18],
  ['reflection','Отражения',0,40],['shadow','Тени',0,50],
] as const
const wallpaperControls = [
  ['dim','Затемнение',0,95,'%'],['blur','Размытие',0,20,' px'],['opacity','Непрозрачность фона',0,100,'%'],
  ['x','Положение по горизонтали',0,100,'%'],['y','Положение по вертикали',0,100,'%'],['scale','Масштаб изображения',50,200,'%'],
] as const
const glowModes = {off:0,subtle:5,balanced:10,expressive:18} as const
const materials = {
  matte:{label:'Матовая',frost:0,reflection:0,surface:100,shadow:12},
  subtle:{label:'Деликатное стекло',frost:4,reflection:3,surface:98,shadow:16},
  balanced:{label:'Умеренное стекло',frost:8,reflection:8,surface:96,shadow:20},
  reflective:{label:'Отражающая',frost:12,reflection:16,surface:94,shadow:24},
} as const

function Range({label,value,min,max,unit='',onChange}:{
  label:string;value:number;min:number;max:number;unit?:string;onChange(value:number):void
}) {
  return <label className="appearance-range"><span>{label}<output>{value}{unit}</output></span>
    <input aria-label={label} type="range" min={min} max={max} value={value} onChange={event=>onChange(Number(event.target.value))}/>
  </label>
}

function Color({label,value,onChange}:{label:string;value:string;onChange(value:string):void}) {
  const [text,setText]=useState(value)
  useEffect(()=>setText(value),[value])
  return <label className="appearance-color"><span>{label}</span><div>
    <input aria-label={label} type="color" value={value} onChange={event=>onChange(event.target.value)}/>
    <input aria-label={label+' HEX'} value={text} maxLength={7} spellCheck={false} onBlur={()=>setText(value)}
      onChange={event=>{const next=event.target.value;setText(next);if(/^#[0-9a-f]{6}$/i.test(next))onChange(next.toLowerCase())}}/>
  </div></label>
}

export function AppearanceEditor({state}:{state:DesktopState}) {
  const {ui_theme,ui_effects,reduced_motion,workspace_appearance}=state.settings
  const saved=useMemo(()=>savedAppearance({ui_theme,ui_effects,reduced_motion,workspace_appearance}),
    [ui_theme,ui_effects,reduced_motion,workspace_appearance])
  const baseline=useRef(saved);baseline.current=saved
  const [draft,setDraft]=useState(saved),[scope,setScope]=useState(''),[name,setName]=useState(''),[preset,setPreset]=useState('')
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[previewError,setPreviewError]=useState('')
  useEffect(()=>setDraft(saved),[saved])
  useEffect(()=>{applyAppearance(draft,false)},[draft])
  useEffect(()=>()=>{applyAppearance(baseline.current)},[])
  const skin=graphAppearance(draft)
  const update=(change:Partial<Appearance>&{arrows?:boolean})=>setDraft(previous=>{
    const graphChange=Object.fromEntries(Object.entries(change).filter(([key])=>(graphSkinKeys as readonly string[]).includes(key))) as Partial<GraphSkin>
    const other=Object.fromEntries(Object.entries(change).filter(([key])=>!(graphSkinKeys as readonly string[]).includes(key)))
    return {...(Object.keys(graphChange).length?updateGraphSkin(previous,graphChange):previous),...other}
  })
  const wallpaper=(scope&&draft.overrides[scope])||draft.wallpaper
  const material=Object.entries(materials).find(([,value])=>
    value.frost===skin.frost&&value.reflection===skin.reflection&&value.surface===skin.surface&&value.shadow===skin.shadow)?.[0]||'custom'
  const changeWallpaper=(change:Partial<Wallpaper>)=>{
    const next={...wallpaper,...change}
    if(scope)update({overrides:{...draft.overrides,[scope]:next}})
    else update({wallpaper:next})
  }
  async function choose() {
    setBusy(true);setError('')
    try {
      await waitForWallpaperPreview()
      const result=await request('wallpaper_choose') as {id:string}|null
      if(result?.id)changeWallpaper({image:result.id,source:'image'})
    } catch(error) {setError(error instanceof Error?error.message:'Изображение недоступно.')}
    finally {setBusy(false)}
  }
  async function save() {
    setBusy(true);setError('')
    try {
      const legacy=['dark','black','light','mono'].includes(draft.theme)?draft.theme:'dark'
      await request('settings_save',{values:{workspace_appearance:JSON.stringify(draft),ui_theme:legacy,
        ui_effects:draft.effects,reduced_motion:draft.reducedMotion}})
    } catch(error) {setError(error instanceof Error?error.message:'Оформление не сохранено.')}
    finally {setBusy(false)}
  }
  function savePreset(duplicate:boolean) {
    const key=name.trim()
    if(!key||key.length>48||(!Object.hasOwn(draft.presets,key)&&Object.keys(draft.presets).length>=12)){
      setError('Укажите имя пресета. Можно сохранить до 12 пресетов.');return
    }
    if(duplicate&&(!preset||!Object.hasOwn(draft.presets,preset)||Object.hasOwn(draft.presets,key))){
      setError('Выберите сохранённый пресет и укажите новое имя.');return
    }
    setError('')
    update({presets:{...draft.presets,[key]:duplicate?draft.presets[preset]:workspacePreset(draft)}})
    setPreset(key)
  }
  const mode=Object.entries(glowModes).find(([,value])=>value===skin.glow)?.[0]||'custom'
  const [customGlow,setCustomGlow]=useState(false)
  const dirty=JSON.stringify(draft)!==JSON.stringify(saved)
  const choices=state.research_canvas?.choices||[]
  return <section className="settings-section appearance-editor" aria-label="Редактор оформления">
    <div className="appearance-intro"><div><h2>Ваша рабочая среда</h2><p>Стиль приложения, тема, акценты и фон. Изменения видны сразу.</p></div>
      <span className="appearance-preview-label">Предпросмотр</span></div>
    <fieldset className="graph-style-choices"><legend>Стиль всего приложения</legend>
      {(['minimal','glass'] as const).map(style=><button key={style} type="button" aria-pressed={draft.appStyle===style}
        aria-label={style==='glass'?'Glass · всё приложение':'Minimal · всё приложение'} onClick={()=>update({appStyle:style})}>
        <strong>{style==='glass'?'Glass':'Minimal'}</strong>
        <small>{style==='glass'?'Сохранённые стекло, глубина и эффекты':'Матовые поверхности, строгие границы, без свечения во всех разделах'}</small>
      </button>)}
    </fieldset>
    <fieldset className="graph-style-choices"><legend>Стиль графа</legend>
      {(['glass','minimal'] as const).map(style=><button key={style} type="button" aria-pressed={draft.graphStyle===style}
        aria-label={style==='glass'?'Glass Graph':'Minimal Graph'} onClick={()=>update({graphStyle:style})}>
        <span className="graph-style-thumbnail" data-graph-style={style} aria-hidden="true"><i/><em/><i/></span>
        <strong>{style==='glass'?'Glass Graph':'Minimal Graph'}</strong>
        <small>{style==='glass'?'Мягкое стекло и личные акценты':'Матовые карточки и строгие линии'}</small>
      </button>)}
    </fieldset>
    <div className="appearance-preview" data-graph-style={draft.graphStyle} style={{'--user-card-radius':skin.cardRadius+'px','--user-glow':String(skin.glow)} as import('react').CSSProperties}>
      <WallpaperLayer wallpaper={wallpaper} preview allowImage={!(state.vault?.enabled&&!state.vault.unlocked)} onError={setPreviewError}/>
      <div className="appearance-sample"><span>Расследование</span><strong>Выбранная карточка</strong><small>Публичное наблюдение</small></div>
      <span className="appearance-sample-edge" aria-hidden="true"/><div className="appearance-sample"><span>Источник</span><strong>Публичный профиль</strong></div>
    </div>
    <div className="theme-options" role="group" aria-label="Тема приложения">
      {[...themes.slice(4),...themes.slice(0,4)].map(theme=><button key={theme.id} className="theme-choice"
        aria-label={`Тема: ${theme.label}`} aria-pressed={draft.theme===theme.id}
        onClick={()=>update({theme:theme.id,colors:{},glow:draft.graphStyle==='minimal'?0:defaults(theme.id).glow})}>
        <span className={'theme-swatch theme-swatch-'+theme.id} aria-hidden="true"/>
        <span><strong>{theme.label}</strong><small>{theme.description}</small></span>
      </button>)}
    </div>
    <Disclosure title="Цвета, свечение и поверхности" description="Акценты карточек, кнопок, связей и панелей">
      <label className="select-field"><span>Поверхности</span><Select aria-label="Стиль поверхностей" value={material}
        onValueChange={value=>{if(value!=='custom'){const {label:_,...style}=materials[value as keyof typeof materials];update(style)}}}>
        {Object.entries(materials).map(([id,value])=><option key={id} value={id}>{value.label}</option>)}
        <option value="custom">Свои параметры</option>
      </Select></label>
      <div className="appearance-grid">{(Object.keys(colorFields) as ColorField[]).map(key=><Color key={key}
        label={colorFields[key]} value={colorFor(draft,key)} onChange={color=>update({colors:{...draft.colors,[key]:color}})}/>)}</div>
      <label className="select-field"><span>Свечение</span><Select aria-label="Режим свечения" value={customGlow?'custom':mode}
        onValueChange={selectedValue=>{const value=selectedValue as keyof typeof glowModes|'custom';setCustomGlow(value==='custom');if(value!=='custom')update({glow:glowModes[value]})}}>
        <option value="off">Выключено</option><option value="subtle">Деликатное</option><option value="balanced">Умеренное</option>
        <option value="expressive">Выразительное</option><option value="custom">Настраиваемое</option>
      </Select></label>
      <div className="appearance-grid">{controls.map(([key,label,min,max])=><Range key={key} label={label} min={min} max={max}
        value={skin[key]} onChange={value=>{if(key==='glow')setCustomGlow(true);update({[key]:value})}}/>)}</div>
      <div className="appearance-grid">
        <label className="select-field"><span>Форма связей</span><Select aria-label="Форма связей" value={skin.edges}
          onValueChange={selectedValue=>update({edges:selectedValue as Appearance['edges']})}>
          {Object.entries(edgeStyles).map(([id,label])=><option key={id} value={id}>{label}</option>)}</Select></label>
        <div className="preference-row"><span>Направленные стрелки</span><Toggle label="Направленные стрелки" checked={skin.arrows} onChange={arrows=>update({arrows})}/></div>
        <label className="select-field"><span>Плотность</span><Select aria-label="Плотность" value={skin.density}
          onValueChange={selectedValue=>update({density:selectedValue as Appearance['density']})}>
          <option value="comfortable">Комфортная</option><option value="compact">Компактная</option></Select></label>
        <label className="select-field"><span>Визуальные эффекты</span><Select aria-label="Визуальные эффекты" value={draft.effects}
          onValueChange={selectedValue=>update({effects:selectedValue as Appearance['effects']})}>
          <option value="full">Полные</option><option value="reduced">Уменьшенные</option><option value="off">Выключены</option>
        </Select></label>
        <div className="preference-row"><span>Уменьшить движение</span><Toggle label="Уменьшить движение" checked={draft.reducedMotion}
          onChange={reducedMotion=>update({reducedMotion})}/></div>
      </div>
    </Disclosure>
    <Disclosure title="Обои графа" description="Общий фон или отдельное оформление расследования">
      <div className="appearance-grid">
        <label className="select-field"><span>Где использовать</span><Select aria-label="Где использовать" value={scope} disabled={busy}
          onValueChange={selectedValue=>{setScope(selectedValue);setPreviewError('')}}>
          <option value="">Все расследования</option>{choices.map(choice=><option key={choice.id} value={choice.id}>{choice.title}</option>)}
        </Select></label>
        <label className="select-field"><span>Фон</span><Select aria-label="Фон графа" value={wallpaper.source} disabled={busy}
          onValueChange={selectedValue=>{setPreviewError('');changeWallpaper({source:selectedValue as Wallpaper['source']})}}>
          {Object.entries(wallpaperSources).map(([id,label])=><option key={id} value={id}>{label}</option>)}
        </Select></label>
      </div>
      <div className="appearance-actions"><Button variant="secondary" size="sm" disabled={busy} onClick={()=>void choose()}>
        <ImagePlus size={16}/>Выбрать изображение</Button>
        {!!wallpaper.image&&<Button size="sm" variant="ghost" disabled={busy} onClick={()=>changeWallpaper({image:'',source:'theme'})}>Убрать изображение</Button>}
        {scope&&draft.overrides[scope]&&<Button size="sm" variant="ghost" disabled={busy} onClick={()=>{
          const overrides={...draft.overrides};delete overrides[scope];update({overrides})
        }}>Восстановить общий фон</Button>}
      </div>
      {previewError&&wallpaper.source==='image'&&<p role="alert">{previewError}</p>}
      {wallpaper.source==='image'&&<div className="appearance-grid">
        <label className="select-field"><span>Качество обоев</span><Select aria-label="Качество обоев" value={wallpaper.quality||'auto'}
          onValueChange={value=>changeWallpaper({quality:value as Wallpaper['quality']})}>
          {Object.entries(wallpaperQualities).map(([id,label])=><option key={id} value={id}>{label}</option>)}
        </Select></label>
        <label className="select-field"><span>Расположение</span><Select aria-label="Расположение" value={wallpaper.fit}
          onValueChange={selectedValue=>changeWallpaper({fit:selectedValue as Wallpaper['fit']})}>
          {Object.entries(fits).map(([id,label])=><option key={id} value={id}>{label}</option>)}</Select></label>
        <label className="select-field"><span>Привязка фона</span><Select aria-label="Привязка фона" value={wallpaper.anchor}
          onValueChange={selectedValue=>changeWallpaper({anchor:selectedValue as Wallpaper['anchor']})}>
          <option value="screen">К окну</option><option value="world">К графу</option></Select></label>
      </div>}
      {wallpaper.source==='image'&&wallpaper.fit==='stretch'&&<p className="notice-inline notice-warning" role="status">
        Растяжение меняет пропорции изображения. «Заполнить» и «Вписать» сохраняют геометрию.</p>}
      {wallpaper.source==='image'&&<p className="field-hint">Качество выбирается отдельно от эффектов.
        В оригинальном качестве без размытия используются исходные байты файла.
        Масштаб 100% в оригинальном размере соответствует исходным размерам в CSS-пикселях.</p>}
      <div className="appearance-grid">
        {wallpaper.source==='image'&&wallpaperControls.map(([key,label,min,max,unit])=><Range key={key}
          label={label} min={min} max={max} unit={unit} value={wallpaper[key]} onChange={value=>changeWallpaper({[key]:value})}/>)}
        {['solid','gradient'].includes(wallpaper.source)&&<Color label="Цвет фона" value={wallpaper.color} onChange={color=>changeWallpaper({color})}/>}
        {wallpaper.source==='gradient'&&<Color label="Конечный цвет градиента" value={wallpaper.end} onChange={end=>changeWallpaper({end})}/>}
      </div>
      <p className="field-hint">Обои хранятся отдельно от доказательств и исключаются из файлов расследования.</p>
      <div className="preference-row"><span><strong>Скрывать личные обои на снимках графа</strong>
        <small>Применяется к снимкам, сохранённым из меню проекта.</small></span>
        <Toggle label="Скрывать личные обои на снимках графа" checked={draft.hidePrivate} onChange={hidePrivate=>update({hidePrivate})}/>
      </div>
    </Disclosure>
    <Disclosure title="Мои пресеты" description="Сохраните сочетание темы, эффектов и обоев">
      <div className="appearance-grid">
        <label className="select-field"><span>Сохранённый пресет</span><Select aria-label="Сохранённый пресет" value={preset} onValueChange={selectedValue=>setPreset(selectedValue)}>
          <option value="">Выбрать…</option>{Object.keys(draft.presets).map(key=><option key={key}>{key}</option>)}
        </Select></label>
        <label className="select-field"><span>Имя пресета</span><input value={name} maxLength={48} onChange={event=>setName(event.target.value)}/></label>
      </div>
      <div className="appearance-actions">
        <Button variant="secondary" size="sm" disabled={!preset} onClick={()=>update(draft.presets[preset])}>Открыть пресет</Button>
        <Button variant="secondary" size="sm" onClick={()=>savePreset(false)}><Save size={15}/>Сохранить пресет</Button>
        <Button variant="ghost" size="sm" disabled={!preset} onClick={()=>savePreset(true)}><Copy size={15}/>Дублировать пресет</Button>
      </div>
    </Disclosure>
    {error&&<p role="alert" className="appearance-error">{error}</p>}
    <div className="appearance-actions appearance-commit">
      <Button size="sm" disabled={!dirty||busy} onClick={()=>void save()}><Check size={15}/>Применить</Button>
      <Button variant="secondary" size="sm" disabled={!dirty||busy} onClick={()=>{setDraft(saved);setError('');setCustomGlow(false)}}>Отмена</Button>
      <Button variant="ghost" size="sm" disabled={busy} onClick={()=>{update({...workspacePreset(defaults(saved.theme)),wallpaper:{...defaultWallpaper}});setCustomGlow(false)}}>
        <RotateCcw size={15}/>Сбросить
      </Button>
    </div>
  </section>
}
