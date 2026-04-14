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
  Progress,
  Empty,
  Alert,
  Button,
  Rate,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { StarFilled } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import dayjs, { type Dayjs } from 'dayjs'
import { reviewsApi, type ReviewSummaryItem, type ReviewHistoryItem, type ReviewStats } from '../../api/reviews'
import { escHtml } from '../../api/utils'
import { SKUSelector } from '../../components/SKUSelector'
import { useAuthStore } from '../../store/authStore'

const { Title } = Typography
const { RangePicker } = DatePicker

const SENTIMENT_LABELS: Record<string, { label: string; color: string }> = {
  positive: { label: 'Позитив', color: 'success' },
  neutral: { label: 'Нейтрально', color: 'default' },
  negative: { label: 'Негатив', color: 'error' },
}

function SentimentTag({ sentiment }: { sentiment: 'positive' | 'neutral' | 'negative' | null }) {
  if (!sentiment) return <Tag color="default">Ожидает классификации</Tag>
  const { label, color } = SENTIMENT_LABELS[sentiment]
  return <Tag color={color}>{label}</Tag>
}

function buildSentimentPie(stats: ReviewStats | undefined): EChartsOption {
  if (!stats?.sentiment_share) return {}
  const { positive, neutral, negative } = stats.sentiment_share
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '45%'],
        label: { formatter: '{b}\n{d}%' },
        data: [
          { name: 'Позитив', value: parseFloat(positive), itemStyle: { color: '#52c41a' } },
          { name: 'Нейтрально', value: parseFloat(neutral), itemStyle: { color: '#8c8c8c' } },
          { name: 'Негатив', value: parseFloat(negative), itemStyle: { color: '#ff4d4f' } },
        ],
      },
    ],
  }
}

function buildTrendChart(stats: ReviewStats | undefined): EChartsOption {
  if (!stats?.weekly_trend?.length) return {}
  const trend = stats.weekly_trend
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        if (!Array.isArray(params) || !params[0]) return ''
        const p = params[0] as { name: string; value: number }
        return `${escHtml(String(p.name))}: ${escHtml(String(p.value))}% позитивных`
      },
    },
    xAxis: {
      type: 'category',
      data: trend.map((t) => dayjs(t.week_start).format('DD.MM')),
      axisLabel: { rotate: 30 },
    },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      {
        type: 'bar',
        data: trend.map((t) => parseFloat(t.positive_share)),
        itemStyle: { color: '#52c41a' },
        label: { show: false },
      },
    ],
    grid: { bottom: 40 },
  }
}

// Static column definitions — no component state captured
const summaryColumns: TableColumnsType<ReviewSummaryItem> = [
  { title: 'Платформа', dataIndex: 'platform_name', key: 'platform_name', width: 140 },
  {
    title: 'Отзывов',
    dataIndex: 'review_count',
    key: 'review_count',
    width: 90,
    sorter: (a, b) => a.review_count - b.review_count,
  },
  {
    title: 'Рейтинг',
    dataIndex: 'avg_rating',
    key: 'avg_rating',
    width: 100,
    render: (v: string | null) =>
      v ? (
        <Space size={4}>
          <StarFilled style={{ color: '#faad14' }} />
          {parseFloat(v).toFixed(1)}
        </Space>
      ) : (
        '—'
      ),
  },
  {
    title: 'Позитив',
    dataIndex: 'positive_pct',
    key: 'positive_pct',
    width: 150,
    render: (v: string) => (
      <Progress
        percent={Math.round(parseFloat(v))}
        size="small"
        status="success"
        style={{ margin: 0 }}
      />
    ),
  },
  {
    title: 'Нейтрально',
    dataIndex: 'neutral_pct',
    key: 'neutral_pct',
    width: 150,
    render: (v: string) => (
      <Progress
        percent={Math.round(parseFloat(v))}
        size="small"
        style={{ margin: 0 }}
      />
    ),
  },
  {
    title: 'Негатив',
    dataIndex: 'negative_pct',
    key: 'negative_pct',
    width: 150,
    render: (v: string) => (
      <Progress
        percent={Math.round(parseFloat(v))}
        size="small"
        status="exception"
        style={{ margin: 0 }}
      />
    ),
  },
  {
    title: 'Последний',
    dataIndex: 'last_review_date',
    key: 'last_review_date',
    width: 110,
    render: (v: string | null) => (v ? dayjs(v).format('DD.MM.YYYY') : '—'),
  },
]

