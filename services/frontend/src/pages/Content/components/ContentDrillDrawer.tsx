import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Drawer, Skeleton, Descriptions, Progress, Image, Typography, Tag, Tooltip } from 'antd'
import { InfoCircleOutlined } from '@ant-design/icons'
import type EChartsReact from 'echarts-for-react'
import ReactECharts from 'echarts-for-react'
import { contentApi } from '../../../api/content'
import { referenceStorageKeyToImageSrc, collectedStorageKeyToImageSrc } from '../../../api/catalog'
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
function normalizeWord(w: string): string {
  return w.toLowerCase().replace(/[«».,;:!?—–\-()[\]{}'"/\\]/g, '').trim()
}

/** Remove hyphen line-breaks ("про- дукт" → "продукт") and collapse whitespace */
function preprocessText(text: string): string {
  return text
    .replace(/-\s+/g, '')   // hyphenated line-wrap: merge back
    .replace(/\s+/g, ' ')   // collapse multiple spaces/newlines
    .trim()
}

function renderDiff(reference: string | null, collected: string | null): React.ReactNode {
  if (!reference && !collected) return <Text type="secondary">— нет данных —</Text>
  if (!reference) return <Text>{collected}</Text>
  if (!collected) return <Text type="secondary">{reference} (не собрано)</Text>

  const refWords = preprocessText(reference).split(' ')
  const colWords = preprocessText(collected).split(' ')
  const refWordSet = new Set(refWords.map(normalizeWord))

  return (
    <span style={{ lineHeight: 1.8 }}>
      {colWords.map((word, i) => {
        const inRef = refWordSet.has(normalizeWord(word))
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
          {/* Score breakdown — DB stores scores as 0–1 decimals; UI needs 0–100 */}
          <Descriptions size="small" bordered column={1} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="Content Total">
              <ScoreBadge score={data.content_total} />
            </Descriptions.Item>
            <Descriptions.Item label={
              <span>
                Изображение&nbsp;
                <Tooltip title="Нейросеть CLIP (ViT) кодирует изображение в вектор из 512 чисел, описывающий семантику: форму упаковки, цвета, расположение логотипа и графики. Скор — косинусное сходство между эталоном и собранным фото. Важно: CLIP не читает текст на этикетке как OCR — мелкие текстовые различия на похожих упаковках могут не влиять на скор.">
                  <InfoCircleOutlined style={{ color: '#8c8c8c', cursor: 'help' }} />
                </Tooltip>
              </span>
            }>
              {data.image_score !== null ? (
                <Progress
                  percent={Math.round(Number(data.image_score))}
                  size="small"
                  status={Number(data.image_score) >= 80 ? 'success' : 'exception'}
                />
              ) : <Text type="secondary">Н/Д</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="Описание">
              {data.description_score !== null ? (
                <Progress
                  percent={Math.round(Number(data.description_score))}
                  size="small"
                  status={Number(data.description_score) >= 80 ? 'success' : 'exception'}
                />
              ) : <Text type="secondary">Н/Д</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="Состав">
              {data.composition_score !== null ? (
                <Progress
                  percent={Math.round(Number(data.composition_score))}
                  size="small"
                  status={Number(data.composition_score) >= 80 ? 'success' : 'exception'}
                />
              ) : (
                <Text type="secondary">
                  {data.collected_composition ? 'Не подсчитан' : 'Не публикуется площадкой'}
                </Text>
              )}
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
                <Image
                  src={collectedStorageKeyToImageSrc(data.collected_image_url) ?? ''}
                  width="100%"
                  style={{ marginTop: 4 }}
                />
              ) : (
                <Text type="secondary">Не собрано</Text>
              )}
            </div>
          </div>

          {/* Description diff */}
          <Typography.Title level={5}>Описание (diff)</Typography.Title>
          <div style={{ background: '#fafafa', padding: 12, borderRadius: 4, marginBottom: 16, fontSize: 13 }}>
            {renderDiff(data.reference_description, data.collected_description)}
          </div>

          {/* Composition diff */}
          <Typography.Title level={5}>Состав (diff)</Typography.Title>
          <div style={{ background: '#fafafa', padding: 12, borderRadius: 4, marginBottom: 16, fontSize: 13 }}>
            {renderDiff(data.reference_composition, data.collected_composition)}
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
