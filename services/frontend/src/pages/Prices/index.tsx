import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Table,
  Typography,
  Row,
  Col,
  Card,
  Statistic,
  DatePicker,
  Select,
  Space,
  Tag,
  Empty,
  Alert,
  Button,
} from 'antd'
import type { TableColumnsType } from 'antd'
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import dayjs, { type Dayjs } from 'dayjs'
import { pricesApi, type PriceLatestItem, type PriceAnomaly, type PriceHistoryItem } from '../../api/prices'
import { SKUSelector } from '../../components/SKUSelector'
import { useAuthStore } from '../../store/authStore'

const { Title } = Typography
const { RangePicker } = DatePicker

function formatPrice(price: string | null | undefined): string {
  if (price == null) return '—'
  return `${parseFloat(price).toLocaleString('ru-RU')} ₽`
}

function formatPct(pct: string | null | undefined): string {
  if (pct == null) return '—'
  const n = parseFloat(pct)
  if (n === 0) return '0.0%'
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
}


function buildHistoryChart(items: PriceHistoryItem[]): EChartsOption {
  if (!items.length) return {}

  // O(n) build: platform → (date → price)
  const platformDatePrice = new Map<string, Map<string, number>>()
  for (const item of items) {
    const date = dayjs(item.collected_at).format('DD.MM')
    if (!platformDatePrice.has(item.platform_name)) {
      platformDatePrice.set(item.platform_name, new Map())
    }
    // last snapshot per date wins (intentional — intraday latest)
    platformDatePrice.get(item.platform_name)!.set(date, parseFloat(item.price))
  }

  const allDates = [...new Set(items.map((i) => dayjs(i.collected_at).format('DD.MM')))]

  const series = [...platformDatePrice.entries()].map(([name, dateMap]) => ({
    name,
    type: 'line' as const,
    smooth: true,
    data: allDates.map((d) => dateMap.get(d) ?? null),
    connectNulls: false,
  }))

  return {
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: unknown) =>
        v != null ? `${Number(v).toLocaleString('ru-RU')} ₽` : '—',
    },
    legend: { bottom: 0, type: 'scroll' },
    grid: { bottom: 40 },
    xAxis: { type: 'category', data: allDates, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { formatter: '{value} ₽' } },
    series,
  }
}

// Static column definitions — no component state captured
const anomalyColumns: TableColumnsType<PriceAnomaly> = [
  { title: 'Платформа', dataIndex: 'platform_name', key: 'platform_name', width: 140 },
  { title: 'Дата', dataIndex: 'date', key: 'date', width: 100 },
  { title: 'До', dataIndex: 'price_before', key: 'price_before', width: 110, render: formatPrice },
  { title: 'После', dataIndex: 'price_after', key: 'price_after', width: 110, render: formatPrice },
  {
    title: 'Изменение',
    key: 'change',
    width: 130,
    render: (_: unknown, row: PriceAnomaly) => {
      const pct = parseFloat(row.change_pct)
      const color = row.direction === 'down' ? '#ff4d4f' : '#52c41a'
      const icon = row.direction === 'down' ? <ArrowDownOutlined /> : <ArrowUpOutlined />
      return (
        <span style={{ color }} aria-label={`${row.direction === 'down' ? 'Снижение' : 'Рост'} ${Math.abs(pct).toFixed(1)}%`}>
          {icon} {Math.abs(pct).toFixed(1)}%
        </span>
      )
    },
  },
]

