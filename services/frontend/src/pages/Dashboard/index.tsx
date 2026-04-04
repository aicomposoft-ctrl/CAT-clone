import { useQuery } from '@tanstack/react-query'
import { Row, Col, Card, Statistic, Table, Tag, Typography, Skeleton, Alert, Button } from 'antd'
import {
  FileTextOutlined,
  BellOutlined,
  ShopOutlined,
  AppstoreOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { dashboardApi, DashboardRedZoneItem, DashboardAlert } from '../../api/dashboard'
import { ScoreBadge } from '../../components/ScoreBadge'

const { Title } = Typography

export default function DashboardPage() {
  const navigate = useNavigate()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: dashboardApi.getSummary,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })

  if (isError) {
    return (
      <Alert
        type="error"
        message="Ошибка загрузки данных"
        description="Не удалось загрузить дашборд. Попробуйте ещё раз."
        action={<Button onClick={() => refetch()}>Повторить</Button>}
      />
    )
  }

  const redZoneColumns = [
    { title: 'SKU', dataIndex: 'sku_name', key: 'sku_name', ellipsis: true },
    { title: 'Артикул', dataIndex: 'article', key: 'article', width: 100 },
    { title: 'Платформа', dataIndex: 'platform_name', key: 'platform_name', width: 140 },
    {
      title: 'Score',
      dataIndex: 'content_total',
      key: 'content_total',
      width: 90,
      render: (v: number | null) => <ScoreBadge score={v} />,
    },
  ]

  const alertTypeLabels: Record<string, { label: string; color: string }> = {
    content_drop: { label: 'Контент', color: 'orange' },
    oos: { label: 'Нет в наличии', color: 'red' },
    price_change: { label: 'Цена', color: 'blue' },
    competitor_promo: { label: 'Акция конкурента', color: 'purple' },
  }

  const alertColumns = [
    {
      title: 'Тип',
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 120,
      render: (v: string) => {
        const meta = alertTypeLabels[v] ?? { label: v, color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    { title: 'SKU', dataIndex: 'sku_name', key: 'sku_name', ellipsis: true },
    { title: 'Платформа', dataIndex: 'platform_name', key: 'platform_name', width: 140 },
    {
      title: 'Время',
      dataIndex: 'triggered_at',
      key: 'triggered_at',
      width: 150,
      render: (v: string) => new Date(v).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        Дашборд
      </Title>

      {/* KPI Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Col span={6} key={i}>
              <Card>
                <Skeleton active paragraph={false} />
              </Card>
            </Col>
          ))
        ) : (
          <>
            <Col span={6}>
              <Card>
                <Statistic
                  title="Средний content score"
                  value={data?.avg_content_score ?? 0}
                  precision={1}
                  suffix="%"
                  prefix={<FileTextOutlined />}
                  valueStyle={{
                    color:
                      (data?.avg_content_score ?? 0) >= 80
                        ? '#52c41a'
                        : (data?.avg_content_score ?? 0) >= 50
                        ? '#faad14'
                        : '#ff4d4f',
                  }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="Активных алертов"
                  value={data?.active_alerts_count ?? 0}
                  prefix={<BellOutlined />}
                  valueStyle={{ color: (data?.active_alerts_count ?? 0) > 0 ? '#ff4d4f' : '#52c41a' }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="Покрытие дистрибуции"
                  value={data?.distribution_coverage_pct ?? 0}
                  precision={1}
                  suffix="%"
                  prefix={<ShopOutlined />}
                  valueStyle={{
                    color: (data?.distribution_coverage_pct ?? 0) >= 90 ? '#52c41a' : '#faad14',
                  }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title="Мониторируется SKU-платформ"
                  value={data?.monitored_sku_count ?? 0}
                  prefix={<AppstoreOutlined />}
                />
              </Card>
            </Col>
          </>
        )}
      </Row>

      <Row gutter={[16, 16]}>
        {/* Red Zone */}
        <Col span={14}>
          <Card
            title="Красная зона (топ-5 по низкому скору)"
            extra={
              <Button type="link" size="small" onClick={() => navigate('/content?score_max=50')}>
                Смотреть все
              </Button>
            }
          >
            {isLoading ? (
              <Skeleton active />
            ) : (data?.red_zone?.length ?? 0) === 0 ? (
              <div style={{ textAlign: 'center', color: '#8c8c8c', padding: '24px 0' }}>
                Нет данных — добавьте SKU для мониторинга
              </div>
            ) : (
              <Table<DashboardRedZoneItem>
                dataSource={data?.red_zone}
                columns={redZoneColumns}
                rowKey="sku_platform_id"
                pagination={false}
                size="small"
              />
            )}
          </Card>
        </Col>

        {/* Recent Alerts */}
        <Col span={10}>
          <Card
            title="Последние алерты"
            extra={
              <Button type="link" size="small" onClick={() => navigate('/alerts')}>
                Все алерты
              </Button>
            }
          >
            {isLoading ? (
              <Skeleton active />
            ) : (data?.recent_alerts?.length ?? 0) === 0 ? (
              <div style={{ textAlign: 'center', color: '#52c41a', padding: '24px 0' }}>
                Нет активных алертов
              </div>
            ) : (
              <Table<DashboardAlert>
                dataSource={data?.recent_alerts}
                columns={alertColumns}
                rowKey="id"
                pagination={false}
                size="small"
                onRow={() => ({
                  onClick: () => navigate('/alerts'),
                  style: { cursor: 'pointer' },
                })}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
