import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { VideoOut } from '../api/types'

export const videosKey = ['videos'] as const

export function useVideos() {
  return useQuery({
    queryKey: videosKey,
    queryFn: () => api.get<VideoOut[]>('/videos'),
  })
}
