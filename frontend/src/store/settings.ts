import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { SettingsOut, SettingsPatch } from '../api/types'

export const settingsKey = ['settings'] as const

export function useSettings() {
  return useQuery({
    queryKey: settingsKey,
    queryFn: () => api.get<SettingsOut>('/settings'),
  })
}

export function usePatchSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patch: SettingsPatch) => api.put<SettingsOut>('/settings', patch),
    onSuccess: (settings) => queryClient.setQueryData(settingsKey, settings),
  })
}
