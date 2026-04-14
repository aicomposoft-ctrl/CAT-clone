import { Select, Alert } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../store/authStore'
import apiClient from '../api/client'

interface SKUOption {
  id: string
  name: string
  article: string | null
  brand: { name: string }
}

interface SKUListResponse {
  items: SKUOption[]
  total: number
  next_cursor: string | null
}

interface Props {
  value: string | undefined
  onChange: (skuId: string | undefined) => void
  style?: React.CSSProperties
}

export function SKUSelector({ value, onChange, style }: Props) {
  const user = useAuthStore((s) => s.user)

  const { data, isLoading, isError } = useQuery<SKUListResponse>({
    queryKey: ['skus-list', user?.org_id],
    queryFn: () =>
      apiClient.get('/skus', { params: { page: 1, size: 200 } }).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
  })

  if (isError) {
    return <Alert type="error" message="Не удалось загрузить список SKU" banner />
  }

  const options = (data?.items ?? []).map((sku) => ({
    value: sku.id,
    label: `${sku.name}${sku.article ? ` (${sku.article})` : ''}`,
    title: sku.brand.name,
  }))

  return (
    <Select
      style={{ minWidth: 280, ...style }}
      placeholder="Выберите SKU"
      allowClear
      showSearch
      loading={isLoading}
      value={value}
      onChange={onChange}
      options={options}
      optionFilterProp="label"
      aria-label="Выберите SKU"
    />
  )
}
