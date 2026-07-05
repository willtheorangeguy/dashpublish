import { useState } from 'react'
import { clipThumbUrl } from '../api/client'
import type { ClipOut } from '../api/types'
import { usePatchClip } from '../store/clips'
import { formatDuration, formatScore } from '../utils/format'
import styles from './ClipCard.module.css'

export function ClipCard({
  clip,
  onOpen,
  selectable,
  selected,
  onToggleSelect,
}: {
  clip: ClipOut
  onOpen?: (clip: ClipOut) => void
  selectable?: boolean
  selected?: boolean
  onToggleSelect?: (id: number) => void
}) {
  const [thumbFailed, setThumbFailed] = useState(false)
  const patchClip = usePatchClip()

  function handleClick() {
    if (selectable) {
      onToggleSelect?.(clip.id)
    } else {
      onOpen?.(clip)
    }
  }

  function toggleStar(e: React.MouseEvent) {
    e.stopPropagation()
    patchClip.mutate({ id: clip.id, patch: { starred: !clip.starred } })
  }

  function toggleHide(e: React.MouseEvent) {
    e.stopPropagation()
    patchClip.mutate({ id: clip.id, patch: { hidden: !clip.hidden } })
  }

  return (
    <div className={`card ${styles.card}`} onClick={handleClick}>
      <div className={styles.thumbWrap}>
        {thumbFailed ? (
          <div className={styles.thumbFallback}>no preview</div>
        ) : (
          <img
            className={styles.thumb}
            src={clipThumbUrl(clip.id)}
            alt={clip.category_name}
            loading="lazy"
            onError={() => setThumbFailed(true)}
          />
        )}
        <div className={styles.badgeRow}>
          <span className="chip">{clip.category_name}</span>
          <span className="badge">{formatScore(clip.score)}</span>
        </div>
        <span className={styles.duration}>{formatDuration(clip.duration_s)}</span>
        {selectable && (
          <div className={`${styles.selectMark} ${selected ? styles.checked : ''}`} />
        )}
      </div>
      {!selectable && (
        <div className={styles.body}>
          <div className={styles.metaRow}>
            <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>
              {clip.hidden ? 'hidden' : ' '}
            </span>
            <div className={styles.actions}>
              <button
                className={`${styles.iconBtn} ${clip.starred ? styles.starred : ''}`}
                onClick={toggleStar}
                title={clip.starred ? 'Unstar' : 'Star'}
              >
                {clip.starred ? '★' : '☆'}
              </button>
              <button
                className={styles.iconBtn}
                onClick={toggleHide}
                title={clip.hidden ? 'Unhide' : 'Hide'}
              >
                {clip.hidden ? '\u{1F441}' : '\u{1F6AB}'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
