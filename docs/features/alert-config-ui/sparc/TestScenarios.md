# Test Scenarios (BDD) — Alert Config UI

## Feature: Alert Config Management

### Scenario: Admin views empty configs list
```gherkin
Given I am logged in as admin
And no alert configs exist for my org
When I navigate to Alerts page
And I click tab "Конфигурации"
Then I see empty state "Нет конфигураций — нажмите +, чтобы создать первую"
And I see button "+ Добавить"
And I see button "Запустить проверку"
```

### Scenario: Admin creates content_drop alert config
```gherkin
Given I am logged in as admin
And I am on Alerts page, tab "Конфигурации"
When I click "+ Добавить"
Then a modal "Новая конфигурация" opens
When I select alert_type "Падение контента"
Then field "Порог" becomes visible
When I set threshold to 70
And I enter email "ops@brand.ru"
And I click "Создать"
Then POST /api/v1/alerts/configs is called with:
  | alert_type | content_drop |
  | threshold  | 70           |
  | email_recipients | ["ops@brand.ru"] |
And modal closes
And toast "Конфигурация создана" appears
And table shows the new config row
```

### Scenario: Admin creates oos alert — threshold hidden
```gherkin
Given I am on Alerts page, tab "Конфигурации"
When I click "+ Добавить"
And I select alert_type "Нет в наличии"
Then field "Порог" is NOT visible
When I enter email "ops@brand.ru"
And I click "Создать"
Then POST body does NOT contain "threshold" field
```

### Scenario: Form validation — content_drop without threshold
```gherkin
Given modal "Новая конфигурация" is open
And alert_type "Падение контента" is selected
When I clear threshold field
And I click "Создать"
Then error "Укажите порог" appears under threshold field
And POST is NOT called
```

### Scenario: Form validation — invalid email
```gherkin
Given modal "Новая конфигурация" is open
When I type "not-an-email" in email_recipients
And I press Enter
And I click "Создать"
Then validation error appears
And POST is NOT called
```

### Scenario: Manager edits alert threshold
```gherkin
Given I am logged in as manager
And a content_drop config with threshold=70 exists
When I click "Изм." on that row
Then modal "Редактировать конфигурацию" opens
And field "alert_type" is disabled (read-only)
And field "sku_id" is disabled
When I change threshold to 60
And I click "Сохранить"
Then PATCH /api/v1/alerts/configs/{id} is called with { "threshold": 60 }
And toast "Изменения сохранены" appears
And table shows updated threshold "≥ 60"
```

### Scenario: Admin deletes config with confirmation
```gherkin
Given a config exists in the table
When I click "Удал." on that row
Then confirmation dialog "Вы уверены?" appears
When I click "OK"
Then DELETE /api/v1/alerts/configs/{id} is called
And row disappears from table
And toast "Конфигурация удалена" appears
```

### Scenario: Delete cancelled
```gherkin
Given a config exists in the table
When I click "Удал." on that row
And confirmation dialog appears
When I click "Отмена"
Then DELETE is NOT called
And row remains in table
```

### Scenario: Toggle is_active via Switch
```gherkin
Given a config with is_active=true exists in the table
When I click the Switch in that row (manager or admin)
Then PATCH /api/v1/alerts/configs/{id} is called with { "is_active": false }
And Switch shows disabled state optimistically
```

### Scenario: Viewer cannot manage configs
```gherkin
Given I am logged in as viewer
When I navigate to Alerts page, tab "Конфигурации"
Then I see the table (read-only)
And button "+ Добавить" is NOT visible
And "Изм." and "Удал." buttons are NOT visible
And Switches in table are disabled
And button "Запустить проверку" is NOT visible
```

### Scenario: Admin runs manual check
```gherkin
Given I am logged in as admin
And I am on Alerts tab "Конфигурации"
When I click "Запустить проверку"
Then POST /api/v1/alerts/check is called
And response: { events_created: 2, emails_sent: 1, errors: [] }
Then success message "Создано событий: 2, отправлено писем: 1" appears
And button becomes disabled with countdown "Проверка (60с)"
```

### Scenario: Rate limit on check button
```gherkin
Given I already clicked "Запустить проверку" 60 seconds ago
And button is still in cooldown
Then button shows "Проверка (Nс)" and is disabled
After cooldown expires:
Then button becomes active again
```

### Scenario: API returns 429 on check
```gherkin
Given POST /api/v1/alerts/check returns 429
When I click "Запустить проверку"
Then toast "Слишком много запросов, подождите 1 минуту" appears
And cooldown timer starts
```

### Scenario: Pagination
```gherkin
Given 55 alert configs exist for my org
When I view Configs tab
Then first page shows 50 rows
And pagination shows "1 / 2"
When I click page 2
Then GET /api/v1/alerts/configs?page=2&size=50 is called
And 5 rows are shown
```

### Scenario: Network error on create
```gherkin
Given network is unavailable
When I submit the create form
Then toast "Нет соединения с сервером" appears
And modal remains open with form data intact
```

## Feature: Alert Events Tab (regression)

### Scenario: Events tab unchanged
```gherkin
Given I am on Alerts page
When I click tab "События"
Then existing events table is shown
And all existing functionality works as before
```

## Edge Cases (добавлено по результатам валидации)

### Scenario: SKU search in create modal
```gherkin
Given modal "Новая конфигурация" is open
When I type "молок" in the SKU search field
Then API GET /skus?search=молок is called (debounced 300ms)
And matching SKUs appear in the dropdown
When I select one
Then sku_id field is set to its UUID
```

### Scenario: Switch toggle failure — optimistic update rollback
```gherkin
Given a config with is_active=true exists in the table
And PATCH /api/v1/alerts/configs/{id} returns 500
When I click the Switch
Then Switch shows disabled state optimistically
But after error response
Then Switch reverts to enabled state
And toast "Ошибка при изменении статуса" appears
```

### Scenario: Modal re-entry after failed create
```gherkin
Given I submitted the create form
And API returned 422 validation error
Then modal stays open with all entered values preserved
And error message is shown inline
When I fix the error and click "Создать"
Then the form submits successfully
```

### Scenario: Email recipients truncation in table
```gherkin
Given a config has email_recipients = ["a@b.ru", "c@d.ru", "e@f.ru"]
When I view the configs table
Then column "Получатели" shows "a@b.ru, c@d.ru" + "+1 ещё"
When I hover over "+1 ещё"
Then tooltip shows "e@f.ru"
```

### Scenario: Config deleted by another admin while modal open
```gherkin
Given I opened edit modal for config X
And another admin deleted config X in another session
When I click "Сохранить"
Then PATCH returns 404
Then modal closes
And toast "Конфигурация не найдена — обновите список" appears
And table refreshes
```

### Scenario: Cooldown resets only on success
```gherkin
Given I clicked "Запустить проверку"
And POST /alerts/check returned 500 (server error)
Then cooldown timer does NOT start
And button remains active immediately
When I click again and POST returns 200
Then 60s cooldown starts
```
