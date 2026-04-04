import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  Table,
  Select,
  DatePicker,
  Button,
  Space,
  Typography,
  Alert,
} from 'antd'
import type { TableColumnsType } from 'antd'
import dayjs from 'dayjs'
import { contentApi, ContentScoreItem } from '../../api/content'
import { ScoreBadge, getScoreRowStyle } from '../../components/ScoreBadge'
import { ContentDrillDrawer } from './components/ContentDrillDrawer'

const { Title } = Typography

const PAGE_SIZE = 50

export default function ContentPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  const filters = {
    platform_id: searchParams.get('platform_id') ?? undefined,
    brand_id: searchParams.get('brand_id') ?? undefined,
    score_max: searchParams.get('score_max') ? Number(searchParams.get('score_max')) : undefined,
    scored_at: searchParams.get('scored_at') ?? undefined,
    page,
    size: PAGE_SIZE,
  }

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['content-scores', filters],
    queryFn: () => contentApi.list(filters),
    staleTime: 5 * 60 * 1000,
  })

  const updateFilter = (key: string, value: string | undefined) => {
    setPage(1)
    setSearchParams((prev) => {
      if (!value) prev.delete(key)
      else prev.set(key, value)
      return prev
    })
  }

  const columns: TableColumnsType<ContentScoreItem> = [
    {
      title: 'Платформа',
      dataIndex: 'platform_name',
      key: 'platform_name',
      width: 130,
      render: (v: string, row) =>
        row.platform_url ? (
          <a href={row.platform_url} target="_blank" rel="noreferrer">
            {v}
          </a>
        ) : (
          v
        ),
    },
    { title: 'Бренд', dataIndex: 'brand_name', key: 'brand_name', width: 120 },
    { title: 'Артикул', dataIndex: 'article', key: 'article', width: 90 },
    {
      title: 'SKU',
      dataIndex: 'sku_name',
      key: 'sku_name',
      ellipsis: true,
    },
    {
      title: 'Content Total',
      dataIndex: 'content_total',
      key: 'content_total',
      width: 120,
      sorter: true,
      render: (v: number | null) => <ScoreBadge score={v} />,
    },
    {
      title: 'Изображение',
      dataIndex: 'image_score',
      key: 'image_score',
      width: 110,
      render: (v: number | null) => <ScoreBadge score={v} />,
    },
    {
      title: 'Описание',
      dataIndex: 'description_score',
      key: 'description_score',
      width: 100,
      render: (v: number | null) => <ScoreBadge score={v} />,
    },
    {
      title: 'Состав',
      dataIndex: 'composition_score',
      key: 'composition_score',
      width: 90,
      render: (v: number | null) => <ScoreBadge score={v} />,
    },
    {
      title: 'Дата',
      dataIndex: 'scored_at',
      key: 'scored_at',
      width: 110,
    },
  ]

  if (isError) {
    return (
      <Alert
        type="error"
        message="Ошибка загрузки контент-скоров"
        action={<Button onClick={() => refetch()}>Повторить</Button>}
      />
    )
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        Контент
      </Title>

      {/* Filters */}
      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          placeholder="Фильтр по скору"
          allowClear
          value={searchParams.get('score_max') ?? undefined}
          style={{ width: 180 }}
          onChange={(v) => updateFilter('score_max', v)}
          options={[
            { value: '50', label: 'Ниже 50% (красная зона)' },
            { value: '80', label: 'Ниже 80% (требует внимания)' },
          ]}
        />
        <DatePicker
          placeholder="Выберите дату"
          value={searchParams.get('scored_at') ? dayjs(searchParams.get('scored_at')) : null}
          onChange={(_, str) => updateFilter('scored_at', str as string || undefined)}
        />
        <Button
          onClick={() => {
            setSearchParams(new URLSearchParams())
            setPage(1)
          }}
        >
          Сбросить фильтры
        </Button>
        <Button
          onClick={async () => {
            // Authenticated download via apiClient — window.open would send no Authorization header
            const params = new URLSearchParams(Object.fromEntries(searchParams))
            try {
              const response = await import('../../api/client').then(m =>
                m.default.get(`/reports/content-export?${params.toString()}`, {
                  responseType: 'blob',
                  timeout: 60000,
                })
              )
              const url = URL.createObjectURL(response.data)
              const a = document.createElement('a')
              a.href = url
              a.download = `content_scores_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.xlsx`
              a.click()
              URL.revokeObjectURL(url)
            } catch {
              // Toast handled by global error interceptor
            }
          }}
        >
          Экспорт в Excel
        </Button>
      </Space>

      {/* Table */}
      <Table<ContentScoreItem>
        dataSource={data?.items}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        virtual
        scroll={{ y: 600 }}
        rowClassName={(record) => {
          const score = record.content_total
          if (score === null || score === undefined) return ''
          if (score < 50) return 'row-red'
          if (score < 80) return 'row-yellow'
          return ''
        }}
        onRow={(record) => ({
          onClick: () => {
            setSelectedId(record.sku_platform_id)
            setDrawerOpen(true)
          },
          style: { cursor: 'pointer', ...getScoreRowStyle(record.content_total) },
        })}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total: data?.total,
          showTotal: (total) => `Всего ${total} записей`,
          onChange: (p) => setPage(p),
        }}
        locale={{ emptyText: 'Нет SKU по выбранным фильтрам' }}
      />

      {/* Drill-down drawer */}
      {selectedId && (
        <ContentDrillDrawer
          skuPlatformId={selectedId}
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
        />
      )}
    </div>
  )
}
