import { Children, forwardRef, isValidElement, useState, useRef, useEffect, useImperativeHandle, type ButtonHTMLAttributes, type DetailsHTMLAttributes,
  type HTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react'
import { Slot } from '@radix-ui/react-slot'
import * as Tooltip from '@radix-ui/react-tooltip'
import * as Dropdown from '@radix-ui/react-dropdown-menu'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import * as Collapsible from '@radix-ui/react-collapsible'
import { cva, type VariantProps } from 'class-variance-authority'
import { clsx } from 'clsx'
import { ChevronDown, Check, MoreHorizontal } from 'lucide-react'
import {SearchableSelect, type SelectOption} from './SearchableSelect'
import {CryptoIcon,networkIcon} from '../crypto-icons'

function textContent(children:ReactNode):string {
  return Children.toArray(children).map(child=>isValidElement<{children?:ReactNode}>(child)
    ?textContent(child.props.children):String(child)).join('')
}

function selectOptions(children:ReactNode, group?:string, disabled=false):SelectOption[] {
  return Children.toArray(children).flatMap(child=>{
    if(!isValidElement<{value?:string|number;label?:string;disabled?:boolean;children?:ReactNode}>(child))return []
    const props=child.props
    if(child.type==='option')return [{
      value:String(props.value??textContent(props.children)),label:props.label||textContent(props.children),
      group,disabled:disabled||props.disabled,
    }]
    return selectOptions(props.children,child.type==='optgroup'?props.label:group,disabled||!!props.disabled)
  })
}

export function Select({value,defaultValue,children,onValueChange,disabled,className,id,...props}:{
  value?:string|number;defaultValue?:string|number;children:ReactNode;onValueChange(value:string):void;
  disabled?:boolean;className?:string;id?:string;'aria-label'?:string;title?:string;name?:string;
  autoFocus?:boolean;required?:boolean;
}) {
  const networkField=['Сеть нового объекта','Сеть Gansar','Сеть кошелька'].includes(props['aria-label']||'')
  const options=selectOptions(children).map(option=>networkField&&networkIcon(option.value)
    ?{...option,icon:<CryptoIcon id={networkIcon(option.value)} size={20}/>} :option)
  const [local,setLocal]=useState(String(defaultValue??options[0]?.value??''))
  const selected=value===undefined?local:String(value)
  return <SearchableSelect id={id} label={props['aria-label']} value={selected} options={options}
    disabled={disabled} className={className} autoFocus={props.autoFocus} required={props.required}
    onChange={next=>{setLocal(next);onValueChange(next)}}/>
}

export function Checkbox({indeterminate=false,readOnly,onChange,...props}:
  InputHTMLAttributes<HTMLInputElement>&{indeterminate?:boolean}) {
  return <input {...props} type="checkbox" readOnly={readOnly}
    ref={node=>{if(node)node.indeterminate=indeterminate}}
    aria-checked={indeterminate?'mixed':props.checked}
    onClick={event=>{if(readOnly)event.preventDefault();props.onClick?.(event)}}
    onChange={event=>{if(!readOnly)onChange?.(event)}}/>
}

export const Details=forwardRef<HTMLDetailsElement,DetailsHTMLAttributes<HTMLDetailsElement>&{dismissible?:boolean}>(
  function Details({className='',children,dismissible=false,onKeyDown,...props},ref){
    const element=useRef<HTMLDetailsElement>(null)
    useImperativeHandle(ref,()=>element.current!)
    useEffect(()=>{
      if(!dismissible)return
      const dismiss=(event:PointerEvent)=>{
        const target=event.target as Element|null
        if(element.current?.open&&target&&!element.current.contains(target)&&!target.closest('[data-radix-popper-content-wrapper]'))element.current.open=false
      }
      document.addEventListener('pointerdown',dismiss,true)
      return()=>document.removeEventListener('pointerdown',dismiss,true)
    },[dismissible])
    return <details {...props} ref={element} className={'disclosure-details '+className} onKeyDown={event=>{
      onKeyDown?.(event)
      if(event.key==='Escape'&&!event.defaultPrevented&&element.current?.open){event.preventDefault();event.stopPropagation();element.current.open=false;element.current.querySelector('summary')?.focus()}
    }}>{children}</details>
  })
export function Summary({children,...props}:HTMLAttributes<HTMLElement>){
  return <summary {...props}><ChevronDown aria-hidden="true" size={16}/><span>{children}</span></summary>
}

// Button composition adapted from shadcn/ui, MIT, Copyright(c)2023 shadcn.
const buttonVariants = cva('button', { variants: {
  variant: { default: 'button-primary', secondary: 'button-secondary', ghost: 'button-ghost', danger: 'button-danger' },
  size: { default: '', sm: 'button-small', icon: 'button-icon' },
}, defaultVariants: { variant: 'default', size: 'default' } })
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & { asChild?: boolean }
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({ className, variant, size, asChild, ...props }, ref) {
  const Component = asChild ? Slot : 'button'
  return <Component ref={ref} className={clsx(buttonVariants({ variant, size }), className)} {...props} />
})

export function IconButton({ label, children, ...props }: ButtonProps & { label: string }) {
  return <Tooltip.Root><Tooltip.Trigger asChild><Button type="button" variant="ghost" size="icon" aria-label={label} {...props}>{children}</Button></Tooltip.Trigger><Tooltip.Portal><Tooltip.Content className="tooltip" sideOffset={7}>{label}<Tooltip.Arrow /></Tooltip.Content></Tooltip.Portal></Tooltip.Root>
}
export function ActionsMenu({ children, label = 'Действия' }: { children: ReactNode; label?: string }) {
  return <Dropdown.Root><Dropdown.Trigger asChild><IconButton label={label}><MoreHorizontal size={17}/></IconButton></Dropdown.Trigger><Dropdown.Portal><Dropdown.Content className="menu" align="end" sideOffset={6}>{children}</Dropdown.Content></Dropdown.Portal></Dropdown.Root>
}
export function MenuItem({ children, onSelect, disabled, danger }: { children: ReactNode; onSelect(): void; disabled?: boolean; danger?: boolean }) {
  return <Dropdown.Item className={clsx('menu-item', danger && 'text-danger')} disabled={disabled} onSelect={onSelect}>{children}</Dropdown.Item>
}
export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange(value: boolean): void; label: string; disabled?: boolean }) {
  return <SwitchPrimitive.Root aria-label={label} className="switch" checked={checked} onCheckedChange={onChange} disabled={disabled}><SwitchPrimitive.Thumb className="switch-thumb" /></SwitchPrimitive.Root>
}
export function Disclosure({ title, description, children, defaultOpen = false }: { title: string; description?: string; children: ReactNode; defaultOpen?: boolean }) {
  return <Collapsible.Root className="disclosure" defaultOpen={defaultOpen}><Collapsible.Trigger className="disclosure-trigger"><span><strong>{title}</strong>{description && <small>{description}</small>}</span><ChevronDown size={16}/></Collapsible.Trigger><Collapsible.Content className="disclosure-content"><div>{children}</div></Collapsible.Content></Collapsible.Root>
}
export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'success' | 'warning' | 'danger' }) {
  return <span className={`badge badge-${tone}`}>{tone === 'success' && <Check size={11}/>} {children}</span>
}
export function EmptyState({ icon, title, children, action }: { icon: ReactNode; title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-symbol">{icon}</div><h2>{title}</h2><p>{children}</p>{action}</div>
}
