import {type ReactNode} from 'react'
import {createPortal} from 'react-dom'

/** Escape ancestors' clipping/stacking contexts in the desktop workspace. */
export function WorkspaceLayer({expanded,children}:{expanded:boolean;children:ReactNode}){
  return expanded?createPortal(children,document.body):children
}
