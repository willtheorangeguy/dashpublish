import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type {
  CompilationCreate,
  CompilationOut,
  CompilationPatch,
  JobOut,
  MetadataOut,
} from '../api/types'

export const compilationsKey = ['compilations'] as const
export const compilationKey = (id: number) => ['compilation', id] as const

const ACTIVE_STATUSES = new Set(['planning', 'rendering'])

export function useCompilations() {
  return useQuery({
    queryKey: compilationsKey,
    queryFn: () => api.get<CompilationOut[]>('/compilations'),
  })
}

export function useCompilation(id: number | null | undefined) {
  return useQuery({
    queryKey: compilationKey(id ?? -1),
    queryFn: () => api.get<CompilationOut>(`/compilations/${id}`),
    enabled: id !== null && id !== undefined,
    refetchInterval: (query) => {
      const comp = query.state.data
      if (!comp) return false
      return ACTIVE_STATUSES.has(comp.status) ? 1500 : false
    },
  })
}

export function useCreateCompilation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CompilationCreate) => api.post<CompilationOut>('/compilations', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: compilationsKey }),
  })
}

export function usePlanCompilation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post<JobOut>(`/compilations/${id}/plan`),
    onSuccess: (_job, id) => queryClient.invalidateQueries({ queryKey: compilationKey(id) }),
  })
}

export function usePatchCompilation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: CompilationPatch }) =>
      api.patch<CompilationOut>(`/compilations/${id}`, patch),
    onSuccess: (comp) => {
      queryClient.setQueryData(compilationKey(comp.id), comp)
      queryClient.invalidateQueries({ queryKey: compilationsKey })
    },
  })
}

export function useRenderCompilation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post<JobOut>(`/compilations/${id}/render`),
    onSuccess: (_job, id) => queryClient.invalidateQueries({ queryKey: compilationKey(id) }),
  })
}

export function useGenerateMetadata() {
  return useMutation({
    mutationFn: (id: number) => api.post<MetadataOut>(`/compilations/${id}/metadata`),
  })
}
