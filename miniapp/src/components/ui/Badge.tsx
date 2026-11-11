import type { ComponentProps } from 'react'
import { cn } from './utils'

type BadgeProps = ComponentProps<'span'> & { tone?: 'neutral' | 'accent' }

export function Badge({ className, tone = 'neutral', ...props }: BadgeProps) {
  return <span className={cn('badge', `badge--${tone}`, className)} {...props} />
}
