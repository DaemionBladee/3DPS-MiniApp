import type { ComponentProps } from 'react'
import { cn } from './utils'

type ButtonProps = ComponentProps<'button'> & {
  variant?: 'primary' | 'secondary' | 'ghost'
}

export function Button({ className, variant = 'primary', type = 'button', ...props }: ButtonProps) {
  return <button type={type} className={cn('button', `button--${variant}`, className)} {...props} />
}
