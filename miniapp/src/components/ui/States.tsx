import { AlertCircle, Inbox, LoaderCircle, type LucideIcon } from 'lucide-react'
import { Button } from './Button'

type EmptyStateProps = {
  title: string
  description: string
  icon?: LucideIcon
}

export function EmptyState({ title, description, icon: Icon = Inbox }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon"><Icon size={25} aria-hidden="true" /></span>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  )
}

export function LoadingState({ label = 'Loading your workspace…' }: { label?: string }) {
  return (
    <div className="feedback-state" role="status">
      <LoaderCircle className="loading-spinner" aria-hidden="true" size={24} />
      <p>{label}</p>
    </div>
  )
}

export function ErrorState({ title = 'Something went wrong', description = 'Please try again in a moment.', onRetry }: {
  title?: string
  description?: string
  onRetry?: () => void
}) {
  return (
    <div className="feedback-state feedback-state--error" role="alert">
      <AlertCircle size={24} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{description}</p>
      {onRetry && <Button variant="secondary" onClick={onRetry}>Try again</Button>}
    </div>
  )
}
