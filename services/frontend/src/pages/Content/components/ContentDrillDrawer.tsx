import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Drawer, Skeleton, Descriptions, Progress, Image, Typography, Tag } from 'antd'
import type EChartsReact from 'echarts-for-react'
import ReactECharts from 'echarts-for-react'
import { contentApi } from '../../../api/content'
import { referenceStorageKeyToImageSrc } from '../../../api/catalog'
import { ScoreBadge } from '../../../components/ScoreBadge'

const { Text } = Typography

interface Props {
  skuPlatformId: string
  open: boolean
  onClose: () => void
}

/**
 * Render a diff between two text strings as plain React spans.
 * Uses simple word-level diff — never uses dangerouslySetInnerHTML.
 */
function renderDiff(reference: string | null, collected: string | null): React.ReactNode {
  if (!reference && !collected) return <Text type="secondary">— нет данных —</Text>
  if (!reference) return <Text>{collected}</Text>
  if (!collected) return <Text type="secondary">{reference} (не собрано)</Text>

  const refWords = reference.split(/\s+/)
  const colWords = collected.split(/\s+/)
  const refWordSet = new Set(refWords)

  return (
    <span style={{ lineHeight: 1.8 }}>
      {colWords.map((word, i) => {
        const inRef = refWordSet.has(word)
        return (
          <span
            key={i}
            style={
              !inRef
                ? { background: '#fff2f0', color: '#ff4d4f', borderRadius: 2, padding: '0 2px' }
                : {}
            }
          >
            {word}{' '}
          </span>
        )
      })}
    </span>
  )
}

export const ContentDrillDrawer: React.FC<Props> = ({ skuPlatformId, open, onClose }) => {
  const chartRef = useRef<EChartsReact>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['content-drilldown', skuPlatformId],
    queryFn: () => contentApi.drilldown(skuPlatformId),
    enabled: open && !!skuPlatformId,
    staleTime: 5 * 60 * 1000,
  })

  // ECharts resize fix: call resize after drawer animation completes
  const handleAfterOpenChange = (visible: boolean) => {
    if (visible) {
      setTimeout(() => {
        chartRef.current?.getEchartsInstance()?.resize()
      }, 100)
    }
  }

  const chartOption = {
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: data?.history.map((h) => h.scored_at) ?? [],
    },
    yAxis: { type: 'value', min: 0, max: 100, name: '%' },
    series: [
      {
        name: 'Content Total',
        type: 'line',
        data: data?.history.map((h) => h.content_total) ?? [],
        smooth: true,
        markLine: {
          data: [
            { yAxis: 80, lineStyle: { color: '#52c41a' } },
            { yAxis: 50, lineStyle: { color: '#faad14' } },
          ],
        },
      },
    ],
  }

  return (
    <Drawer
      title={data ? `${data.sku_name} — ${data.platform_name}` : 'Загрузка...'}
      open={open}
      onClose={onClose}
      width={640}
      afterOpenChange={handleAfterOpenChange}
    >
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : data ? (
        <div>
          {/* Score breakdown */}
          <Descriptions size="small" bordered column={1} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Content Total">
              <ScoreBadge score={data.content_total !== null ? Number(data.content_total) : null} />
            </Descriptions.Item>
            <Descriptions.Item label="Изображение">
              <Progress
                percent={Number(data.image_score ?? 0)}
                size="small"
                status={Number(data.image_score ?? 0) >= 80 ? 'success' : 'exception'}
              />
            </Descriptions.Item>
            <Descriptions.Item label="Описание">
              <Progress
                percent={Number(data.description_score ?? 0)}
                size="small"
                status={Number(data.description_score ?? 0) >= 80 ? 'success' : 'exception'}
              />
            </Descriptions.Item>
            <Descriptions.Item label="Состав">
              <Progress
                percent={Number(data.composition_score ?? 0)}
                size="small"
                status={Number(data.composition_score ?? 0) >= 80 ? 'success' : 'exception'}
              />
            </Descriptions.Item>
          </Descriptions>

          {/* Image comparison */}
          <Typography.Title level={5}>Изображение</Typography.Title>
          <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <Tag color="blue">Эталон</Tag>
              {data.reference_image_url ? (
                <Image
                  src={referenceStorageKeyToImageSrc(data.reference_image_url) ?? ''}
                  width="100%"
                  style={{ marginTop: 4 }}
                />
              ) : (
                <Text type="secondary">Эталон не загружен</Text>
              )}
            </div>
            <div style={{ flex: 1 }}>
              <Tag color="default">Собранное</Tag>
              {data.collected_image_url ? (
                <Image src={data.collected_image_url} width="100%" style={{ marginTop: 4 }} />
              ) : (
                <Text type="secondary">Не собрано</Text>
              )}
            </div>
          </div>

          {/* Description diff */}
          <Typography.Title level={5}>Описание (diff)</Typography.Title>
          <div
            style={{
              background: '#fafafa',
              padding: 12,
              borderRadius: 4,
              marginBottom: 16,
              fontSize: 13,
            }}
          >
            {renderDiff(data.reference_description, data.collected_description)}
          </div>

          {/* Trend chart */}
          <Typography.Title level={5}>Тренд (30 дней)</Typography.Title>
          <ReactECharts
            ref={chartRef}
            option={chartOption}
            style={{ height: 200 }}
            notMerge
          />

          {/* Platform link */}
          {data.platform_url && (
            <div style={{ marginTop: 16 }}>
              <a href={data.platform_url} target="_blank" rel="noreferrer">
                Открыть на маркетплейсе ↗
              </a>
            </div>
          )}
        </div>
      ) : null}
    </Drawer>
  )
}
