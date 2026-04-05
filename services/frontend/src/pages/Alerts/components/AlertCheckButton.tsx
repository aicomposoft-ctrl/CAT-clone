import { Button } from 'antd'
import { PlayCircleOutlined } from '@ant-design/icons'
import { useAlertCheck } from '../hooks/useAlertCheck'

export default function AlertCheckButton() {
  const { run, isLoading, isCooling, remaining } = useAlertCheck()

  return (
    <Button
      icon={<PlayCircleOutlined />}
      onClick={() => run()}
      loading={isLoading}
      disabled={isCooling}
      title={isCooling ? `Доступно через ${remaining}с` : 'Запустить проверку алертов'}
    >
      {isCooling ? `Проверка (${remaining}с)` : 'Запустить проверку'}
    </Button>
  )
}
