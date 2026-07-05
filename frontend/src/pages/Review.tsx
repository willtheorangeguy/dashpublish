import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { compilationStreamUrl } from '../api/client'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState } from '../components/EmptyState'
import { useToast } from '../components/ToastContext'
import { useCompilation, useGenerateMetadata } from '../store/compilations'
import { usePublishGoLive, usePublishRecords, useUploadToYoutube } from '../store/publish'
import styles from './Review.module.css'

export function Review() {
  const params = useParams<{ id: string }>()
  const compilationId = Number(params.id)

  const { data: compilation, isLoading } = useCompilation(compilationId)
  const generateMetadata = useGenerateMetadata()
  const uploadToYoutube = useUploadToYoutube()
  const publishGoLive = usePublishGoLive()
  const { data: publishRecords } = usePublishRecords()
  const { showToast } = useToast()

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [newTag, setNewTag] = useState('')
  const [confirmPublish, setConfirmPublish] = useState(false)

  useEffect(() => {
    if (compilation?.title) setTitle(compilation.title)
  }, [compilation?.title])

  const record = useMemo(
    () =>
      (publishRecords ?? [])
        .filter((r) => r.compilation_id === compilationId)
        .sort((a, b) => (a.uploaded_at < b.uploaded_at ? 1 : -1))[0],
    [publishRecords, compilationId],
  )

  async function generate() {
    try {
      const meta = await generateMetadata.mutateAsync(compilationId)
      setTitle(meta.title)
      setDescription(meta.description)
      setTags(meta.tags)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to generate metadata', { tone: 'error' })
    }
  }

  function addTag() {
    const t = newTag.trim()
    if (!t || tags.includes(t)) return
    setTags([...tags, t])
    setNewTag('')
  }

  function removeTag(t: string) {
    setTags(tags.filter((x) => x !== t))
  }

  async function upload() {
    try {
      const rec = await uploadToYoutube.mutateAsync({ compilationId, body: { title, description, tags } })
      showToast(`Uploaded as private (${rec.youtube_video_id})`, { tone: 'success' })
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Upload failed', { tone: 'error' })
    }
  }

  async function publishPublic() {
    if (!record) return
    setConfirmPublish(false)
    try {
      await publishGoLive.mutateAsync(record.id)
      showToast('Published publicly', { tone: 'success' })
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Publish failed', { tone: 'error' })
    }
  }

  if (isLoading) return <EmptyState title="Loading compilation…" />
  if (!compilation) return <EmptyState title="Compilation not found" />

  const isPublished = !!record?.published_at

  return (
    <div className={styles.page}>
      <h1>Review — {compilation.title ?? `Compilation #${compilation.id}`}</h1>

      <section className={`card ${styles.section} ${styles.player}`}>
        {compilation.status === 'rendered' || compilation.status === 'uploaded' || compilation.status === 'published' ? (
          <video src={compilationStreamUrl(compilation.id)} controls />
        ) : (
          <EmptyState title={`Compilation status: ${compilation.status}`} hint="Render it from the Builder page first." />
        )}
      </section>

      <section className={`card ${styles.section}`}>
        <h3>Metadata</h3>
        <button className="btn btn-primary" onClick={generate} disabled={generateMetadata.isPending} style={{ alignSelf: 'flex-start' }}>
          {generateMetadata.isPending ? 'Generating…' : 'Generate metadata'}
        </button>

        <div className="field">
          <label className="label" htmlFor="rev-title">
            Title
          </label>
          <input id="rev-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="field">
          <label className="label" htmlFor="rev-desc">
            Description
          </label>
          <textarea
            id="rev-desc"
            className="textarea"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div className="field">
          <span className="label">Tags</span>
          <div className={styles.tagList}>
            {tags.map((t) => (
              <span key={t} className={`chip ${styles.tagChip}`}>
                {t}
                <button onClick={() => removeTag(t)} aria-label={`Remove ${t}`}>
                  ×
                </button>
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <input
              className="input"
              style={{ maxWidth: 220 }}
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

        <button
          className="btn btn-primary"
          onClick={upload}
          disabled={uploadToYoutube.isPending || !title}
          style={{ alignSelf: 'flex-start' }}
        >
          {uploadToYoutube.isPending ? 'Uploading…' : 'Upload to YouTube (private)'}
        </button>
      </section>

      {record && (
        <section className={`card ${styles.recordCard}`}>
          <h3 style={{ margin: 0 }}>Publish status</h3>
          <div className={styles.recordRow}>
            <span className={`${styles.privacyBadge} ${isPublished ? styles.public : styles.private}`}>
              {isPublished ? 'public' : record.privacy_status}
            </span>
            <a href={`https://www.youtube.com/watch?v=${record.youtube_video_id}`} target="_blank" rel="noreferrer">
              Watch on YouTube ↗
            </a>
          </div>
          {isPublished ? (
            <span style={{ color: 'var(--success)' }}>✅ Published{record.published_at ? ` at ${record.published_at}` : ''}</span>
          ) : (
            <button className="btn btn-primary" onClick={() => setConfirmPublish(true)} style={{ alignSelf: 'flex-start' }}>
              Publish public
            </button>
          )}
        </section>
      )}

      {confirmPublish && (
        <ConfirmDialog
          title="Publish this video publicly?"
          body="This flips the YouTube video from private to public. This action is visible to everyone immediately."
          confirmLabel="Publish"
          onConfirm={publishPublic}
          onCancel={() => setConfirmPublish(false)}
        />
      )}
    </div>
  )
}
