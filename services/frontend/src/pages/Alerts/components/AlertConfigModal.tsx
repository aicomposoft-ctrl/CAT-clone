import { useEffect, useRef, useState } from 'react'
import {
  Modal, Form, Select, Slider, InputNumber, Switch, Button, Space, Row, Col,
} from 'antd'
import { useQuery } from '@tanstack/react-query'
import { skusApi, platformsApi } from '../../../api/catalog'
import type { AlertConfig, AlertConfigCreateRequest } from '../../../api/alerts'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  mode: 'create' | 'edit'
  config?: AlertConfig
  onSubmit: (data: AlertConfigCreateRequest) => void
  onCancel: () => void
  isSubmitting: boolean
}

// ── Email regex ───────────────────────────────────────────────────────────────

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

// ── Component ─────────────────────────────────────────────────────────────────

export default function AlertConfigModal({ mode, config, onSubmit, onCancel, isSubmitting }: Props) {
  const [form] = Form.useForm()
  const isEdit = mode === 'edit'
  const title = isEdit ? 'Редактировать конфигурацию' : 'Новая конфигурация'

  // Track alert_type locally to show/hide threshold
  const [alertType, setAlertType] = useState<'content_drop' | 'oos'>(
    config?.alert_type ?? 'content_drop',
  )

  // Watch threshold field for Slider ↔ InputNumber sync
  const threshold = Form.useWatch('threshold', form)

  // ── SKU search with manual debounce (300ms) ──────────────────────────────
  const [skuSearch, setSkuSearch] = useState('')
  const [debouncedSkuSearch, setDebouncedSkuSearch] = useState('')
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleSkuSearch = (value: string) => {
    setSkuSearch(value)
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      setDebouncedSkuSearch(value)
    }, 300)
  }

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
  }, [])

  // ── Data fetching ────────────────────────────────────────────────────────
  const { data: skusData } = useQuery({
    queryKey: ['skus', { limit: 50, search: debouncedSkuSearch }],
    queryFn: () => skusApi.list({ limit: 50 }),
    staleTime: 30_000,
  })
  const skus = skusData?.items ?? []

  const { data: platforms = [] } = useQuery({
    queryKey: ['platforms'],
    queryFn: platformsApi.list,
    staleTime: 5 * 60_000,
  })

  // ── Pre-fill form in edit mode ───────────────────────────────────────────
  useEffect(() => {
    if (isEdit && config) {
      form.setFieldsValue({
        alert_type: config.alert_type,
        sku_id: config.sku_id ?? undefined,
        platform_id: config.platform_id ?? undefined,
        threshold: config.threshold ?? undefined,
        email_recipients: config.email_recipients,
        is_active: config.is_active,
      })
      setAlertType(config.alert_type)
    }
  }, [isEdit, config, form])

  // ── Handlers ─────────────────────────────────────────────────────────────

  const handleAlertTypeChange = (value: 'content_drop' | 'oos') => {
    setAlertType(value)
    if (value === 'oos') {
      form.setFieldValue('threshold', undefined)
    }
  }

  const handleFinish = (values: {
    alert_type: 'content_drop' | 'oos'
    sku_id?: string
    platform_id?: string
    threshold?: number
    email_recipients: string[]
    is_active?: boolean
  }) => {
    const payload: AlertConfigCreateRequest = {
      alert_type: values.alert_type,
      sku_id: values.sku_id ?? null,
      platform_id: values.platform_id ?? null,
      email_recipients: values.email_recipients,
      is_active: values.is_active ?? true,
    }
    if (alertType === 'content_drop') {
      payload.threshold = values.threshold
    }
    onSubmit(payload)
  }

  const validateEmails = (_: unknown, emails: string[]) => {
    if (!emails || emails.length === 0) {
      return Promise.reject(new Error('Укажите хотя бы один email'))
    }
    if (emails.length > 20) {
      return Promise.reject(new Error('Максимум 20 адресов'))
    }
    for (const email of emails) {
      if (!EMAIL_RE.test(email)) {
        return Promise.reject(new Error(`Неверный email: ${email}`))
      }
    }
    return Promise.resolve()
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const skuOptions = skus
    .filter((s) =>
      !debouncedSkuSearch ||
      s.name.toLowerCase().includes(debouncedSkuSearch.toLowerCase()) ||
      (s.article ?? '').toLowerCase().includes(debouncedSkuSearch.toLowerCase()),
    )
    .map((s) => ({ value: s.id, label: `${s.name}${s.article ? ` (${s.article})` : ''}` }))

  const platformOptions = platforms.map((p) => ({ value: p.id, label: p.name }))

  return (
    <Modal
      title={title}
      open
      onCancel={onCancel}
      footer={null}
      width={520}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleFinish}
        style={{ marginTop: 8 }}
      >
        {/* alert_type */}
        <Form.Item
          name="alert_type"
          label="Тип алерта"
          initialValue="content_drop"
          rules={[{ required: true, message: 'Выберите тип алерта' }]}
        >
          <Select
            disabled={isEdit}
            onChange={handleAlertTypeChange}
            options={[
              { value: 'content_drop', label: 'Падение контента' },
              { value: 'oos', label: 'Нет в наличии' },
            ]}
          />
        </Form.Item>

        {/* sku_id */}
        <Form.Item name="sku_id" label="SKU">
          <Select
            showSearch
            allowClear
            disabled={isEdit}
            placeholder="Все SKU"
            filterOption={false}
            onSearch={handleSkuSearch}
            searchValue={skuSearch}
            options={skuOptions}
            notFoundContent={debouncedSkuSearch.length > 0 ? 'Не найдено' : 'Начните вводить название'}
          />
        </Form.Item>

        {/* platform_id */}
        <Form.Item name="platform_id" label="Платформа">
          <Select
            allowClear
            disabled={isEdit}
            placeholder="Все платформы"
            options={platformOptions}
          />
        </Form.Item>

        {/* threshold — visible only for content_drop */}
        {alertType === 'content_drop' && (
          <Form.Item
            name="threshold"
            label="Порог контент-скора (%)"
            rules={[
              { required: true, message: 'Укажите порог' },
              { type: 'number', min: 0, max: 100, message: 'Значение от 0 до 100' },
            ]}
          >
            <Row gutter={12} align="middle">
              <Col flex={1}>
                <Slider
                  min={0}
                  max={100}
                  value={typeof threshold === 'number' ? threshold : 0}
                  onChange={(v) => form.setFieldValue('threshold', v)}
                />
              </Col>
              <Col>
                <InputNumber
                  min={0}
                  max={100}
                  style={{ width: 64 }}
                  value={typeof threshold === 'number' ? threshold : undefined}
                  onChange={(v) => form.setFieldValue('threshold', v)}
                />
              </Col>
            </Row>
          </Form.Item>
        )}

        {/* email_recipients */}
        <Form.Item
          name="email_recipients"
          label="Email-получатели"
          rules={[{ validator: validateEmails }]}
        >
          <Select
            mode="tags"
            tokenSeparators={[',']}
            placeholder="email@example.ru"
            open={false}
            suffixIcon={null}
          />
        </Form.Item>

        {/* is_active */}
        <Form.Item
          name="is_active"
          label="Статус"
          valuePropName="checked"
          initialValue
        >
          <Switch checkedChildren="Активен" unCheckedChildren="Отключён" />
        </Form.Item>

        {/* Footer buttons */}
        <Form.Item style={{ marginBottom: 0, marginTop: 24 }}>
          <Space>
            <Button onClick={onCancel}>Отмена</Button>
            <Button type="primary" htmlType="submit" loading={isSubmitting}>
              {isEdit ? 'Сохранить' : 'Создать'}
            </Button>
          </Space>
        </Form.Item>
      </Form>
    </Modal>
  )
}
