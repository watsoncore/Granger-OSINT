import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Slot } from '@radix-ui/react-slot'
import * as Tooltip from '@radix-ui/react-tooltip'
import * as Dropdown from '@radix-ui/react-dropdown-menu'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import * as Collapsible from '@radix-ui/react-collapsible'
import { cva, type VariantProps } from 'class-variance-authority'
import { clsx } from 'clsx'
import { ChevronDown, Check, MoreHorizontal } from 'lucide-react'

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
