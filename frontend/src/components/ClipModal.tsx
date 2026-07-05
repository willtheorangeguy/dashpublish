import { useState } from 'react'
import { clipStreamUrl } from '../api/client'
import type { ClipOut } from '../api/types'
import { usePatchClip } from '../store/clips'
import { useVideos } from '../store/videos'
import { formatDate, formatDuration, formatScore } from '../utils/format'
import styles from './ClipModal.module.css'

export function ClipModal({ clip, onClose }: { clip: ClipOut; onClose: () => void }) {
  const { data: videos } = useVideos()
  const patchClip = usePatchClip()
  const [newTag, setNewTag] = useState('')

  const video = videos?.find((v) => v.id === clip.video_id)
  const tagEntries = Object.entries(clip.user_tags ?? {})

  function addTag() {
    const key = newTag.trim()
    if (!key) return
    patchClip.mutate({
      id: clip.id,
      patch: { user_tags: { ...clip.user_tags, [key]: true } },
    })
    setNewTag('')
  }

  function removeTag(key: string) {
    const next = { ...clip.user_tags }
    delete next[key]
    patchClip.mutate({ id: clip.id, patch: { user_tags: next } })
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={`card ${styles.dialog}`} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h3 style={{ margin: 0 }}>{clip.category_name}</h3>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className={styles.videoWrap}>
          {/* Backend supports Range requests, so this streams directly. */}
          <video src={clipStreamUrl(clip.id)} controls autoPlay />
        </div>
        <div className={styles.body}>
          <div className={styles.metaGrid}>
            <span className="badge">score {formatScore(clip.score)}</span>
            <span className="chip">{formatDuration(clip.duration_s)}</span>
            <span className="chip">{formatDate(clip.created_at)}</span>
            <button
              className="btn btn-sm"
              onClick={() => patchClip.mutate({ id: clip.id, patch: { starred: !clip.starred } })}
            >
              {clip.starred ? '★ Starred' : '☆ Star'}
            </button>
            <button
              className="btn btn-sm"
              onClick={() => patchClip.mutate({ id: clip.id, patch: { hidden: !clip.hidden } })}
            >
              {clip.hidden ? 'Unhide' : 'Hide'}
            </button>
          </div>

          <div>
            <span className="label">Source video</span>
            <div className={styles.sourcePath}>
              {video ? `${video.path} (${video.camera ?? 'unknown cam'})` : `video #${clip.video_id}`}
            </div>
          </div>

          <div>
            <span className="label">Tags</span>
            <div className={styles.tagList}>
              {tagEntries.length === 0 && (
                <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>No tags yet</span>
              )}
              {tagEntries.map(([key]) => (
                <span key={key} className={`chip ${styles.tagChip}`}>
                  {key}
                  <button onClick={() => removeTag(key)} aria-label={`Remove ${key}`}>
                    ×
                  </button>
                </span>
              ))}
            </div>
            <div className={styles.addTagRow} style={{ marginTop: 8 }}>
              <input
                className="input"
                placeholder="Add tag and press Enter"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') addTag()
                }}
              />
              <button className="btn btn-sm" onClick={addTag}>
                Add
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
