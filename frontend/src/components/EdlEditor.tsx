import { useState } from 'react'
import { clipThumbUrl } from '../api/client'
import type { ClipOut, EdlSegment } from '../api/types'
import { formatScore } from '../utils/format'
import styles from './EdlEditor.module.css'

export function EdlEditor({
  segments,
  clipsById,
  onChange,
}: {
  segments: EdlSegment[]
  clipsById: Map<number, ClipOut>
  onChange: (segments: EdlSegment[]) => void
}) {
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null)

  function reorder(from: number, to: number) {
    if (from === to) return
    const next = [...segments]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    onChange(next.map((seg, i) => ({ ...seg, order: i })))
  }

  function patchSegment(index: number, patch: Partial<EdlSegment>) {
    const next = segments.map((seg, i) => (i === index ? { ...seg, ...patch } : seg))
    onChange(next)
  }

  function removeSegment(index: number) {
    const next = segments.filter((_, i) => i !== index).map((seg, i) => ({ ...seg, order: i }))
    onChange(next)
  }

  if (segments.length === 0) {
    return <p style={{ color: 'var(--text-faint)' }}>No segments in this EDL.</p>
  }

  return (
    <div className={styles.list}>
      {segments.map((seg, index) => {
        const clip = clipsById.get(seg.clip_id)
        return (
          <div
            key={`${seg.clip_id}-${index}`}
            className={`card ${styles.row} ${draggingIndex === index ? styles.dragging : ''}`}
            draggable
            onDragStart={() => setDraggingIndex(index)}
            onDragEnd={() => setDraggingIndex(null)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => {
              if (draggingIndex !== null) reorder(draggingIndex, index)
              setDraggingIndex(null)
            }}
          >
            <span className={styles.handle}>⠿</span>
            {clip ? (
              <img className={styles.thumb} src={clipThumbUrl(clip.id)} alt={clip.category_name} />
            ) : (
              <div className={styles.thumb} />
            )}
            <div className={styles.info}>
              <strong>{clip?.category_name ?? `clip #${seg.clip_id}`}</strong>
              <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>
                {clip ? `score ${formatScore(clip.score)}` : ''}
              </span>
            </div>
            <div className={styles.trims}>
              <label className="label" style={{ margin: 0 }}>
                start
                <input
                  className="input"
                  type="number"
                  step="0.1"
                  value={seg.trim_start ?? 0}
                  onChange={(e) => patchSegment(index, { trim_start: Number(e.target.value) })}
                />
              </label>
              <label className="label" style={{ margin: 0 }}>
                end
                <input
                  className="input"
                  type="number"
                  step="0.1"
                  value={seg.trim_end ?? clip?.duration_s ?? 0}
                  onChange={(e) => patchSegment(index, { trim_end: Number(e.target.value) })}
                />
              </label>
            </div>
            <button className={styles.removeBtn} onClick={() => removeSegment(index)} title="Remove segment">
              ×
            </button>
          </div>
        )
      })}
    </div>
  )
}