export default function PricesPage() {
  const orgId = useAuthStore((s) => s.user?.org_id)

  const [skuId, setSkuId] = useState<string | undefined>()
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(
    () => [dayjs().subtract(29, 'day'), dayjs()]
  )
  const [platformId, setPlatformId] = useState<string | undefined>()

  const dateFrom = dateRange[0].format('YYYY-MM-DD')
  const dateTo = dateRange[1].format('YYYY-MM-DD')

  const latestQuery = useQuery({
    queryKey: ['prices-latest', orgId, skuId],
    queryFn: () => {
      if (!skuId) throw new Error('skuId required')
      return pricesApi.latest(skuId)
    },
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const anomaliesQuery = useQuery({
    queryKey: ['prices-anomalies', orgId, skuId, dateFrom, dateTo],
    queryFn: () => {
      if (!skuId) throw new Error('skuId required')
      return pricesApi.anomalies(skuId, dateFrom, dateTo)
    },
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const historyQuery = useQuery({
    queryKey: ['prices-history', orgId, skuId, platformId, dateFrom, dateTo],
    queryFn: () => {
      if (!skuId) throw new Error('skuId required')
      return pricesApi.history(skuId, platformId, dateFrom, dateTo)
    },
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const statsQuery = useQuery({
    queryKey: ['prices-stats', orgId, skuId, platformId, dateFrom, dateTo],
    queryFn: () => {
      if (!skuId) throw new Error('skuId required')
      return pricesApi.stats(skuId, platformId, dateFrom, dateTo)
    },
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const platformOptions = useMemo(
    () =>
      (latestQuery.data?.items ?? []).map((item) => ({
        value: item.platform_id,
        label: item.platform_name,
      })),
    [latestQuery.data],
  )

  const latestColumns = useMemo<TableColumnsType<PriceLatestItem>>(
    () => [
      { title: 'Платформа', dataIndex: 'platform_name', key: 'platform_name', width: 140 },
      {
        title: 'Цена',
        dataIndex: 'price',
        key: 'price',
        width: 120,
        render: (v: string) => <strong>{formatPrice(v)}</strong>,
        sorter: (a, b) => parseFloat(a.price) - parseFloat(b.price),
      },
      {
        title: 'Без скидки',
        dataIndex: 'original_price',
        key: 'original_price',
        width: 120,
        render: formatPrice,
      },
      {
        title: 'Скидка',
        dataIndex: 'discount_pct',
        key: 'discount_pct',
        width: 90,
        render: (v: string) => {
          const n = parseFloat(v)
          return n > 0 ? <Tag color="orange">{n.toFixed(1)}%</Tag> : '—'
        },
      },
      {
        title: 'Акция',
        dataIndex: 'promo_label',
        key: 'promo_label',
        render: (v: string | null) => v ?? '—',
      },
      {
        title: 'Дешевле всех',
        key: 'cheapest',
        width: 110,
        render: (_: unknown, row: PriceLatestItem) =>
          row.platform_id === latestQuery.data?.cheapest_platform_id ? (
            <Tag color="success">Дешевле всех</Tag>
          ) : null,
      },
      {
        title: 'Обновлено',
        dataIndex: 'collected_at',
        key: 'collected_at',
        width: 130,
        render: (v: string) => dayjs(v).format('DD.MM.YYYY HH:mm'),
      },
    ],
    [latestQuery.data?.cheapest_platform_id],
  )

  const historyChartOption = useMemo(
    () => buildHistoryChart(historyQuery.data?.items ?? []),
    [historyQuery.data],
  )

  const stats = statsQuery.data
  const changePct = stats?.change_pct ? parseFloat(stats.change_pct) : null

  const handleSkuChange = useMemo(
    () => (v: string | undefined) => { setSkuId(v); setPlatformId(undefined) },
    [],
  )

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>Мониторинг цен</Title>

      <Row gutter={12} style={{ marginBottom: 24 }} align="middle">
        <Col>
          <SKUSelector value={skuId} onChange={handleSkuChange} />
        </Col>
        <Col>
          <RangePicker
            value={dateRange}
            onChange={(v) => v && setDateRange(v as [Dayjs, Dayjs])}
            format="DD.MM.YYYY"
            aria-label="Период"
            allowClear={false}
          />
        </Col>
      </Row>

      {!skuId ? (
        <Empty description="Выберите SKU для просмотра данных о ценах" style={{ marginTop: 60 }} />
      ) : (
        <>
          {/* Stats Cards */}
          {stats && (
            <Row gutter={16} style={{ marginBottom: 24 }}>
              {(
                [
                  { title: 'Мин. цена', value: formatPrice(stats.price_min) },
                  { title: 'Макс. цена', value: formatPrice(stats.price_max) },
                  { title: 'Средняя цена', value: formatPrice(stats.price_avg) },
                  {
                    title: 'Изменение',
                    value: formatPct(stats.change_pct),
                    valueStyle: changePct != null
                      ? { color: changePct < 0 ? '#ff4d4f' : '#52c41a' }
                      : undefined,
                  },
                ] as { title: string; value: string; valueStyle?: React.CSSProperties }[]
              ).map((card) => (
                <Col span={6} key={card.title}>
                  <Card size="small">
                    <Statistic
                      title={card.title}
                      value={card.value}
                      valueStyle={card.valueStyle}
                      loading={statsQuery.isLoading}
                    />
                  </Card>
                </Col>
              ))}
            </Row>
          )}

          {/* Latest Prices */}
          <Title level={4}>Актуальные цены</Title>
          {latestQuery.isError ? (
            <Alert
              type="error"
              message="Ошибка загрузки цен"
              action={<Button size="small" onClick={() => latestQuery.refetch()}>Повторить</Button>}
              style={{ marginBottom: 16 }}
            />
          ) : (
            <Table
              dataSource={latestQuery.data?.items ?? []}
              columns={latestColumns}
              rowKey="platform_id"
              loading={latestQuery.isLoading}
              pagination={false}
              size="small"
              rowClassName={(row) =>
                row.platform_id === latestQuery.data?.cheapest_platform_id ? 'row-cheapest' : ''
              }
              style={{ marginBottom: 24 }}
            />
          )}

          {/* Anomalies */}
          <Title level={4}>Аномалии цен</Title>
          {anomaliesQuery.isError ? (
            <Alert
              type="error"
              message="Ошибка загрузки аномалий"
              action={<Button size="small" onClick={() => anomaliesQuery.refetch()}>Повторить</Button>}
              style={{ marginBottom: 16 }}
            />
          ) : (
            <Table
              dataSource={anomaliesQuery.data?.items ?? []}
              columns={anomalyColumns}
              rowKey={(r) => `${r.platform_id}-${r.date}`}
              loading={anomaliesQuery.isLoading}
              pagination={{ pageSize: 20 }}
              size="small"
              locale={{ emptyText: 'Аномалий не обнаружено' }}
              style={{ marginBottom: 24 }}
            />
          )}

          {/* History Chart */}
          <Title level={4}>История цен</Title>
          <Space style={{ marginBottom: 12 }}>
            <Select
              placeholder="Все платформы"
              allowClear
              style={{ width: 200 }}
              options={platformOptions}
              value={platformId}
              onChange={setPlatformId}
            />
          </Space>
          {historyQuery.isError ? (
            <Alert type="error" message="Ошибка загрузки истории" style={{ marginBottom: 16 }} />
          ) : historyQuery.data?.items.length ? (
            <ReactECharts
              option={historyChartOption}
              style={{ height: 300 }}
              notMerge={false}
              lazyUpdate
            />
          ) : (
            <Empty
              description={historyQuery.isLoading ? 'Загрузка...' : 'Нет данных за выбранный период'}
              style={{ height: 200 }}
            />
          )}
        </>
      )}

      {/* CSS for cheapest row highlight — static, no user data interpolated */}
      <style>{`.row-cheapest td { background-color: #f6ffed !important; }`}</style>
    </div>
  )
}

