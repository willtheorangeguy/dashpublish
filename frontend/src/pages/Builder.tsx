import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { compilationStreamUrl } from '../api/client'
import type { ClipOut, CompilationCreate, CompilationProfile, EdlSegment } from '../api/types'
import { ClipCard } from '../components/ClipCard'
import { EdlEditor } from '../components/EdlEditor'
import { EmptyState } from '../components/EmptyState'
import { ProgressBar } from '../components/ProgressBar'
import { useToast } from '../components/ToastContext'
import { useClips } from '../store/clips'
import {
  useCompilation,
  useCreateCompilation,
  usePatchCompilation,
  usePlanCompilation,
  useRenderCompilation,
} from '../store/compilations'
import { useJob } from '../store/jobs'
import styles from './Builder.module.css'

type SourceMode = 'starred' | 'top' | 'manual'

export function Builder() {
  const [profile, setProfile] = useState<CompilationProfile>('short')
  const [source, setSource] = useState<SourceMode>('starred')
  const [manualSelected, setManualSelected] = useState<Set<number>>(new Set())
  const [musicPath, setMusicPath] = useState('')
  const [compilationId, setCompilationId] = useState<number | null>(null)
  const [planJobId, setPlanJobId] = useState<number | null>(null)
  const [renderJobId, setRenderJobId] = useState<number | null>(null)
  const [edlSegments, setEdlSegments] = useState<EdlSegment[] | null>(null)
  const [title, setTitle] = useState('')

  const { showToast } = useToast()
  const { data: allClips } = useClips({})
  const createCompilation = useCreateCompilation()
  const planCompilation = usePlanCompilation()
  const patchCompilation = usePatchCompilation()
  const renderCompilation = useRenderCompilation()
  const { data: compilation } = useCompilation(compilationId)
  const { data: planJob } = useJob(planJobId)
  const { data: renderJob } = useJob(renderJobId)

  const clipsById = useMemo(() => {
    const map = new Map<number, ClipOut>()
    ;(allClips ?? []).forEach((c) => map.set(c.id, c))
    return map
  }, [allClips])

  // Sync the local editable EDL copy whenever a fresh one arrives (initial
  // load of a draft, or right after "Plan with AI" finishes). Once the user
  // starts editing, edlSegments stays non-null so later polling refetches of
  // the same compilation don't clobber in-progress edits.
  useEffect(() => {
    if (compilation?.edl && edlSegments === null) {
      setEdlSegments(compilation.edl.segments ?? [])
    }
  }, [compilation, edlSegments])

  useEffect(() => {
    if (compilation?.title) setTitle(compilation.title)
  }, [compilation?.title])

  function toggleManual(id: number) {
    setManualSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function createDraft() {
    if (source === 'manual' && manualSelected.size === 0) {
      showToast('Select at least one clip for a manual compilation', { tone: 'error' })
      return
    }
    const body: CompilationCreate = { profile }
    if (source === 'manual') {
      body.clip_ids = Array.from(manualSelected)
    } else {
      body.from_selection = source
    }
    if (musicPath.trim()) body.music_path = musicPath.trim()

    try {
      const comp = await createCompilation.mutateAsync(body)
      setCompilationId(comp.id)
      setEdlSegments(null)
      setPlanJobId(null)
      setRenderJobId(null)
      showToast('Draft compilation created', { tone: 'success' })
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to create draft', { tone: 'error' })
    }
  }

  async function planWithAI() {
    if (!compilationId) return
    try {
      const job = await planCompilation.mutateAsync(compilationId)
      setPlanJobId(job.id)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to start planning', { tone: 'error' })
    }
  }

  function saveEdl() {
    if (!compilationId || !edlSegments || !compilation) return
    patchCompilation.mutate(
      {
        id: compilationId,
        patch: {
          title: title || undefined,
          edl: { ...(compilation.edl ?? { segments: [] }), segments: edlSegments },
        },
      },
      {
        onSuccess: () => showToast('Changes saved', { tone: 'success' }),
        onError: (err) => showToast(err instanceof Error ? err.message : 'Save failed', { tone: 'error' }),
      },
    )
  }

  async function renderNow() {
    if (!compilationId) return
    try {
      const job = await renderCompilation.mutateAsync(compilationId)
      setRenderJobId(job.id)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to start render', { tone: 'error' })
    }
  }

  const isPlanning = compilation?.status === 'planning'
  const isRendering = compilation?.status === 'rendering'
  const hasEdl = !!edlSegments

  return (
    <div className={styles.page}>
      <h1>Builder</h1>

      <section className={`card ${styles.section}`}>
        <h3>1. Profile</h3>
        <div className={styles.radioRow}>
          <label className={`${styles.radioCard} ${profile === 'short' ? styles.active : ''}`}>
            <input
              type="radio"
              name="profile"
              checked={profile === 'short'}
              onChange={() => setProfile('short')}
              style={{ display: 'none' }}
            />
            <strong>Short-form</strong>
            <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>
              9:16 vertical, center-cropped, ≤60s. Great for Shorts.
            </span>
          </label>
          <label className={`${styles.radioCard} ${profile === 'long' ? styles.active : ''}`}>
            <input
              type="radio"
              name="profile"
              checked={profile === 'long'}
              onChange={() => setProfile('long')}
              style={{ display: 'none' }}
            />
            <strong>Long-form</strong>
            <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>
              16:9, roughly 3-10 minutes, more segments strung together.
            </span>
          </label>
        </div>
      </section>

      <section className={`card ${styles.section}`}>
        <h3>2. Clip source</h3>
        <div className={styles.radioRow}>
          {(['starred', 'top', 'manual'] as SourceMode[]).map((mode) => (
            <label key={mode} className={`${styles.radioCard} ${source === mode ? styles.active : ''}`}>
              <input
                type="radio"
                name="source"
                checked={source === mode}
                onChange={() => setSource(mode)}
                style={{ display: 'none' }}
              />
              <strong style={{ textTransform: 'capitalize' }}>{mode}</strong>
              <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>
                {mode === 'starred' && 'Use everything you have starred.'}
                {mode === 'top' && 'Let the backend pick top-rated clips.'}
                {mode === 'manual' && 'Hand-pick clips below.'}
              </span>
            </label>
          ))}
        </div>

        {source === 'manual' && (
          <div className={styles.grid}>
            {(allClips ?? []).length === 0 && <EmptyState title="No clips available yet" />}
            {(allClips ?? []).map((clip) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                selectable
                selected={manualSelected.has(clip.id)}
                onToggleSelect={toggleManual}
              />
            ))}
          </div>
        )}

        <div className="field">
          <label className="label" htmlFor="music-path">
            Music path (optional)
          </label>
          <input
            id="music-path"
            className="input"
            placeholder="/path/to/music.mp3"
            value={musicPath}
            onChange={(e) => setMusicPath(e.target.value)}
          />
        </div>

        <div className={styles.actionRow}>
          <button className="btn btn-primary" onClick={createDraft} disabled={createCompilation.isPending}>
            {createCompilation.isPending ? 'Creating…' : 'Create draft'}
          </button>
          {compilation && <span className={styles.statusRow}>Draft #{compilation.id} · {compilation.status}</span>}
        </div>
      </section>

      {compilation && (
        <section className={`card ${styles.section}`}>
          <h3>3. Plan & edit</h3>

          {!hasEdl && (
            <div className={styles.actionRow}>
              <button className="btn btn-primary" onClick={planWithAI} disabled={planCompilation.isPending || isPlanning}>
                {isPlanning ? 'Planning…' : 'Plan with AI'}
              </button>
              {planJob && (planJob.status === 'queued' || planJob.status === 'running') && (
                <div style={{ flex: 1 }}>
                  <ProgressBar value={planJob.progress} />
                </div>
              )}
              {planJob?.status === 'failed' && (
                <span style={{ color: 'var(--danger)' }}>{planJob.error ?? 'Planning failed'}</span>
              )}
            </div>
          )}

          {hasEdl && (
            <>
              <div className="field">
                <label className="label" htmlFor="comp-title">
                  Title
                </label>
                <input
                  id="comp-title"
                  className="input"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>

              <EdlEditor segments={edlSegments ?? []} clipsById={clipsById} onChange={setEdlSegments} />

              <div className={styles.actionRow}>
                <button className="btn" onClick={saveEdl} disabled={patchCompilation.isPending}>
                  {patchCompilation.isPending ? 'Saving…' : 'Save changes'}
                </button>
                <button className="btn btn-primary" onClick={renderNow} disabled={renderCompilation.isPending || isRendering}>
                  {isRendering ? 'Rendering…' : 'Render'}
                </button>
                {renderJob && (renderJob.status === 'queued' || renderJob.status === 'running') && (
                  <div style={{ flex: 1 }}>
                    <ProgressBar value={renderJob.progress} />
                  </div>
                )}
                {renderJob?.status === 'failed' && (
                  <span style={{ color: 'var(--danger)' }}>{renderJob.error ?? 'Render failed'}</span>
                )}
              </div>
            </>
          )}

          {compilation.status === 'rendered' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <video src={compilationStreamUrl(compilation.id)} controls style={{ width: '100%', maxHeight: 420, background: '#000' }} />
              <Link className="btn btn-primary" to={`/review/${compilation.id}`} style={{ alignSelf: 'flex-start' }}>
                Go to Review →
              </Link>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
