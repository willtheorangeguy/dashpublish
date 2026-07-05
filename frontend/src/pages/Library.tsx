import { useMemo, useState } from 'react'
import { ClipCard } from '../components/ClipCard'
import { ClipModal } from '../components/ClipModal'
import { EmptyState } from '../components/EmptyState'
import { useToast } from '../components/ToastContext'
import { useCategories } from '../store/categories'
import { useClips } from '../store/clips'
import { useStartScan } from '../store/scans'
import type { ClipOut, ClipSort } from '../api/types'
import styles from './Library.module.css'

export function Library() {
  const [starredOnly, setStarredOnly] = useState(false)
  const [minScore, setMinScore] = useState(0)
  const [sort, setSort] = useState<ClipSort>('newest')
  const [selectedCategories, setSelectedCategories] = useState<Set<number>>(new Set())
  const [openClip, setOpenClip] = useState<ClipOut | null>(null)

  const { data: categories } = useCategories()
  // Category multi-select is filtered client-side: the REST contract exposes a
  // single `category` id, not a repeatable multi-value param.
  const { data: clips, isLoading } = useClips({
    starred: starredOnly || undefined,
    hidden: false,
    min_score: minScore || undefined,
    sort,
  })
  const startScan = useStartScan()
  const { showToast } = useToast()

  const visibleClips = useMemo(() => {
    if (!clips) return []
    if (selectedCategories.size === 0) return clips
    return clips.filter((c) => selectedCategories.has(c.category_id))
  }, [clips, selectedCategories])

  function toggleCategory(id: number) {
    setSelectedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function runScan() {
    try {
      const job = await startScan.mutateAsync()
      showToast(`Scan started (job #${job.id})`, { linkTo: '/status', linkLabel: 'View status', tone: 'success' })
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to start scan', { tone: 'error' })
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Library</h1>
        <button className="btn btn-primary" onClick={runScan} disabled={startScan.isPending}>
          {startScan.isPending ? 'Starting…' : 'Run scan'}
        </button>
      </div>

      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <div className={styles.filterGroup}>
            <span className={styles.filterTitle}>Category</span>
            {(categories ?? []).map((c) => (
              <label key={c.id} className={styles.checkRow}>
                <input
                  type="checkbox"
                  checked={selectedCategories.has(c.id)}
                  onChange={() => toggleCategory(c.id)}
                />
                {c.name}
              </label>
            ))}
            {categories?.length === 0 && (
              <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>No categories yet</span>
            )}
          </div>

          <div className={styles.filterGroup}>
            <span className={styles.filterTitle}>Filters</span>
            <label className={styles.checkRow}>
              <input
                type="checkbox"
                checked={starredOnly}
                onChange={(e) => setStarredOnly(e.target.checked)}
              />
              Starred only
            </label>
          </div>

          <div className={styles.filterGroup}>
            <span className={styles.filterTitle}>Min score: {minScore.toFixed(2)}</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
            />
          </div>

          <div className={styles.filterGroup}>
            <span className={styles.filterTitle}>Sort</span>
            <select className="select" value={sort} onChange={(e) => setSort(e.target.value as ClipSort)}>
              <option value="newest">Newest</option>
              <option value="score">Score</option>
            </select>
          </div>
        </aside>

        <div>
          {isLoading && <EmptyState title="Loading clips…" />}
          {!isLoading && visibleClips.length === 0 && (
            <EmptyState
              title="No clips found"
              hint="Run a scan or adjust your filters to see detected clips here."
            />
          )}
          {!isLoading && visibleClips.length > 0 && (
            <div className={styles.grid}>
              {visibleClips.map((clip) => (
                <ClipCard key={clip.id} clip={clip} onOpen={setOpenClip} />
              ))}
            </div>
          )}
        </div>
      </div>

      {openClip && <ClipModal clip={openClip} onClose={() => setOpenClip(null)} />}
    </div>
  )
}
