# Pseudocode — Alert Config UI

## 1. AlertConfigTab (главный компонент вкладки)

```
COMPONENT AlertConfigTab:
  STATE: modalState = { mode: 'closed' }
  STATE: page = 1
  STATE: deleteTarget = null

  DATA: { query, createMutation, updateMutation, removeMutation } = useAlertConfigs(page)
  DATA: user = useAuthStore(s => s.user)
  DATA: canManage = user.role IN ['admin', 'manager']
  DATA: canCheck = user.role === 'admin'

  FUNCTION openCreate():
    SET modalState = { mode: 'create' }

  FUNCTION openEdit(config):
    SET modalState = { mode: 'edit', config }

  FUNCTION closeModal():
    SET modalState = { mode: 'closed' }

  FUNCTION handleSubmit(values):
    IF modalState.mode === 'create':
      CALL createMutation.mutate(values)
      ON SUCCESS: closeModal(), toast("Конфигурация создана")
    ELSE IF modalState.mode === 'edit':
      CALL updateMutation.mutate({ id: modalState.config.id, data: values })
      ON SUCCESS: closeModal(), toast("Изменения сохранены")

  FUNCTION confirmDelete(config):
    SHOW AntD Modal.confirm("Удалить конфигурацию?")
    ON OK:
      CALL removeMutation.mutate(config.id)
      ON SUCCESS: toast("Конфигурация удалена")

  RENDER:
    IF canManage: Button "+ Добавить" → openCreate()
    IF canCheck: AlertCheckButton
    AlertConfigTable(
      data=query.data,
      loading=query.isLoading,
      onEdit=openEdit,
      onDelete=confirmDelete,
      canManage=canManage,
      page=page,
      onPageChange=setPage
    )
    IF modalState.mode !== 'closed':
      AlertConfigModal(
        mode=modalState.mode,
        config=modalState.config,
        onSubmit=handleSubmit,
        onCancel=closeModal,
        isSubmitting=createMutation.isPending OR updateMutation.isPending
      )
```

## 2. AlertConfigTable

```
COMPONENT AlertConfigTable(data, loading, onEdit, onDelete, canManage, page, onPageChange):

  COLUMNS:
    - "Тип": render Tag (content_drop=orange, oos=red) with icon
    - "Охват":
        IF sku_id → load sku name from skusApi cache (or show truncated UUID)
        IF platform_id → load platform name
        ELSE → "Все SKU / Все платформы"
    - "Порог":
        IF alert_type === 'content_drop' → "≥ {threshold}"
        ELSE → "—"
    - "Получатели":
        SHOW first 2 emails
        IF more → "+N ещё" Tooltip with full list
    - "Активен":
        Switch checked=is_active
        IF canManage: onClick → updateMutation({ is_active: !current })
        ELSE: disabled Switch
    - "Действия" (hidden if NOT canManage):
        Button "Изм." → onEdit(record)
        Button "Удал." danger → onDelete(record)

  RENDER:
    Table(
      dataSource=data.items,
      columns=columns,
      rowKey="id",
      loading=loading,
      pagination=...
      locale.emptyText="Нет конфигураций — нажмите +, чтобы создать первую"
    )
```

## 3. AlertConfigModal

