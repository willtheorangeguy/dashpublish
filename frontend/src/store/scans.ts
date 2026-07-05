import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { JobOut, ScanOut } from '../api/types'
import { jobsKey } from './jobs'

export const scansKey = ['scans'] as const

export function useScans() {
  return useQuery({
    queryKey: scansKey,
    queryFn: () => api.get<ScanOut[]>('/scans'),
  })
}

export function useStartScan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<JobOut>('/scans'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scansKey })
      queryClient.invalidateQueries({ queryKey: jobsKey })
    },
  })
}
