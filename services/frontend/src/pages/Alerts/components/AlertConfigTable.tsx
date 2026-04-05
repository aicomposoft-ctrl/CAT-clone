import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Table, Tag, Switch, Button, Space, Tooltip } from 'antd'
import type { TableColumnsType } from 'antd'
import { FileTextOutlined, ShopOutlined } from '@ant-design/icons'
import type { UseMutationResult } from '@tanstack/react-query'
import { AlertConfig, AlertConfigPage, AlertConfigUpdateRequest } from '../../../api/alerts'
import { skusApi, platformsApi } from '../../../api/catalog'

// ── Alert metadata (mirrors ALERT_META in index.tsx, scoped to config types) ──

const ALERT_META: Record<'content_drop' | 'oos', { label: string; color: string; icon: React.ReactNode }> = {
  content_drop: { label: 'Контент', color: 'orange', icon: <FileTextOutlined /> },
  oos: { label: 'Нет в наличии', color: 'red', icon: <ShopOutlined /> },
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  data: AlertConfigPage | undefined
  loading: boolean
  onEdit: (config: AlertConfig) => void
  onDelete: (config: AlertConfig) => void
  canManage: boolean
  page: number
  onPageChange: (page: number) => void
  updateMutation: UseMutationResult<
    AlertConfig,
    Error,
    { id: string; data: AlertConfigUpdateRequest },
    { prev: AlertConfigPage | undefined }
  >
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function AlertConfigTable({
  data,
  loading,
  onEdit,
  onDelete,
  canManage,
  page,
  onPageChange,
  updateMutation,
}: Props) {
  // Load SKUs and platforms from React Query cache for name enrichment
  const { data: skusData } = useQuery({
    queryKey: ['skus', { limit: 200 }],
    queryFn: () => skusApi.list({ limit: 200 }),
    staleTime: 5 * 60 * 1000,
  })

  const { data: platforms } = useQuery({
    queryKey: ['platforms'],
    queryFn: () => platformsApi.list(),
    staleTime: 5 * 60 * 1000,
  })

  const skuMap = useMemo(
    () => Object.fromEntries((skusData?.items ?? []).map((s) => [s.id, s.name])),
    [skusData],
  )

  const platformMap = useMemo(
    () => Object.fromEntries((platforms ?? []).map((p) => [p.id, p.name])),
    [platforms],
  )

  // ── Columns ────────────────────────────────────────────────────────────────

  const columns: TableColumnsType<AlertConfig> = [
    {
      title: 'Тип',
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 160,
      render: (v: 'content_drop' | 'oos') => {
        const meta = ALERT_META[v] ?? { label: v, color: 'default', icon: null }
        return (
          <Tag color={meta.color} icon={meta.icon}>
            {meta.label}
          </Tag>
        )
      },
    },
    {
      title: 'Охват',
      key: 'scope',
      width: 220,
      render: (_: unknown, record: AlertConfig) => {
        const skuName = record.sku_id ? (skuMap[record.sku_id] ?? record.sku_id) : null
        const platformName = record.platform_id
          ? (platformMap[record.platform_id] ?? record.platform_id)
          : null
        return (
          <Space direction="vertical" size={0}>
            <span>{skuName ? `SKU: ${skuName}` : 'Все SKU'}</span>
            <span style={{ color: '#8c8c8c', fontSize: 12 }}>
              {platformName ? `Площадка: ${platformName}` : 'Все'}
            </span>
          </Space>
        )
      },
    },
    {
      title: 'Порог',
      key: 'threshold',
      width: 90,
      render: (_: unknown, record: AlertConfig) =>
        record.alert_type === 'content_drop' && record.threshold !== null
          ? `≥ ${record.threshold}`
          : '—',
    },
    {
      title: 'Получатели',
      dataIndex: 'email_recipients',
      key: 'email_recipients',
      width: 220,
      render: (emails: string[]) => {
        if (!emails || emails.length === 0) return '—'
        const visible = emails.slice(0, 2)
        const hidden = emails.slice(2)
        return (
          <Space size={4} wrap>
            {visible.map((email) => (
              <span key={email}>{email}</span>
            ))}
            {hidden.length > 0 && (
              <Tooltip title={hidden.join(', ')}>
                <span style={{ color: '#1677ff', cursor: 'default' }}>+{hidden.length} ещё</span>
              </Tooltip>
            )}
          </Space>
        )
      },
    },
    {
      title: 'Активен',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 90,
      render: (isActive: boolean, record: AlertConfig) => (
        <Switch
          checked={isActive}
          disabled={!canManage}
          aria-label={`Активировать конфигурацию ${record.alert_type}`}
          onClick={
            canManage
              ? () =>
                  updateMutation.mutate({
                    id: record.id,
                    data: { is_active: !isActive },
                  })
              : undefined
          }
        />
      ),
    },
    ...(canManage
      ? [
          {
            title: 'Действия',
            key: 'actions',
            width: 130,
            render: (_: unknown, record: AlertConfig) => (
              <Space size={4}>
                <Button size="small" onClick={() => onEdit(record)}>
                  Изм.
                </Button>
                <Button size="small" danger onClick={() => onDelete(record)}>
                  Удал.
                </Button>
              </Space>
            ),
          } as TableColumnsType<AlertConfig>[number],
        ]
      : []),
  ]

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <Table<AlertConfig>
      dataSource={data?.items}
      columns={columns}
      rowKey="id"
      loading={loading}
      pagination={{
        current: page,
        pageSize: 50,
        total: data?.total,
        showTotal: (t) => `Всего ${t} конфигураций`,
        onChange: onPageChange,
      }}
      locale={{
        emptyText: 'Нет конфигураций — нажмите +, чтобы создать первую',
      }}
    />
  )
}
