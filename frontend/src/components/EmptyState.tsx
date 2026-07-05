import type { ReactNode } from 'react'

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <div style={{ fontSize: 15, color: 'var(--text-dim)' }}>{title}</div>
      {hint && <div style={{ fontSize: 13 }}>{hint}</div>}
      {action}
    </div>
  )
}
