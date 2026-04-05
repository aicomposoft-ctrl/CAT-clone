import { useState } from 'react'
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
import dayjs, { Dayjs } from 'dayjs'
import { pricesApi, PriceLatestItem, PriceAnomaly, PriceHistoryItem } from '../../api/prices'
import { SKUSelector } from '../../components/SKUSelector'

const { Title } = Typography
const { RangePicker } = DatePicker

const DEFAULT_RANGE: [Dayjs, Dayjs] = [dayjs().subtract(29, 'day'), dayjs()]

function formatPrice(price: string | null): string {
  if (!price) return '—'
  return `${parseFloat(price).toLocaleString('ru-RU')} ₽`
}

function formatPct(pct: string | null): string {
  if (!pct) return '—'
  const n = parseFloat(pct)
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
}

function buildHistoryChart(items: PriceHistoryItem[]): EChartsOption {
  if (!items.length) return {}

  // Group by platform
  const platformMap: Record<string, { dates: string[]; prices: number[] }> = {}
  for (const item of items) {
    const date = dayjs(item.collected_at).format('DD.MM')
    if (!platformMap[item.platform_name]) {
      platformMap[item.platform_name] = { dates: [], prices: [] }
    }
    platformMap[item.platform_name].dates.push(date)
    platformMap[item.platform_name].prices.push(parseFloat(item.price))
  }

  // Collect all unique dates in order
  const allDates = [...new Set(items.map((i) => dayjs(i.collected_at).format('DD.MM')))]

  const series = Object.entries(platformMap).map(([name, data]) => ({
    name,
    type: 'line' as const,
    smooth: true,
    data: allDates.map((d) => {
      const idx = data.dates.lastIndexOf(d)
      return idx >= 0 ? data.prices[idx] : null
    }),
    connectNulls: false,
  }))

  return {
    tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => (v != null ? `${Number(v).toLocaleString('ru-RU')} ₽` : '—') },
    legend: { bottom: 0, type: 'scroll' },
    grid: { bottom: 40 },
    xAxis: { type: 'category', data: allDates, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', axisLabel: { formatter: '{value} ₽' } },
    series,
  }
}

export default function PricesPage() {
  const [skuId, setSkuId] = useState<string | undefined>()
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(DEFAULT_RANGE)
  const [platformId, setPlatformId] = useState<string | undefined>()

  const dateFrom = dateRange?.[0].format('YYYY-MM-DD')
  const dateTo = dateRange?.[1].format('YYYY-MM-DD')

  const latestQuery = useQuery({
    queryKey: ['prices-latest', skuId],
    queryFn: () => pricesApi.latest(skuId!),
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const anomaliesQuery = useQuery({
    queryKey: ['prices-anomalies', skuId, dateFrom, dateTo],
    queryFn: () => pricesApi.anomalies(skuId!, dateFrom, dateTo),
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const historyQuery = useQuery({
    queryKey: ['prices-history', skuId, platformId, dateFrom, dateTo],
    queryFn: () => pricesApi.history(skuId!, platformId, dateFrom, dateTo),
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const statsQuery = useQuery({
    queryKey: ['prices-stats', skuId, platformId, dateFrom, dateTo],
    queryFn: () => pricesApi.stats(skuId!, platformId, dateFrom, dateTo),
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  // Platform options from latest prices data
  const platformOptions = (latestQuery.data?.items ?? []).map((item) => ({
    value: item.platform_id,
    label: item.platform_name,
  }))

  const latestColumns: TableColumnsType<PriceLatestItem> = [
    {
      title: 'Платформа',
      dataIndex: 'platform_name',
      key: 'platform_name',
      width: 140,
    },
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
  ]

  const anomalyColumns: TableColumnsType<PriceAnomaly> = [
    { title: 'Платформа', dataIndex: 'platform_name', key: 'platform_name', width: 140 },
    { title: 'Дата', dataIndex: 'date', key: 'date', width: 100 },
    { title: 'До', dataIndex: 'price_before', key: 'price_before', width: 110, render: formatPrice },
    { title: 'После', dataIndex: 'price_after', key: 'price_after', width: 110, render: formatPrice },
    {
      title: 'Изменение',
      key: 'change',
      width: 120,
      render: (_: unknown, row: PriceAnomaly) => {
        const pct = parseFloat(row.change_pct)
        const color = row.direction === 'down' ? '#ff4d4f' : '#52c41a'
        const icon = row.direction === 'down' ? <ArrowDownOutlined /> : <ArrowUpOutlined />
        return (
          <span style={{ color }}>
            {icon} {Math.abs(pct).toFixed(1)}%
          </span>
        )
      },
    },
  ]

  const stats = statsQuery.data

  return (
    <div style={{ padding: '24px' }}>
      <Title level={3}>Мониторинг цен</Title>

      {/* Filters */}
      <Row gutter={12} style={{ marginBottom: 24 }} align="middle">
        <Col>
          <SKUSelector value={skuId} onChange={(v) => { setSkuId(v); setPlatformId(undefined) }} />
        </Col>
        <Col>
          <RangePicker
            value={dateRange}
            onChange={(v) => setDateRange(v as [Dayjs, Dayjs] | null)}
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
              {[
                { title: 'Мин. цена', value: formatPrice(stats.price_min) },
                { title: 'Макс. цена', value: formatPrice(stats.price_max) },
                { title: 'Средняя цена', value: formatPrice(stats.price_avg) },
                {
                  title: 'Изменение',
                  value: formatPct(stats.change_pct),
                  valueStyle: stats.change_pct
                    ? { color: parseFloat(stats.change_pct) < 0 ? '#ff4d4f' : '#52c41a' }
                    : undefined,
                },
              ].map((card) => (
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
              option={buildHistoryChart(historyQuery.data.items)}
              style={{ height: 300 }}
              notMerge
            />
          ) : (
            <Empty description={historyQuery.isLoading ? 'Загрузка...' : 'Нет данных за выбранный период'} style={{ height: 200 }} />
          )}
        </>
      )}

      <style>{`.row-cheapest td { background-color: #f6ffed !important; }`}</style>
    </div>
  )
}
