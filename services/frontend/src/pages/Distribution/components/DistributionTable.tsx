import { DeleteOutlined } from '@ant-design/icons'
import { Popconfirm, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { DistributionPlanRow, DistributionTableProps } from '../types'

const PAGE_SIZE = 50

export function DistributionTable({
  data,
  total,
  page,
  loading,
  canDelete,
  onDelete,
  onPageChange,
}: DistributionTableProps) {
  const columns: ColumnsType<DistributionPlanRow> = [
    {
      title: 'SKU Barcode',
      dataIndex: 'sku_barcode',
      width: 160,
      render: (v: string | null) => v ?? <Typography.Text type="secondary">—</Typography.Text>,
    },
    { title: 'Platform', dataIndex: 'platform_name', width: 140 },
    { title: 'Group', dataIndex: 'group_name', width: 180 },
    { title: 'Plan Qty', dataIndex: 'plan_tt_count', width: 100, align: 'right' },
    { title: 'Week', dataIndex: 'week_number', width: 70, align: 'center' },
    { title: 'Year', dataIndex: 'year', width: 70, align: 'center' },
  ]

  if (canDelete) {
    columns.push({
      title: '',
      key: 'actions',
      width: 60,
      render: (_: unknown, row: DistributionPlanRow) => (
        <Popconfirm
          title="Delete this plan row?"
          okText="Delete"
          okButtonProps={{ danger: true }}
          onConfirm={() => onDelete(row.id)}
        >
          <DeleteOutlined style={{ cursor: 'pointer', color: '#ff4d4f' }} />
        </Popconfirm>
      ),
    })
  }

  return (
    <Table<DistributionPlanRow>
      rowKey="id"
      dataSource={data}
      columns={columns}
      loading={loading}
      pagination={{
        current: page,
        total,
        pageSize: PAGE_SIZE,
        onChange: onPageChange,
        showTotal: (t) => `${t} rows`,
        showSizeChanger: false,
      }}
      locale={{
        emptyText: (
          <Typography.Text type="secondary">
            No plans found. Upload a CSV to get started.
          </Typography.Text>
        ),
      }}
      scroll={{ x: 780 }}
    />
  )
}
