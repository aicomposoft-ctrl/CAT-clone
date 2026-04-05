import { Typography, Tabs } from 'antd'
import AlertEventTab from './components/AlertEventTab'
import AlertConfigTab from './components/AlertConfigTab'

const { Title } = Typography

export default function AlertsPage() {
  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        Алерты
      </Title>
      <Tabs
        defaultActiveKey="events"
        items={[
          {
            key: 'events',
            label: 'События',
            children: <AlertEventTab />,
          },
          {
            key: 'configs',
            label: 'Конфигурации',
            children: <AlertConfigTab />,
          },
        ]}
      />
    </div>
  )
}
