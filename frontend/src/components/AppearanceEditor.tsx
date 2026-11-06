import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Copy, ImagePlus, RotateCcw, Save } from 'lucide-react'
import { request } from '../bridge'
import { themes } from '../themes'
import {
  applyAppearance, colorFields, colorFor, defaults, defaultWallpaper, edgeStyles, fits,
  savedAppearance, wallpaperSources, workspacePreset, type Appearance, type ColorField, type Wallpaper,
} from '../appearance'
import type { DesktopState } from '../types'
import { WallpaperLayer, waitForWallpaperPreview } from './WallpaperLayer'
import { Button, Disclosure, Toggle } from './ui'

const controls = [
  ['glow','Интенсивность свечения',0,36],['border','Контраст границ',30,100],
  ['cardRadius','Скругление карточек',0,24],['panelRadius','Скругление панелей',0,30],
  ['surface','Непрозрачность панелей',75,100],['frost','Матовость стекла',0,18],
  ['reflection','Отражения',0,40],['shadow','Тени',0,50],
] as const
const wallpaperControls = [
  ['dim','Затемнение',0,95,'%'],['blur','Размытие',0,20,' px'],['opacity','Непрозрачность фона',0,100,'%'],
  ['x','Положение по горизонтали',0,100,'%'],['y','Положение по вертикали',0,100,'%'],['scale','Масштаб изображения',50,200,'%'],
] as const
const glowModes = {off:0,subtle:6,balanced:12,expressive:24} as const

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
  const update=(change:Partial<Appearance>)=>setDraft(previous=>({...previous,...change}))
  const wallpaper=(scope&&draft.overrides[scope])||draft.wallpaper
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
      if(result?.id)changeWallpaper({image:result.id,source:'image',dim:65})
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
  const mode=Object.entries(glowModes).find(([,value])=>value===draft.glow)?.[0]||'custom'
  const [customGlow,setCustomGlow]=useState(false)
  const dirty=JSON.stringify(draft)!==JSON.stringify(saved)
  const choices=state.research_canvas?.choices||[]
  return <section className="settings-section appearance-editor" aria-label="Редактор оформления">
    <div className="appearance-intro"><div><h2>Ваша рабочая среда</h2><p>Тема, акценты и фон полотна. Изменения видны сразу.</p></div>
      <span className="appearance-preview-label">Предпросмотр</span></div>
    <div className="appearance-preview">
      <WallpaperLayer wallpaper={wallpaper} preview allowImage={!(state.vault?.enabled&&!state.vault.unlocked)} onError={setPreviewError}/>
      <div className="appearance-sample"><span>Расследование</span><strong>Выбранная карточка</strong><small>Публичное наблюдение</small></div>
      <span className="appearance-sample-edge" aria-hidden="true"/><div className="appearance-sample"><span>Источник</span><strong>Публичный профиль</strong></div>
    </div>
    <div className="theme-options" role="group" aria-label="Тема приложения">
      {[...themes.slice(4),...themes.slice(0,4)].map(theme=><button key={theme.id} className="theme-choice"
        aria-label={`Тема: ${theme.label}`} aria-pressed={draft.theme===theme.id}
        onClick={()=>update({theme:theme.id,colors:{},glow:defaults(theme.id).glow})}>
        <span className={'theme-swatch theme-swatch-'+theme.id} aria-hidden="true"/>
        <span><strong>{theme.label}</strong><small>{theme.description}</small></span>
      </button>)}
    </div>
    <Disclosure title="Цвета, свечение и поверхности" description="Акценты карточек, кнопок, связей и панелей">
      <div className="appearance-grid">{(Object.keys(colorFields) as ColorField[]).map(key=><Color key={key}
        label={colorFields[key]} value={colorFor(draft,key)} onChange={color=>update({colors:{...draft.colors,[key]:color}})}/>)}</div>
      <label className="select-field"><span>Свечение</span><select aria-label="Режим свечения" value={customGlow?'custom':mode}
        onChange={event=>{const value=event.target.value as keyof typeof glowModes|'custom';setCustomGlow(value==='custom');if(value!=='custom')update({glow:glowModes[value]})}}>
        <option value="off">Выключено</option><option value="subtle">Деликатное</option><option value="balanced">Умеренное</option>
        <option value="expressive">Выразительное</option><option value="custom">Настраиваемое</option>
      </select></label>
      <div className="appearance-grid">{controls.map(([key,label,min,max])=><Range key={key} label={label} min={min} max={max}
        value={draft[key]} onChange={value=>{if(key==='glow')setCustomGlow(true);update({[key]:value})}}/>)}</div>
      <div className="appearance-grid">
        <label className="select-field"><span>Форма связей</span><select value={draft.edges}
          onChange={event=>update({edges:event.target.value as Appearance['edges']})}>
          {Object.entries(edgeStyles).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
        <label className="select-field"><span>Плотность</span><select value={draft.density}
          onChange={event=>update({density:event.target.value as Appearance['density']})}>
          <option value="comfortable">Комфортная</option><option value="compact">Компактная</option></select></label>
        <label className="select-field"><span>Визуальные эффекты</span><select value={draft.effects}
          onChange={event=>update({effects:event.target.value as Appearance['effects']})}>
          <option value="full">Полные</option><option value="reduced">Уменьшенные</option><option value="off">Выключены</option>
        </select></label>
        <div className="preference-row"><span>Уменьшить движение</span><Toggle label="Уменьшить движение" checked={draft.reducedMotion}
          onChange={reducedMotion=>update({reducedMotion})}/></div>
      </div>
    </Disclosure>
    <Disclosure title="Обои полотна" description="Общий фон или отдельное оформление расследования">
      <div className="appearance-grid">
        <label className="select-field"><span>Где использовать</span><select value={scope} disabled={busy}
          onChange={event=>{setScope(event.target.value);setPreviewError('')}}>
          <option value="">Все расследования</option>{choices.map(choice=><option key={choice.id} value={choice.id}>{choice.title}</option>)}
        </select></label>
        <label className="select-field"><span>Фон</span><select aria-label="Фон полотна" value={wallpaper.source} disabled={busy}
          onChange={event=>{setPreviewError('');changeWallpaper({source:event.target.value as Wallpaper['source']})}}>
          {Object.entries(wallpaperSources).map(([id,label])=><option key={id} value={id}>{label}</option>)}
        </select></label>
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
        <label className="select-field"><span>Расположение</span><select value={wallpaper.fit}
          onChange={event=>changeWallpaper({fit:event.target.value as Wallpaper['fit']})}>
          {Object.entries(fits).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
        <label className="select-field"><span>Привязка фона</span><select value={wallpaper.anchor}
          onChange={event=>changeWallpaper({anchor:event.target.value as Wallpaper['anchor']})}>
          <option value="screen">К окну</option><option value="world">К полотну</option></select></label>
      </div>}
      <div className="appearance-grid">
        {wallpaper.source==='image'&&wallpaperControls.map(([key,label,min,max,unit])=><Range key={key}
          label={label} min={min} max={max} unit={unit} value={wallpaper[key]} onChange={value=>changeWallpaper({[key]:value})}/>)}
        {['solid','gradient'].includes(wallpaper.source)&&<Color label="Цвет фона" value={wallpaper.color} onChange={color=>changeWallpaper({color})}/>}
        {wallpaper.source==='gradient'&&<Color label="Конечный цвет градиента" value={wallpaper.end} onChange={end=>changeWallpaper({end})}/>}
      </div>
      <p className="field-hint">Обои хранятся отдельно от доказательств и исключаются из файлов расследования.</p>
      <div className="preference-row"><span><strong>Скрывать личные обои на снимках полотна</strong>
        <small>Применяется к снимкам, сохранённым из меню проекта.</small></span>
        <Toggle label="Скрывать личные обои на снимках полотна" checked={draft.hidePrivate} onChange={hidePrivate=>update({hidePrivate})}/>
      </div>
    </Disclosure>
    <Disclosure title="Мои пресеты" description="Сохраните сочетание темы, эффектов и обоев">
      <div className="appearance-grid">
        <label className="select-field"><span>Сохранённый пресет</span><select value={preset} onChange={event=>setPreset(event.target.value)}>
          <option value="">Выбрать…</option>{Object.keys(draft.presets).map(key=><option key={key}>{key}</option>)}
        </select></label>
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
