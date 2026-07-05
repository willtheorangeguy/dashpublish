import { Fragment, useState } from 'react'
import { EmptyState } from '../components/EmptyState'
import { ProgressBar } from '../components/ProgressBar'
import { useJobs } from '../store/jobs'
import { useScans } from '../store/scans'
import { formatDate } from '../utils/format'
import styles from './Status.module.css'

export function Status() {
  const { data: jobs, isLoading } = useJobs()
  const { data: scans } = useScans()
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  function toggleExpanded(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className={styles.page}>
      <h1>Status</h1>

      <section className={`card ${styles.section}`}>
        <h3>Jobs</h3>
        {isLoading && <EmptyState title="Loading jobs…" />}
        {!isLoading && (jobs?.length ?? 0) === 0 && <EmptyState title="No jobs yet" hint="Jobs appear here once you run a scan, plan, render, or upload." />}
        {!isLoading && (jobs?.length ?? 0) > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Status</th>
                <th className={styles.progressCell}>Progress</th>
                <th>Message</th>
                <th>Created</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(jobs ?? []).map((job) => (
                <Fragment key={job.id}>
                  <tr>
                    <td>#{job.id}</td>
                    <td>{job.type}</td>
                    <td>
                      <span className={`${styles.statusBadge} ${styles[job.status]}`}>{job.status}</span>
                    </td>
                    <td className={styles.progressCell}>
                      <ProgressBar value={job.progress} />
                    </td>
                    <td>{job.message ?? '--'}</td>
                    <td>{formatDate(job.created_at)}</td>
                    <td>
                      {job.status === 'failed' && job.error && (
                        <button className={styles.expandBtn} onClick={() => toggleExpanded(job.id)}>
                          {expanded.has(job.id) ? 'Hide error' : 'Show error'}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expanded.has(job.id) && job.error && (
                    <tr>
                      <td colSpan={7} className={styles.errorRow}>
                        {job.error}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className={`card ${styles.section}`}>
        <h3>Recent scans</h3>
        {(scans?.length ?? 0) === 0 ? (
          <EmptyState title="No scans yet" hint="Run one from the Library page." />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Clips found</th>
                <th>Started</th>
                <th>Finished</th>
              </tr>
            </thead>
            <tbody>
              {(scans ?? []).map((scan) => (
                <tr key={scan.id}>
                  <td>#{scan.id}</td>
                  <td>
                    <span className={`${styles.statusBadge} ${styles[scan.status]}`}>{scan.status}</span>
                  </td>
                  <td>{scan.clips_found}</td>
                  <td>{formatDate(scan.started_at)}</td>
                  <td>{scan.finished_at ? formatDate(scan.finished_at) : '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
