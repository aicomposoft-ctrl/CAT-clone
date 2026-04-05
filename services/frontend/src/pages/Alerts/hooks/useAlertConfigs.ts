import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  alertConfigsApi,
  AlertConfigCreateRequest,
  AlertConfigPage,
  AlertConfigUpdateRequest,
} from '../../../api/alerts'

export function useAlertConfigs(page = 1) {
  const queryClient = useQueryClient()
  const queryKey = ['alert-configs', { page }]

  const query = useQuery({
    queryKey,
    queryFn: () => alertConfigsApi.list({ page, size: 50 }),
    staleTime: 2 * 60 * 1000,
  })

  const createMutation = useMutation({
    mutationFn: (data: AlertConfigCreateRequest) => alertConfigsApi.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-configs'] }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: AlertConfigUpdateRequest }) =>
      alertConfigsApi.update(id, data),
    onMutate: async ({ id, data }) => {
      await queryClient.cancelQueries({ queryKey: ['alert-configs'] })
      const prev = queryClient.getQueryData<AlertConfigPage>(queryKey)
      queryClient.setQueryData<AlertConfigPage>(queryKey, (old) => {
        if (!old) return old
        return {
          ...old,
          items: old.items.map((item) =>
            item.id === id ? { ...item, ...data } : item
          ),
        }
      })
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(queryKey, ctx.prev)
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-configs'] }),
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => alertConfigsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-configs'] }),
  })

  return { query, createMutation, updateMutation, removeMutation }
}
