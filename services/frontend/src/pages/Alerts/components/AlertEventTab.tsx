import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Table, Select, Button, Alert, Tag, Space } from 'antd'
import type { TableColumnsType } from 'antd'
import {
  BellOutlined,
  DollarOutlined,
  FileTextOutlined,
  ShopOutlined,
  CheckOutlined,
} from '@ant-design/icons'
import { alertsApi, AlertEvent } from '../../../api/alerts'
import { useAuthStore } from '../../../store/authStore'

const PAGE_SIZE = 50

const ALERT_META: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  content_drop: { label: 'Контент', color: 'orange', icon: <FileTextOutlined /> },
  oos: { label: 'Нет в наличии', color: 'red', icon: <ShopOutlined /> },
  price_change: { label: 'Цена', color: 'blue', icon: <DollarOutlined /> },
  competitor_promo: { label: 'Акция конкурента', color: 'purple', icon: <BellOutlined /> },
}

export default function AlertEventTab() {
  const [alertTypeFilter, setAlertTypeFilter] = useState<string | undefined>()
  const [showAcknowledged, setShowAcknowledged] = useState(false)
  const [page, setPage] = useState(1)
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()

  const filters = {
    alert_type: alertTypeFilter,
    is_sent: showAcknowledged ? undefined : false,
    page,
    size: PAGE_SIZE,
  }

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['alerts', filters],
    queryFn: () => alertsApi.list(filters),
    staleTime: 5 * 60 * 1000,
  })

  const acknowledgeMutation = useMutation({
    mutationFn: (id: string) => alertsApi.acknowledge(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      queryClient.invalidateQueries({ queryKey: ['alerts-count'] })
    },
  })

  const canAcknowledge = user?.role === 'admin' || user?.role === 'manager'

  const columns: TableColumnsType<AlertEvent> = [
    {
      title: 'Тип',
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 150,
      render: (v: string) => {
        const meta = ALERT_META[v] ?? { label: v, color: 'default', icon: <BellOutlined /> }
        return (
          <Tag color={meta.color} icon={meta.icon}>
            {meta.label}
          </Tag>
        )
      },
    },
    {
      title: 'Статус',
      dataIndex: 'is_sent',
      key: 'is_sent',
      width: 100,
      render: (v: boolean) =>
        v ? (
          <Tag color="default">Квитировано</Tag>
        ) : (
          <Tag color="red">Новый</Tag>
        ),
    },
    {
      title: 'Время',
      dataIndex: 'triggered_at',
      key: 'triggered_at',
      width: 150,
      render: (v: string) =>
        new Date(v).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }),
    },
    {
      title: 'До / После',
      key: 'values',
      width: 120,
      render: (_: unknown, record: AlertEvent) => (
        <span>
          {record.value_before !== null ? record.value_before?.toFixed(1) : '—'}
          {' → '}
          {record.value_after !== null ? record.value_after?.toFixed(1) : '—'}
        </span>
      ),
    },
    canAcknowledge
      ? {
          title: '',
          key: 'actions',
          width: 120,
          render: (_: unknown, record: AlertEvent) =>
            !record.is_sent ? (
              <Button
                size="small"
                icon={<CheckOutlined />}
                loading={acknowledgeMutation.isPending}
                onClick={(e) => {
                  e.stopPropagation()
                  acknowledgeMutation.mutate(record.id)
                }}
              >
                Квитировать
              </Button>
            ) : null,
        }
      : null,
  ].filter(Boolean) as TableColumnsType<AlertEvent>

  if (isError) {
    return (
      <Alert
        type="error"
        message="Ошибка загрузки алертов"
        action={<Button onClick={() => refetch()}>Повторить</Button>}
      />
    )
  }

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          placeholder="Тип алерта"
          allowClear
          value={alertTypeFilter}
          style={{ width: 180 }}
          onChange={(v) => { setAlertTypeFilter(v); setPage(1) }}
          options={Object.entries(ALERT_META).map(([key, meta]) => ({
            value: key,
            label: meta.label,
          }))}
        />
        <Button
          type={showAcknowledged ? 'primary' : 'default'}
          onClick={() => { setShowAcknowledged(!showAcknowledged); setPage(1) }}
        >
          {showAcknowledged ? 'Скрыть квитированные' : 'Показать все'}
        </Button>
      </Space>

      <Table<AlertEvent>
        dataSource={data?.items}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total: data?.total,
          showTotal: (total) => `Всего ${total} алертов`,
          onChange: (p) => setPage(p),
        }}
        locale={{
          emptyText: showAcknowledged
            ? 'Нет алертов'
            : 'Нет активных алертов — всё в порядке',
        }}
      />
    </div>
  )
}
