export const themes = [
  { id: 'dark', label: 'Тёмная', description: 'Дымчатый графит с отражающими кромками и тёплым акцентом' },
  { id: 'black', label: 'Чёрная', description: 'Чёрные поверхности и светлый текст' },
  { id: 'light', label: 'Белая', description: 'Белый фон и тёмная типографика' },
  { id: 'mono', label: 'Чёрно-белая', description: 'Только чёрный, белый и нейтральные серые' },
] as const
export type ThemeId = typeof themes[number]['id']
declare global { interface Window { __GRANGER_THEME__?: string; __GRANGER_EFFECTS__?: string } }
export function themeId(value: unknown): ThemeId {
  return themes.some(theme => theme.id === value) ? value as ThemeId : 'dark'
}
export function applyTheme(value: unknown) {
  const selected = themeId(value)
  document.documentElement.dataset.theme = selected
  try { localStorage.setItem('granger.ui_theme', selected) } catch { /* Native settings remain authoritative. */ }
  return selected
}
// Runs before React's first render. A native snapshot then supplies the saved setting.
export function restoreTheme() {
  applyEffects(window.__GRANGER_EFFECTS__)
  try { applyTheme(window.__GRANGER_THEME__ ?? localStorage.getItem('granger.ui_theme')) } catch { applyTheme(window.__GRANGER_THEME__ ?? 'dark') }
}

export function applyEffects(value:unknown){
  document.documentElement.dataset.effects=value==='off'||value==='reduced'?value:'full'
}
