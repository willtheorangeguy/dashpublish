import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { JobOut } from '../api/types'

export const jobsKey = ['jobs'] as const

const ACTIVE_STATUSES = new Set(['queued', 'running'])

export function useJobs() {
  return useQuery({
    queryKey: jobsKey,
    queryFn: () => api.get<JobOut[]>('/jobs'),
    refetchInterval: (query) => {
      const jobs = query.state.data
      const hasActive = jobs?.some((j) => ACTIVE_STATUSES.has(j.status))
      return hasActive ? 2000 : false
    },
  })
}

/** Polls a single job by id every 1.5s while it is queued/running. */
export function useJob(id: number | null | undefined) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: () => api.get<JobOut>(`/jobs/${id}`),
    enabled: id !== null && id !== undefined,
    refetchInterval: (query) => {
      const job = query.state.data
      if (!job) return 1500
      return ACTIVE_STATUSES.has(job.status) ? 1500 : false
    },
  })
}
