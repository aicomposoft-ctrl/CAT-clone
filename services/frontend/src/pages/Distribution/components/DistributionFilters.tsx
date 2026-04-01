import { Button, InputNumber, Select, Space } from 'antd'
import type { DistributionFiltersProps } from '../types'

const currentYear = new Date().getFullYear()
const YEAR_OPTIONS = [currentYear - 1, currentYear, currentYear + 1].map((y) => ({
  value: y,
  label: String(y),
}))

export function DistributionFilters({ value, onChange }: DistributionFiltersProps) {
  function handleReset() {
    onChange({ page: 1 })
  }

  return (
    <Space wrap style={{ marginBottom: 16 }}>
      <InputNumber
        placeholder="Week"
        min={1}
        max={53}
        value={value.week_number}
        onChange={(v) => onChange({ ...value, week_number: v ?? undefined, page: 1 })}
        style={{ width: 100 }}
      />
      <Select
        placeholder="Year"
        options={YEAR_OPTIONS}
        value={value.year}
        onChange={(v) => onChange({ ...value, year: v ?? undefined, page: 1 })}
        allowClear
        style={{ width: 100 }}
      />
      <Button onClick={handleReset}>Reset</Button>
    </Space>
  )
}
