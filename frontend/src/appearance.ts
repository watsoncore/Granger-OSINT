import { applyEffects, applyTheme, themeId, type ThemeId } from './themes'
import type { DesktopState } from './types'

export const wallpaperSources = {
  theme: 'Фон темы', graphite: 'Midnight Graphite', mist: 'Azure Mist', smoke: 'Crimson Smoke',
  depth: 'Violet Depth', black: 'Minimal Black', grid: 'Subtle Grid', solid: 'Pure Color',
  gradient: 'Градиент', image: 'Личное изображение',
} as const
export const fits = {cover:'Заполнить',contain:'Вписать',center:'По центру',stretch:'Растянуть',tile:'Мозаика'} as const
export const edgeStyles = {straight:'Прямые',curved:'Дуги',orthogonal:'Под углом',bezier:'Плавные Безье'} as const
export const colorFields = {
  accent:'Основной акцент', node:'Выбранная карточка', edge:'Выбранная связь',
  hover:'Наведение', nav:'Активная навигация', button:'Основная кнопка',
} as const
export type ColorField = keyof typeof colorFields
export type Wallpaper = {
  source: keyof typeof wallpaperSources; image: string; fit: keyof typeof fits; anchor: 'screen' | 'world';
  x: number; y: number; scale: number; dim: number; blur: number; opacity: number; color: string; end: string;
}
export type AppearancePreset = {
  theme: ThemeId; colors: Partial<Record<ColorField,string>>;
  glow: number; border: number; cardRadius: number; panelRadius: number; surface: number;
  frost: number; reflection: number; shadow: number; density: 'compact' | 'comfortable';
  edges: keyof typeof edgeStyles; effects: 'full' | 'reduced' | 'off'; reducedMotion: boolean; wallpaper: Wallpaper;
}
export type Appearance = AppearancePreset & {
  overrides: Record<string,Wallpaper>; presets: Record<string,AppearancePreset>; hidePrivate: boolean;
}

export const defaultWallpaper: Wallpaper = {
  source:'theme', image:'', fit:'cover', anchor:'screen', x:50, y:50, scale:100, dim:65,
  blur:0, opacity:100, color:'#11171f', end:'#242335',
}
export const themeAccents: Record<ThemeId,string> = {
  dark:'#d7bc94', black:'#e0c59f', light:'#705020', mono:'#ffffff',
  azure:'#89caff', crimson:'#e89caa', violet:'#c7b3fb', silver:'#d7e3ef', amber:'#e2bb86', custom:'#91c8ed',
}

export function defaults(theme: ThemeId = 'dark'): Appearance {
  return {
    theme, colors:{}, glow:theme==='silver'?4:12, border:75, cardRadius:12, panelRadius:16,
    surface:96, frost:8, reflection:10, shadow:22, density:'comfortable', edges:'curved',
    effects:'full', reducedMotion:false, wallpaper:{...defaultWallpaper}, overrides:{}, presets:{}, hidePrivate:true,
  }
}

export function savedAppearance(settings: DesktopState['settings']): Appearance {
  const base=defaults(themeId(settings.ui_theme))
  if(settings.ui_effects==='reduced'||settings.ui_effects==='off')base.effects=settings.ui_effects
  base.reducedMotion=settings.reduced_motion===true
  if(typeof settings.workspace_appearance!=='string'||!settings.workspace_appearance)return base
  try {
    const saved=JSON.parse(settings.workspace_appearance) as Partial<Appearance>
    return {...base,...saved,theme:themeId(saved.theme),wallpaper:{...base.wallpaper,...saved.wallpaper}}
  } catch { return base }
}

export function colorFor(preset: AppearancePreset, key: ColorField) {
  return preset.colors[key] ?? preset.colors.accent ?? themeAccents[preset.theme]
}

function contrast(hex: string) {
  const linear=[1,3,5].map(index=>{
    const channel=parseInt(hex.slice(index,index+2),16)/255
    return channel<=.04045?channel/12.92:((channel+.055)/1.055)**2.4
  })
  return linear[0]*.2126+linear[1]*.7152+linear[2]*.0722>.179?'#121820':'#ffffff'
}

export function applyAppearance(appearance: AppearancePreset, remember = true) {
  applyTheme(appearance.theme,remember)
  applyEffects(appearance.effects)
  const root=document.documentElement
  root.dataset.motion=appearance.reducedMotion?'reduced':'normal'
  root.dataset.density=appearance.density
  const accent=colorFor(appearance,'accent'), button=colorFor(appearance,'button')
  const variables={
    '--user-accent':accent, '--user-node':colorFor(appearance,'node'), '--user-edge':colorFor(appearance,'edge'),
    '--user-hover':colorFor(appearance,'hover'), '--user-nav':colorFor(appearance,'nav'), '--user-button':button,
    '--user-button-text':contrast(button), '--user-glow':String(appearance.glow),
    '--user-card-radius':appearance.cardRadius+'px', '--user-panel-radius':appearance.panelRadius+'px',
    '--user-border':appearance.border+'%', '--user-surface':appearance.surface+'%',
    '--user-frost':appearance.frost+'px', '--user-reflection':appearance.reflection+'%',
    '--user-shadow':appearance.shadow+'%', '--user-edge-style':appearance.edges,
  }
  for(const [name,value] of Object.entries(variables))root.style.setProperty(name,value)
}

export function workspacePreset(appearance: Appearance): AppearancePreset {
  const {overrides,presets,hidePrivate,...preset}=appearance
  return preset
}

export function effectiveWallpaper(appearance: Appearance, canvasId?: string) {
  return canvasId&&appearance.overrides[canvasId]||appearance.wallpaper
}
