import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import styles from './Toast.module.css'

interface Toast {
  id: number
  message: string
  linkTo?: string
  linkLabel?: string
  tone?: 'info' | 'success' | 'error'
}

interface ToastOptions {
  linkTo?: string
  linkLabel?: string
  tone?: Toast['tone']
  durationMs?: number
}

interface ToastContextValue {
  showToast: (message: string, options?: ToastOptions) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const showToast = useCallback((message: string, options: ToastOptions = {}) => {
    const id = nextId++
    setToasts((prev) => [
      ...prev,
      { id, message, linkTo: options.linkTo, linkLabel: options.linkLabel, tone: options.tone ?? 'info' },
    ])
    const duration = options.durationMs ?? 5000
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, duration)
  }, [])

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className={styles.stack}>
        {toasts.map((t) => (
          <div key={t.id} className={`${styles.toast} ${styles[t.tone ?? 'info']}`}>
            <span>{t.message}</span>
            {t.linkTo && (
              <Link to={t.linkTo} onClick={() => dismiss(t.id)}>
                {t.linkLabel ?? 'View'}
              </Link>
            )}
            <button className={styles.close} onClick={() => dismiss(t.id)} aria-label="Dismiss">
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
