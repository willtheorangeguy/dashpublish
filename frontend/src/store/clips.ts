import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ClipOut, ClipPatch, ClipsQuery } from '../api/types'

export function clipsKey(query: ClipsQuery = {}) {
  return ['clips', query] as const
}

export function useClips(query: ClipsQuery = {}) {
  return useQuery({
    queryKey: clipsKey(query),
    queryFn: () => api.get<ClipOut[]>('/clips', query as Record<string, unknown>),
  })
}

export function usePatchClip() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: ClipPatch }) =>
      api.patch<ClipOut>(`/clips/${id}`, patch),
    // Optimistically update every cached clip list containing this clip.
    onMutate: async ({ id, patch }) => {
      await queryClient.cancelQueries({ queryKey: ['clips'] })
      const previous = queryClient.getQueriesData<ClipOut[]>({ queryKey: ['clips'] })
      previous.forEach(([key, clips]) => {
        if (!clips) return
        queryClient.setQueryData<ClipOut[]>(
          key,
          clips.map((c) => (c.id === id ? { ...c, ...patch } : c)),
        )
      })
      return { previous }
    },
    onError: (_err, _vars, context) => {
      context?.previous.forEach(([key, clips]) => {
        queryClient.setQueryData(key, clips)
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['clips'] })
    },
  })
}
