import { useState } from 'react'
import { Alert, Button, Modal, Space, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useAlertConfigs } from '../hooks/useAlertConfigs'
import { useAuthStore } from '../../../store/authStore'
import AlertConfigTable from './AlertConfigTable'
import AlertConfigModal from './AlertConfigModal'
import AlertCheckButton from './AlertCheckButton'
import type { AlertConfig, AlertConfigCreateRequest } from '../../../api/alerts'

// ── Modal state type ──────────────────────────────────────────────────────────

type ModalState =
  | { mode: 'closed' }
  | { mode: 'create' }
  | { mode: 'edit'; config: AlertConfig }

// ── Component ─────────────────────────────────────────────────────────────────

export default function AlertConfigTab() {
  const [modalState, setModalState] = useState<ModalState>({ mode: 'closed' })
  const [page, setPage] = useState(1)

  const { query, createMutation, updateMutation, removeMutation } = useAlertConfigs(page)

  const user = useAuthStore((s) => s.user)
  const canManage = user?.role === 'admin' || user?.role === 'manager'
  const canCheck = user?.role === 'admin'

  // ── Modal helpers ────────────────────────────────────────────────────────

  const openCreate = () => setModalState({ mode: 'create' })
  const openEdit = (config: AlertConfig) => setModalState({ mode: 'edit', config })
  const closeModal = () => setModalState({ mode: 'closed' })

  // ── Submit handler ───────────────────────────────────────────────────────

  const handleSubmit = (data: AlertConfigCreateRequest) => {
    if (modalState.mode === 'create') {
      createMutation.mutate(data, {
        onSuccess: () => {
          closeModal()
          message.success('Конфигурация создана')
        },
        onError: (err: unknown) => {
          const status = (err as { response?: { status?: number } })?.response?.status
          if (status === 404) {
            message.error('Конфигурация не найдена — обновите список')
          } else {
            message.error('Ошибка при создании конфигурации')
          }
        },
      })
    } else if (modalState.mode === 'edit') {
      updateMutation.mutate(
        { id: modalState.config.id, data },
        {
          onSuccess: () => {
            closeModal()
            message.success('Изменения сохранены')
          },
          onError: (err: unknown) => {
            const status = (err as { response?: { status?: number } })?.response?.status
            if (status === 404) {
              message.error('Конфигурация не найдена — обновите список')
            } else {
              message.error('Ошибка при сохранении изменений')
            }
          },
        },
      )
    }
  }

  // ── Delete handler ───────────────────────────────────────────────────────

  const handleDelete = (config: AlertConfig) => {
    Modal.confirm({
      title: 'Удалить конфигурацию?',
      content: 'Вы уверены? Все связанные события останутся в истории.',
      okText: 'Удалить',
      okType: 'danger',
      cancelText: 'Отмена',
      onOk: () => {
        removeMutation.mutate(config.id, {
          onSuccess: () => {
            message.success('Конфигурация удалена')
          },
          onError: (err: unknown) => {
            const status = (err as { response?: { status?: number } })?.response?.status
            if (status === 404) {
              message.error('Конфигурация не найдена — обновите список')
            } else {
              message.error('Ошибка при удалении конфигурации')
            }
          },
        })
      },
    })
  }

  // ── Error state ──────────────────────────────────────────────────────────

  if (query.isError) {
    return (
      <Alert
        type="error"
        message="Ошибка загрузки конфигураций"
        action={<Button onClick={() => query.refetch()}>Повторить</Button>}
      />
    )
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        {canManage && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            Добавить
          </Button>
        )}
        {canCheck && <AlertCheckButton />}
      </Space>

      <AlertConfigTable
        data={query.data}
        loading={query.isLoading}
        onEdit={openEdit}
        onDelete={handleDelete}
        canManage={canManage}
        page={page}
        onPageChange={setPage}
        updateMutation={updateMutation}
      />

      {modalState.mode !== 'closed' && (
        <AlertConfigModal
          mode={modalState.mode}
          config={modalState.mode === 'edit' ? modalState.config : undefined}
          onSubmit={handleSubmit}
          onCancel={closeModal}
          isSubmitting={createMutation.isPending || updateMutation.isPending}
        />
      )}
    </div>
  )
}