```
COMPONENT AlertConfigModal(mode, config, onSubmit, onCancel, isSubmitting):
  
  STATE: form = useForm()
  STATE: alertType = config?.alert_type OR 'content_drop'
  
  DATA: { data: skus } = useQuery(['skus', { limit: 200 }], staleTime=5min)
  DATA: { data: platforms } = useQuery(['platforms'], staleTime=5min)
  
  isEdit = mode === 'edit'
  title = isEdit ? "Редактировать конфигурацию" : "Новая конфигурация"

  ON MOUNT (edit mode):
    form.setFieldsValue({
      alert_type: config.alert_type,
      sku_id: config.sku_id,
      platform_id: config.platform_id,
      threshold: config.threshold,
      email_recipients: config.email_recipients,
      is_active: config.is_active,
    })

  FUNCTION handleAlertTypeChange(value):
    SET alertType = value
    IF value === 'oos':
      form.setFieldValue('threshold', undefined)

  FUNCTION handleFinish(values):
    payload = {
      alert_type: values.alert_type,
      sku_id: values.sku_id OR null,
      platform_id: values.platform_id OR null,
      email_recipients: values.email_recipients,
      is_active: values.is_active ?? true,
    }
    IF alertType === 'content_drop':
      payload.threshold = values.threshold
    CALL onSubmit(payload)

  FUNCTION validateEmails(emails):
    FOR each email IN emails:
      IF NOT matches /^[^\s@]+@[^\s@]+\.[^\s@]+$/:
        RETURN Error("Неверный email: {email}")
    RETURN OK

  RENDER:
    Modal(title, open=true, onCancel, footer=null):
      Form(form, onFinish=handleFinish, layout="vertical"):
        
        FormItem("alert_type", rules=[required]):
          Select(
            disabled=isEdit,
            onChange=handleAlertTypeChange,
            options=[
              { value:'content_drop', label:'Падение контента' },
              { value:'oos', label:'Нет в наличии' }
            ]
          )
        
        FormItem("sku_id"):
          Select(
            showSearch, allowClear, disabled=isEdit,
            placeholder="Все SKU",
            filterOption=(input, opt) => opt.label.toLowerCase().includes(input.toLowerCase()),
            options=skus.map(s => { value:s.id, label:`${s.name} (${s.article})` })
          )
        
        FormItem("platform_id"):
          Select(
            allowClear, disabled=isEdit,
            placeholder="Все платформы",
            options=platforms.map(p => { value:p.id, label:p.name })
          )
        
        IF alertType === 'content_drop':
          FormItem("threshold", rules=[required, min=0, max=100]):
            Row:
              Col(flex=1): Slider(min=0, max=100, value=thresholdWatch)
              Col: InputNumber(min=0, max=100, style={width:60})
        
        FormItem("email_recipients",
                  rules=[required, validator=validateEmails]):
          Select(
            mode="tags",
            tokenSeparators=[',', ' '],
            placeholder="email@example.ru"
          )
        
        FormItem("is_active", valuePropName="checked", initialValue=true):
          Switch(checkedChildren="Активен", unCheckedChildren="Отключён")
        
        Space:
          Button(onClick=onCancel): "Отмена"
          Button(type="primary", htmlType="submit", loading=isSubmitting):
            isEdit ? "Сохранить" : "Создать"
```

## 4. AlertCheckButton

```
COMPONENT AlertCheckButton:
  
  STATE: cooldownUntil = 0
  STATE: remaining = 0  // seconds until cooldown ends
  
  DATA: { run, isLoading } = useAlertCheck()
  
  // Tick remaining counter every second during cooldown
  EFFECT [cooldownUntil]:
    IF cooldownUntil > Date.now():
      interval = setInterval(() => {
        diff = Math.ceil((cooldownUntil - Date.now()) / 1000)
        IF diff > 0: SET remaining = diff
        ELSE: clearInterval, SET remaining = 0
      }, 1000)
      CLEANUP: clearInterval

  FUNCTION handleClick():
    CALL run()
    ON SUCCESS: SET cooldownUntil = Date.now() + 60_000

  isCooling = remaining > 0

  RENDER:
    Button(
      icon=<PlayCircleOutlined />,
      onClick=handleClick,
      loading=isLoading,
      disabled=isCooling,
      title=isCooling ? `Доступно через ${remaining}с` : "Запустить проверку алертов"
    ):
      isCooling ? `Проверка (${remaining}с)` : "Запустить проверку"
```

## 5. index.tsx (обновлённая страница Alerts)

```
COMPONENT AlertsPage:
  STATE: activeTab = 'events'

  RENDER:
    Title("Алерты")
    Tabs(
      activeKey=activeTab,
      onChange=setActiveTab,
      items=[
        {
          key: 'events',
          label: Badge(count=unreadCount): "События",
          children: AlertEventTab
        },
        {
          key: 'configs',
          label: "Конфигурации",
          children: AlertConfigTab
        }
      ]
    )
```

## 6. Existing Event Tab (вынести без изменений)

```
COMPONENT AlertEventTab:
  // Текущее содержимое index.tsx перенести без изменений:
  // - фильтр по alert_type
  // - фильтр показать/скрыть квитированные
  // - таблица событий
  // - кнопка "Квитировать"
```
