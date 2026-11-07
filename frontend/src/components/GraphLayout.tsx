import {useLayoutEffect,useRef,type CSSProperties,type HTMLAttributes} from 'react'
import type {AppearancePreset} from '../appearance'

/** One grid owns all chrome. The canvas stays full-size under its safe zones. */
export function GraphLayout({appearance,style,children,...props}:HTMLAttributes<HTMLDivElement>&{appearance:AppearancePreset}) {
  const host=useRef<HTMLDivElement>(null)
  const previousGeometry=useRef('')
  useLayoutEffect(()=>{
    const root=host.current
    if(!root)return
    const measure=()=>{
      const bounds=root.getBoundingClientRect(),visible=(selector:string)=>[...root.querySelectorAll<HTMLElement>(selector)].filter(element=>element.offsetWidth&&element.offsetHeight)
      const top=Math.max(12,...visible('.research-title,.graph-command-bar,.canvas-view-switch,.canvas-focus').map(element=>element.getBoundingClientRect().bottom-bounds.top))+8
      const dock=root.querySelector<HTMLElement>('.graph-right-dock')
      const bottom=Math.max(12,...visible('.canvas-bottom-controls,.canvas-selection-toolbar,.research-footer').map(element=>bounds.bottom-element.getBoundingClientRect().top))+8
      const left=visible('.graph-analysis-index').reduce((safe,element)=>Math.max(safe,element.getBoundingClientRect().right-bounds.left+8),68)
      const right=dock?.childElementCount?(dock.offsetWidth+24):12
      const header=root.querySelector<HTMLElement>('.research-title'),command=root.querySelector<HTMLElement>('.graph-command-bar')
      const projectHeight=Math.max(80,innerHeight-(header?.getBoundingClientRect().bottom||0)-20)
      const filterHeight=Math.max(80,innerHeight-(command?.getBoundingClientRect().bottom||0)-20)
      const signature=[top,right,bottom,left,projectHeight,filterHeight,bounds.width,bounds.height].join('|')
      if(signature===previousGeometry.current)return
      previousGeometry.current=signature
      root.style.setProperty('--graph-top-safe',`${top}px`)
      root.style.setProperty('--graph-right-safe',`${right}px`)
      root.style.setProperty('--graph-bottom-safe',`${bottom}px`)
      root.style.setProperty('--graph-left-safe',`${left}px`)
      root.style.setProperty('--graph-project-max-height',`${projectHeight}px`)
      root.style.setProperty('--graph-filter-max-height',`${filterHeight}px`)
      root.dataset.layoutWidth=String(Math.round(bounds.width))
      root.dispatchEvent(new Event('granger-graph-safe-zones'))
    }
    const observer=new ResizeObserver(measure)
    observer.observe(root)
    for(const element of root.querySelectorAll('.research-title,.graph-command-bar,.graph-right-dock,.canvas-bottom-controls,.canvas-selection-toolbar,.research-footer'))observer.observe(element)
    const mutations=new MutationObserver(measure)
    mutations.observe(root,{childList:true,subtree:true})
    measure()
    return()=>{observer.disconnect();mutations.disconnect()}
  },[])
  const variables:Record<string,string>={
    '--appearance-surface':'color-mix(in srgb,var(--panel) var(--user-surface),transparent)',
    '--appearance-shadow':'0 10px 24px color-mix(in srgb,#000 var(--user-shadow),transparent)',
    '--appearance-reflection':'inset 0 1px color-mix(in srgb,var(--text) var(--user-reflection),transparent)',
    '--border-soft':'color-mix(in srgb,var(--border) var(--user-border),transparent)',
    '--user-card-radius':appearance.cardRadius+'px','--user-panel-radius':appearance.panelRadius+'px',
    '--user-glow':String(appearance.glow),'--user-border':appearance.border+'%',
    '--user-surface':appearance.surface+'%','--user-frost':appearance.frost+'px',
    '--user-reflection':appearance.reflection+'%','--user-shadow':appearance.shadow+'%',
    '--user-selection-border':String(appearance.selectionBorder),'--user-hover-glow':String(appearance.hoverGlow),
    '--user-edge-highlight':String(appearance.edgeHighlight),
  }
  return <div {...props} ref={host} data-graph-layout="coordinated" data-graph-style={appearance.graphStyle}
    data-graph-density={appearance.density} style={{...variables,...style} as CSSProperties}>{children}</div>
}