// Static column definitions — review_text is scraped/untrusted, rendered as text only (no dangerouslySetInnerHTML)
const historyColumns: TableColumnsType<ReviewHistoryItem> = [
  {
    title: 'Дата',
    dataIndex: 'review_date',
    key: 'review_date',
    width: 100,
    render: (v: string) => dayjs(v).format('DD.MM.YYYY'),
  },
  { title: 'Платформа', dataIndex: 'platform_name', key: 'platform_name', width: 130 },
  {
    title: 'Рейтинг',
    dataIndex: 'rating',
    key: 'rating',
    width: 140,
    render: (v: number) => (
      <Rate
        disabled
        value={v}
        style={{ fontSize: 12 }}
        aria-label={`Рейтинг: ${v} из 5`}
      />
    ),
  },
  {
    title: 'Тональность',
    dataIndex: 'sentiment',
    key: 'sentiment',
    width: 150,
    render: (v: 'positive' | 'neutral' | 'negative' | null) => <SentimentTag sentiment={v} />,
  },
  {
    title: 'Текст отзыва',
    dataIndex: 'review_text',
    key: 'review_text',
    ellipsis: { showTitle: false },
    render: (v: string) => (
      <span title={v}>
        {v.length > 200 ? `${v.slice(0, 200)}…` : v}
      </span>
    ),
  },
]

const PAGE_SIZE = 100

