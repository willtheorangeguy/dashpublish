import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { PublishRecordOut, PublishUploadBody } from '../api/types'

export const publishKey = ['publish'] as const

export function usePublishRecords() {
  return useQuery({
    queryKey: publishKey,
    queryFn: () => api.get<PublishRecordOut[]>('/publish'),
  })
}

export function useUploadToYoutube() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ compilationId, body }: { compilationId: number; body: PublishUploadBody }) =>
      api.post<PublishRecordOut>(`/publish/${compilationId}/upload`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: publishKey }),
  })
}

export function usePublishGoLive() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (publishId: number) => api.post<PublishRecordOut>(`/publish/${publishId}/publish`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: publishKey }),
  })
}
