import { useState, useEffect } from 'react'
import {
  Tabs, Typography, Button, Table, Tag, Space, Modal, Form, Input, Select,
  Upload, message, Popconfirm, Tooltip, Badge, Drawer, Spin, Image, Divider, Alert,
} from 'antd'
import {
  PlusOutlined, UploadOutlined, DeleteOutlined, LinkOutlined, DisconnectOutlined,
  PictureOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { ColumnsType } from 'antd/es/table'
import { brandsApi, skusApi, platformsApi, skuPlatformsApi, referenceApi } from '../../api/catalog'
import type { Brand, SKU, SKUPlatform, ReferenceTextPatchResponse } from '../../api/catalog'

const { Title } = Typography

// ── Brands Tab ───────────────────────────────────────────────────────────────

function BrandsTab() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const { data: brands = [], isLoading } = useQuery({
    queryKey: ['brands'],
    queryFn: brandsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: ({ name, type }: { name: string; type: 'client' | 'competitor' }) =>
      brandsApi.create(name, type),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['brands'] })
      qc.invalidateQueries({ queryKey: ['skus'] })
      message.success('Бренд создан')
      setOpen(false)
      form.resetFields()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      const detail = e.response?.data?.detail
      message.error(detail === 'BRAND_NAME_DUPLICATE' ? 'Бренд с таким названием уже существует' : 'Ошибка создания')
    },
  })

  const columns: ColumnsType<Brand> = [
    { title: 'Название', dataIndex: 'name', key: 'name' },
    {
      title: 'Тип', dataIndex: 'type', key: 'type', width: 130,
      render: (v: string) => (
        <Tag color={v === 'client' ? 'blue' : 'orange'}>
          {v === 'client' ? 'Свой' : 'Конкурент'}
        </Tag>
      ),
    },
    {
      title: 'Создан', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => new Date(v).toLocaleDateString('ru-RU'),
    },
  ]

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          Добавить бренд
        </Button>
      </div>
      <Table rowKey="id" dataSource={brands} columns={columns} loading={isLoading} size="small" />

      <Modal
        title="Новый бренд"
        open={open}
        onCancel={() => { setOpen(false); form.resetFields() }}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        okText="Создать"
        cancelText="Отмена"
      >
        <Form form={form} layout="vertical" onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="name" label="Название" rules={[{ required: true, message: 'Введите название' }]}>
            <Input placeholder="Например: Valio" />
          </Form.Item>
          <Form.Item name="type" label="Тип" initialValue="client" rules={[{ required: true }]}>
            <Select options={[{ value: 'client', label: 'Свой бренд' }, { value: 'competitor', label: 'Конкурент' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

// ── Platform linker drawer ────────────────────────────────────────────────────

function PlatformDrawer({ sku, onClose }: { sku: SKU | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [linkForm] = Form.useForm()
  const [linkOpen, setLinkOpen] = useState(false)

  const { data: platforms = [] } = useQuery({
    queryKey: ['platforms'],
    queryFn: platformsApi.list,
  })

  const { data: linked = [], isLoading } = useQuery({
    queryKey: ['sku-platforms', sku?.id],
    queryFn: () => skuPlatformsApi.listForSku(sku!.id),
    enabled: !!sku,
  })

  const linkMutation = useMutation({
    mutationFn: (v: { platform_id: string; external_id?: string; url?: string }) =>
      skuPlatformsApi.link({ sku_id: sku!.id, ...v }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sku-platforms', sku?.id] })
      message.success('Платформа привязана')
      setLinkOpen(false)
      linkForm.resetFields()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      const detail = e.response?.data?.detail
      message.error(detail === 'SKU_PLATFORM_DUPLICATE' ? 'Уже привязана' : 'Ошибка привязки')
    },
  })

  const unlinkMutation = useMutation({
    mutationFn: (id: string) => skuPlatformsApi.unlink(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sku-platforms', sku?.id] })
      message.success('Отвязано')
    },
  })

  const linkedPlatformIds = new Set(linked.map((l) => l.platform_id))
  const availablePlatforms = platforms.filter((p) => p.is_active && !linkedPlatformIds.has(p.id))

  const platformName = (id: string) => platforms.find((p) => p.id === id)?.name ?? id

  const cols: ColumnsType<SKUPlatform> = [
    { title: 'Платформа', dataIndex: 'platform_id', render: platformName },
    { title: 'External ID', dataIndex: 'external_id', render: (v) => v ?? '—' },
    {
      title: '', key: 'actions', width: 50,
      render: (_, row) => (
        <Popconfirm title="Отвязать платформу?" onConfirm={() => unlinkMutation.mutate(row.id)} okText="Да" cancelText="Нет">
          <Tooltip title="Отвязать">
            <Button size="small" icon={<DisconnectOutlined />} danger type="text" loading={unlinkMutation.isPending} />
          </Tooltip>
        </Popconfirm>
      ),
    },
  ]

  return (
    <Drawer
      title={sku ? `Платформы: ${sku.name}` : ''}
      open={!!sku}
      onClose={onClose}
      width={480}
      extra={
        availablePlatforms.length > 0 && (
          <Button size="small" type="primary" icon={<LinkOutlined />} onClick={() => setLinkOpen(true)}>
            Привязать
          </Button>
        )
      }
    >
      {isLoading ? (
        <Spin />
      ) : (
        <Table rowKey="id" dataSource={linked} columns={cols} size="small" pagination={false}
          locale={{ emptyText: 'Нет привязанных платформ' }} />
      )}

      <Modal
        title="Привязать платформу"
        open={linkOpen}
        onCancel={() => { setLinkOpen(false); linkForm.resetFields() }}
        onOk={() => linkForm.submit()}
        confirmLoading={linkMutation.isPending}
        okText="Привязать"
        cancelText="Отмена"
      >
        <Form form={linkForm} layout="vertical" onFinish={(v) => linkMutation.mutate(v)}>
          <Form.Item name="platform_id" label="Платформа" rules={[{ required: true }]}>
            <Select
              options={availablePlatforms.map((p) => ({ value: p.id, label: p.name }))}
              placeholder="Выберите платформу"
            />
          </Form.Item>
          <Form.Item name="external_id" label="External ID (артикул на платформе)">
            <Input placeholder="Необязательно" />
          </Form.Item>
          <Form.Item name="url" label="URL карточки">
            <Input placeholder="https://..." />
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  )
}

// ── Reference Drawer ─────────────────────────────────────────────────────────

function ReferenceDrawer({ sku, onClose }: { sku: SKU | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const skuId = sku?.id

  const {
    data: skuDetail,
    isLoading: skuDetailLoading,
    isError: skuDetailError,
  } = useQuery({
    queryKey: ['sku-detail', skuId],
    queryFn: () => skusApi.get(skuId!),
    enabled: !!skuId,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: 'always',
  })

  const canEditReference = !!skuDetail && !skuDetailLoading && !skuDetailError

  useEffect(() => {
    setPreviewUrl(null)
  }, [skuId])

  const { data: imgData, isLoading: imgLoading } = useQuery({
    queryKey: ['reference-image', skuId],
    queryFn: () => referenceApi.getImageUrl(skuId!),
    enabled: !!skuId,
    staleTime: 0,
  })

  useEffect(() => {
    if (imgData?.url) setPreviewUrl(imgData.url)
  }, [skuId, imgData?.url])

  const displayUrl = previewUrl ?? imgData?.url ?? null

  const imgMutation = useMutation({
    mutationFn: (file: File) => referenceApi.uploadImage(skuId!, file),
    onSuccess: (result: { url: string }) => {
      setPreviewUrl(result.url)
      qc.invalidateQueries({ queryKey: ['skus'] })
      qc.invalidateQueries({ queryKey: ['sku-detail', skuId] })
      qc.invalidateQueries({ queryKey: ['reference-image', skuId] })
      message.success('Фото загружено')
    },
    onError: (err: unknown) => {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })?.response
        ?.status
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(
        status === 503
          ? `Загрузка недоступна (503). Проверьте MinIO и бакет cat-references: ${detail ?? 'S3 error'}`
          : 'Ошибка загрузки фото',
      )
    },
  })

  type TextSaveVars = { reference_description?: string; reference_composition?: string }

  const textMutation = useMutation<ReferenceTextPatchResponse, Error, TextSaveVars>({
    mutationFn: (v) => referenceApi.updateText(skuId!, v),
    onSuccess: (saved) => {
      // Merge PATCH echo into cache. Do not invalidate sku-detail here: a follow-up GET
      // can race or (with an older API bundle) omit fields and overwrite good cache → empty form.
      qc.setQueryData<SKU | undefined>(['sku-detail', skuId], (prev) =>
        prev
          ? {
              ...prev,
              reference_description: saved.reference_description,
              reference_composition: saved.reference_composition,
              updated_at: saved.updated_at ?? prev.updated_at,
            }
          : prev,
      )
      qc.invalidateQueries({ queryKey: ['skus'] })
      message.success('Эталонный текст сохранён')
    },
    onError: () => message.error('Ошибка сохранения'),
  })

  return (
    <Drawer
      title={sku ? `Эталон: ${sku.name}` : ''}
      open={!!sku}
      onClose={onClose}
      width={520}
      destroyOnClose
    >
      <Typography.Title level={5}>Эталонное фото</Typography.Title>
      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        Фото с правильной подачей товара — сравнивается с фото на платформе при оценке контента.
      </Typography.Text>

      {skuDetailError ? (
        <Alert
          type="error"
          showIcon
          message="Не удалось загрузить данные SKU"
          description="Обновите API (нужен GET /skus/{id}) и перезапустите контейнер api. Без этого эталонный текст может сохраняться пустым."
          style={{ marginBottom: 12 }}
        />
      ) : null}

      {(skuDetailLoading || imgLoading) && !displayUrl ? (
        <Spin />
      ) : displayUrl ? (
        <div style={{ marginBottom: 12 }}>
          <Image src={displayUrl} width={200} style={{ borderRadius: 4 }} />
        </div>
      ) : (
        <div style={{ color: '#8c8c8c', marginBottom: 12 }}>Фото не загружено</div>
      )}

      <Upload
        showUploadList={false}
        accept="image/jpeg,image/png,image/webp"
        beforeUpload={(file) => { imgMutation.mutate(file); return false }}
        disabled={!canEditReference}
      >
        <Button
          icon={<UploadOutlined />}
          loading={imgMutation.isPending}
          disabled={!canEditReference}
        >
          {displayUrl ? 'Заменить фото' : 'Загрузить фото'}
        </Button>
      </Upload>

      <Divider />

      <Typography.Title level={5}>Эталонный текст</Typography.Title>
      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        Описание и состав, которые должны быть на карточке товара. Используются для расчёта контент-скора.
      </Typography.Text>

      {skuDetailLoading || !skuDetail ? (
        <Spin />
      ) : (
        <Form
          key={`ref-text-${skuDetail.id}-${skuDetail.updated_at}`}
          layout="vertical"
          initialValues={{
            reference_description: skuDetail.reference_description ?? '',
            reference_composition: skuDetail.reference_composition ?? '',
          }}
          onFinish={(v) => textMutation.mutate(v)}
        >
          <Form.Item name="reference_description" label="Описание">
            <Input.TextArea rows={4} maxLength={2000} showCount placeholder="Полное описание продукта..." />
          </Form.Item>
          <Form.Item name="reference_composition" label="Состав">
            <Input.TextArea rows={3} maxLength={1000} showCount placeholder="Ингредиенты, состав..." />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={textMutation.isPending}
            disabled={!canEditReference}
          >
            Сохранить текст
          </Button>
        </Form>
      )}
    </Drawer>
  )
}

// ── SKUs Tab ──────────────────────────────────────────────────────────────────

function SKUsTab() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editSku, setEditSku] = useState<SKU | null>(null)
  const [platformSku, setPlatformSku] = useState<SKU | null>(null)
  const [referenceSku, setReferenceSku] = useState<SKU | null>(null)
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const [brandFilter, setBrandFilter] = useState<string | undefined>()
  const [includeInactive, setIncludeInactive] = useState(false)

  const { data: brands = [] } = useQuery({ queryKey: ['brands'], queryFn: brandsApi.list })
  const { data, isLoading } = useQuery({
    queryKey: ['skus', brandFilter, includeInactive],
    queryFn: () => skusApi.list({ brand_id: brandFilter, include_inactive: includeInactive, limit: 200 }),
  })
  const skus = data?.items ?? []

  const createMutation = useMutation({
    mutationFn: skusApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skus'] })
      message.success('SKU создан')
      setCreateOpen(false)
      createForm.resetFields()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      const d = e.response?.data?.detail
      message.error(d === 'SKU_ARTICLE_DUPLICATE' ? 'Артикул уже существует' : 'Ошибка создания')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof skusApi.update>[1] }) =>
      skusApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skus'] })
      message.success('SKU обновлён')
      setEditSku(null)
    },
    onError: () => message.error('Ошибка обновления'),
  })

  const deleteMutation = useMutation({
    mutationFn: skusApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skus'] })
      message.success('SKU удалён')
    },
    onError: () => message.error('Ошибка удаления'),
  })

  const bulkMutation = useMutation({
    mutationFn: skusApi.bulkUpload,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['skus'] })
      message.success(`Загружено: ${r.imported}, ошибок: ${r.failed}`)
    },
    onError: () => message.error('Ошибка загрузки файла'),
  })

  const openEdit = (sku: SKU) => {
    setEditSku(sku)
    editForm.setFieldsValue({
      name: sku.name,
      brand_id: sku.brand.id,
      article: sku.article ?? '',
      rpc: sku.rpc ?? '',
      barcode: sku.barcode ?? '',
      category: sku.category ?? '',
      sub_category: sku.sub_category ?? '',
    })
  }

  const brandOptions = brands.map((b) => ({ value: b.id, label: b.name }))

  const columns: ColumnsType<SKU> = [
    { title: 'Название', dataIndex: 'name', key: 'name', ellipsis: true },
    { title: 'Артикул', dataIndex: 'article', key: 'article', width: 110, render: (v) => v ?? '—' },
    {
      title: 'Бренд', key: 'brand', width: 130,
      render: (_, r) => <Tag>{r.brand.name}</Tag>,
    },
    { title: 'Категория', dataIndex: 'category', key: 'category', width: 140, render: (v) => v ?? '—' },
    {
      title: 'Статус', dataIndex: 'is_active', key: 'is_active', width: 90,
      render: (v: boolean) => <Badge status={v ? 'success' : 'default'} text={v ? 'Активен' : 'Архив'} />,
    },
    {
      title: '', key: 'actions', width: 120,
      render: (_, row) => (
        <Space size={4}>
          <Tooltip title="Эталон (фото + текст)">
            <Button size="small" icon={<PictureOutlined />} onClick={() => setReferenceSku(row)} />
          </Tooltip>
          <Tooltip title="Платформы">
            <Button size="small" icon={<LinkOutlined />} onClick={() => setPlatformSku(row)} />
          </Tooltip>
          <Tooltip title="Редактировать">
            <Button size="small" onClick={() => openEdit(row)}>✎</Button>
          </Tooltip>
          <Popconfirm title="Удалить SKU?" onConfirm={() => deleteMutation.mutate(row.id)} okText="Да" cancelText="Нет">
            <Button size="small" icon={<DeleteOutlined />} danger type="text" />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <Select
          allowClear placeholder="Фильтр по бренду"
          style={{ width: 200 }}
          options={brandOptions}
          onChange={setBrandFilter}
        />
        <Select
          value={includeInactive ? 'all' : 'active'}
          style={{ width: 140 }}
          onChange={(v) => setIncludeInactive(v === 'all')}
          options={[{ value: 'active', label: 'Только активные' }, { value: 'all', label: 'Все (включая архив)' }]}
        />
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <Upload
            showUploadList={false}
            accept=".csv,.xlsx,.xls"
            beforeUpload={(file) => { bulkMutation.mutate(file); return false }}
          >
            <Button icon={<UploadOutlined />} loading={bulkMutation.isPending}>Загрузить CSV</Button>
          </Upload>
          <Button
            type="primary" icon={<PlusOutlined />}
            disabled={brands.length === 0}
            onClick={() => setCreateOpen(true)}
          >
            Добавить SKU
          </Button>
        </div>
      </div>

      {brands.length === 0 && (
        <div style={{ marginBottom: 12, color: '#faad14' }}>
          ⚠ Сначала создайте бренд на вкладке «Бренды»
        </div>
      )}

      <Table rowKey="id" dataSource={skus} columns={columns} loading={isLoading} size="small"
        pagination={{ pageSize: 50, showSizeChanger: false }} />

      {/* Create modal */}
      <Modal
        title="Новый SKU"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); createForm.resetFields() }}
        onOk={() => createForm.submit()}
        confirmLoading={createMutation.isPending}
        okText="Создать"
        cancelText="Отмена"
        width={560}
      >
        <Form form={createForm} layout="vertical" onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="brand_id" label="Бренд" rules={[{ required: true }]}>
            <Select options={brandOptions} placeholder="Выберите бренд" />
          </Form.Item>
          <Form.Item name="name" label="Название" rules={[{ required: true, message: 'Введите название' }]}>
            <Input placeholder="Молоко Viola 3,5% 1л" />
          </Form.Item>
          <Form.Item name="article" label="Артикул (внутренний)">
            <Input placeholder="VIO-001" />
          </Form.Item>
          <Form.Item name="rpc" label="RPC">
            <Input />
          </Form.Item>
          <Form.Item name="barcode" label="Штрихкод">
            <Input placeholder="EAN/UPC" />
          </Form.Item>
          <Form.Item name="category" label="Категория">
            <Input placeholder="Молочные продукты" />
          </Form.Item>
          <Form.Item name="sub_category" label="Подкатегория">
            <Input placeholder="Молоко" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit modal */}
      <Modal
        title={`Редактировать: ${editSku?.name ?? ''}`}
        open={!!editSku}
        onCancel={() => setEditSku(null)}
        onOk={() => editForm.submit()}
        confirmLoading={updateMutation.isPending}
        okText="Сохранить"
        cancelText="Отмена"
        width={560}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={(v) => updateMutation.mutate({ id: editSku!.id, data: v })}
        >
          <Form.Item name="brand_id" label="Бренд" rules={[{ required: true }]}>
            <Select options={brandOptions} />
          </Form.Item>
          <Form.Item name="name" label="Название" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="article" label="Артикул">
            <Input />
          </Form.Item>
          <Form.Item name="rpc" label="RPC">
            <Input />
          </Form.Item>
          <Form.Item name="barcode" label="Штрихкод">
            <Input />
          </Form.Item>
          <Form.Item name="category" label="Категория">
            <Input />
          </Form.Item>
          <Form.Item name="sub_category" label="Подкатегория">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      {/* Platform drawer */}
      <PlatformDrawer sku={platformSku} onClose={() => setPlatformSku(null)} />

      {/* Reference drawer */}
      <ReferenceDrawer sku={referenceSku} onClose={() => setReferenceSku(null)} />
    </>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  return (
    <div style={{ padding: '0 4px' }}>
      <Title level={4} style={{ marginBottom: 24 }}>Настройки каталога</Title>
      <Tabs
        defaultActiveKey="brands"
        items={[
          { key: 'brands', label: 'Бренды', children: <BrandsTab /> },
          { key: 'skus', label: 'SKU', children: <SKUsTab /> },
        ]}
      />
    </div>
  )
}