export default function ReviewsPage() {
  const orgId = useAuthStore((s) => s.user?.org_id)

  const [skuId, setSkuId] = useState<string | undefined>()
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(
    () => [dayjs().subtract(29, 'day'), dayjs()]
  )
  const [sentimentFilter, setSentimentFilter] = useState<'positive' | 'neutral' | 'negative' | undefined>()
  const [reviewPage, setReviewPage] = useState(1)

  const dateFrom = dateRange[0].format('YYYY-MM-DD')
  const dateTo = dateRange[1].format('YYYY-MM-DD')

  const summaryQuery = useQuery({
    queryKey: ['reviews-summary', orgId, skuId, dateFrom, dateTo],
    queryFn: () => {
      if (!skuId) throw new Error('skuId required')
      return reviewsApi.summary(skuId, dateFrom, dateTo)
    },
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const statsQuery = useQuery({
    queryKey: ['reviews-stats', orgId, skuId, dateFrom, dateTo],
    queryFn: () => {
      if (!skuId) throw new Error('skuId required')
      return reviewsApi.stats(skuId, dateFrom, dateTo)
    },
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const historyQuery = useQuery({
    queryKey: ['reviews-history', orgId, skuId, sentimentFilter, dateFrom, dateTo, reviewPage],
    queryFn: () => {
      if (!skuId) throw new Error('skuId required')
      return reviewsApi.history(skuId, {
        sentiment: sentimentFilter,
        dateFrom,
        dateTo,
        limit: PAGE_SIZE,
        offset: (reviewPage - 1) * PAGE_SIZE,
      })
    },
    enabled: !!skuId,
    staleTime: 5 * 60 * 1000,
  })

  const stats = statsQuery.data

  const sentimentPieOption = useMemo(() => buildSentimentPie(stats), [stats])
  const trendChartOption = useMemo(() => buildTrendChart(stats), [stats])

  const handleSkuChange = useMemo(
    () => (v: string | undefined) => {
      setSkuId(v)
      setSentimentFilter(undefined)
      setReviewPage(1)
    },
    [],
  )

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>Отзывы и тональность</Title>

      <Row gutter={12} style={{ marginBottom: 24 }} align="middle">
        <Col>
          <SKUSelector value={skuId} onChange={handleSkuChange} />
        </Col>
        <Col>
          <RangePicker
            value={dateRange}
            onChange={(v) => {
              if (v) {
                setDateRange(v as [Dayjs, Dayjs])
                setReviewPage(1)
              }
            }}
            format="DD.MM.YYYY"
            aria-label="Период"
            allowClear={false}
          />
        </Col>
      </Row>

      {!skuId ? (
        <Empty description="Выберите SKU для просмотра отзывов и тональности" style={{ marginTop: 60 }} />
      ) : (
        <>
          {/* Overview row: pie + stats */}
          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={12}>
              <Card title="Распределение тональности" size="small">
                {stats?.sentiment_share ? (
                  <ReactECharts
                    option={sentimentPieOption}
                    style={{ height: 260 }}
                    notMerge={false}
                    lazyUpdate
                  />
                ) : statsQuery.isLoading ? (
                  <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    Загрузка...
                  </div>
                ) : (
                  <Empty description="Данные тональности недоступны" style={{ paddingTop: 60 }} />
                )}
              </Card>
            </Col>
            <Col span={12}>
              <Card title="Общая статистика" size="small" style={{ height: '100%' }}>
                {statsQuery.isError ? (
                  <Alert
                    type="error"
                    message="Ошибка загрузки статистики"
                    action={<Button size="small" onClick={() => statsQuery.refetch()}>Повторить</Button>}
                  />
                ) : (
                  <Row gutter={16}>
                    <Col span={12}>
                      <Statistic
                        title="Всего отзывов"
                        value={stats?.review_count ?? '—'}
                        loading={statsQuery.isLoading}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title="Средний рейтинг"
                        value={stats?.avg_rating ? parseFloat(stats.avg_rating).toFixed(1) : '—'}
                        prefix={<StarFilled style={{ color: '#faad14' }} />}
                        loading={statsQuery.isLoading}
                      />
                    </Col>
                  </Row>
                )}
              </Card>
            </Col>
          </Row>

          {/* Weekly trend */}
          {stats?.weekly_trend?.length ? (
            <>
              <Title level={4}>Недельный тренд (позитивные отзывы %)</Title>
              <ReactECharts
                option={trendChartOption}
                style={{ height: 220, marginBottom: 24 }}
                notMerge={false}
                lazyUpdate
              />
            </>
          ) : null}

          {/* Summary by platform */}
          <Title level={4}>По платформам</Title>
          {summaryQuery.isError ? (
            <Alert
              type="error"
              message="Ошибка загрузки данных по платформам"
              action={<Button size="small" onClick={() => summaryQuery.refetch()}>Повторить</Button>}
              style={{ marginBottom: 16 }}
            />
          ) : (
            <Table
              dataSource={summaryQuery.data?.items ?? []}
              columns={summaryColumns}
              rowKey="platform_id"
              loading={summaryQuery.isLoading}
              pagination={false}
              size="small"
              style={{ marginBottom: 24 }}
            />
          )}

          {/* Individual reviews */}
          <Title level={4}>Отзывы</Title>
          <Space style={{ marginBottom: 12 }}>
            <Select
              placeholder="Все тональности"
              allowClear
              style={{ width: 180 }}
              value={sentimentFilter}
              onChange={(v) => { setSentimentFilter(v); setReviewPage(1) }}
              options={[
                { value: 'positive', label: 'Позитивные' },
                { value: 'neutral', label: 'Нейтральные' },
                { value: 'negative', label: 'Негативные' },
              ]}
              aria-label="Фильтр по тональности"
            />
          </Space>
          {historyQuery.isError ? (
            <Alert
              type="error"
              message="Ошибка загрузки отзывов"
              action={<Button size="small" onClick={() => historyQuery.refetch()}>Повторить</Button>}
              style={{ marginBottom: 16 }}
            />
          ) : (
            <Table
              dataSource={historyQuery.data?.items ?? []}
              columns={historyColumns}
              rowKey="id"
              loading={historyQuery.isLoading}
              pagination={{
                current: reviewPage,
                pageSize: PAGE_SIZE,
                total: historyQuery.data?.total ?? 0,
                onChange: (p) => setReviewPage(p),
                showTotal: (total) => `Всего ${total} отзывов`,
              }}
              size="small"
              locale={{ emptyText: 'Нет отзывов за выбранный период' }}
            />
          )}
        </>
      )}
    </div>
  )
}
