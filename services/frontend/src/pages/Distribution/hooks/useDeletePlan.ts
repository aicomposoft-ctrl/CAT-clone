import { useMutation, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { distributionApi } from '../../../api/stock'

export function useDeletePlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => distributionApi.deletePlan(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['distribution-plans'] })
      message.success('Plan row deleted')
    },
    onError: () => {
      message.error('Failed to delete — try again')
    },
  })
}
