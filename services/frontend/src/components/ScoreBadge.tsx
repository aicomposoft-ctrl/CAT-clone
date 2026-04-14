import { Tag } from 'antd'

interface Props {
  score: number | null | undefined
}

function getStyle(score: number): { color: string; label: string } {
  if (score >= 80) return { color: 'success', label: 'green' }
  if (score >= 50) return { color: 'warning', label: 'yellow' }
  return { color: 'error', label: 'red' }
}

export const ScoreBadge: React.FC<Props> = ({ score }) => {
  if (score === null || score === undefined) {
    return <span style={{ color: '#8c8c8c' }}>—</span>
  }
  const { color } = getStyle(score)
  return (
    <Tag color={color} aria-label={`Content score: ${score.toFixed(1)}%`}>
      {score.toFixed(1)}%
    </Tag>
  )
}

export function getScoreRowStyle(score: number | null | undefined): React.CSSProperties {
  if (score === null || score === undefined) return {}
  if (score >= 80) return { backgroundColor: '#f6ffed' }
  if (score >= 50) return { backgroundColor: '#fffbe6' }
  return { backgroundColor: '#fff2f0' }
}
