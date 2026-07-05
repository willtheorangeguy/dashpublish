import styles from './ConfirmDialog.module.css'

export function ConfirmDialog({
  title,
  body,
  confirmLabel = 'Confirm',
  danger,
  onConfirm,
  onCancel,
}: {
  title: string
  body?: string
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div className={`card ${styles.dialog}`} onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        {body && <p style={{ margin: 0, color: 'var(--text-dim)' }}>{body}</p>}
        <div className={styles.actions}>
          <button className="btn" onClick={onCancel}>
            Cancel
          </button>
          <button className={danger ? 'btn btn-danger' : 'btn btn-primary'} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
