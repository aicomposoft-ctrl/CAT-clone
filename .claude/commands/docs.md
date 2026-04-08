---
description: Generate or update project documentation in Russian and English.
  Creates a comprehensive set of markdown files covering deployment, usage,
  architecture, and user flows.
  $ARGUMENTS: optional flags — "rus" (Russian only), "eng" (English only), "update" (refresh existing)
---

# /docs $ARGUMENTS

## Purpose

Generate professional, bilingual project documentation from source code,
existing docs, and development insights. Output: `/README/rus/` and `/README/eng/`.

## Step 1: Gather Context

Read all available sources to build comprehensive understanding:

### Primary sources (project documentation):
```
docs/PRD.md (or docs/*.md)          — product requirements, features
docs/Architecture.md                 — system architecture, tech stack
docs/Specification.md                — API, data model, user stories
docs/Completion.md                   — deployment, environment setup
docs/features/                       — feature-specific documentation
docs/plans/                          — implementation plans
CLAUDE.md                            — project overview, commands, agents
DEVELOPMENT_GUIDE.md                 — development workflow
INSTALL.md                           — installation instructions
docker-compose.yml                   — infrastructure services
.env.example                         — environment variables
```

### Secondary sources (knowledge base):
```
myinsights/1nsights.md               — development insights index
myinsights/details/                   — detailed insight files
.claude/feature-roadmap.json          — feature list and statuses
```

### Tertiary sources (code analysis):
```
Source code structure                 — actual implementation
package.json / Cargo.toml / etc.     — dependencies, scripts
README.md (existing, if any)         — current documentation
```

## Step 2: Determine Scope

```
IF $ARGUMENTS contains "rus":  languages = ["rus"]
ELIF $ARGUMENTS contains "eng": languages = ["eng"]
ELSE: languages = ["rus", "eng"]

IF $ARGUMENTS contains "update":
    mode = "update"  — read existing /README/ files, update only changed sections
ELSE:
    mode = "create"  — generate from scratch
```

## Step 3: Generate Documentation Set

For EACH language in languages, generate these files:

### File 1: `deployment.md` — Как развернуть систему / Deployment Guide

```markdown
# Развертывание системы / Deployment Guide

## Требования к окружению
- OS, runtime versions, Docker version
- Minimum hardware requirements

## Быстрый старт (Quick Start)
- Clone → configure → run (step by step)
- Docker-based deployment
- Environment variables explanation

## Полное развертывание (Production Deployment)
- Infrastructure provisioning
- SSL/TLS configuration
- Database initialization
- Service startup order
- Health checks verification

## Обновление (Updating)
- How to update to a new version
- Database migration steps
- Rollback procedure
```

### File 2: `admin-guide.md` — Руководство администратора / Admin Guide

```markdown
# Руководство администратора / Administrator Guide

## Управление пользователями
- User creation, roles, permissions

## Конфигурация системы
- Configuration files and their purposes
- Feature flags / toggles
- Performance tuning

## Мониторинг и логирование
- How to check system health
- Log locations and format
- Alerting setup

## Резервное копирование
- Backup procedures
- Restore procedures

## Устранение неполадок
- Common issues and solutions
- Diagnostic commands
```

### File 3: `user-guide.md` — Руководство пользователя / User Guide

```markdown
# Руководство пользователя / User Guide

## Начало работы
- First login / registration
- Initial setup

## Основные функции
- Feature-by-feature walkthrough
- Screenshots / descriptions of key screens

## Типичные сценарии использования
- Common workflows step by step

## FAQ
- Frequently asked questions
```

### File 4: `infrastructure.md` — Требования к инфраструктуре / Infrastructure Requirements

```markdown
# Требования к инфраструктуре / Infrastructure Requirements

## Минимальные требования
- CPU, RAM, Disk for each component
- Network requirements

## Рекомендуемые требования
- Production-grade specifications
- High-availability setup

## Сетевые требования
- Ports to open
- Internal service communication
- External API access requirements

## Зависимости
- Required external services
- Third-party integrations
- License requirements
```

### File 5: `architecture.md` — Архитектура системы / System Architecture

```markdown
# Архитектура и принципы работы / Architecture & Design Principles

## Обзор архитектуры
- High-level system diagram (Mermaid)
- Component responsibilities

## Технологический стек
- Languages, frameworks, databases
- Why each was chosen (from ADRs if available)

## Компоненты системы
- Service-by-service description
- Communication patterns (REST, events, queues)

## Модель данных
- Key entities and relationships
- Database schema overview

## Безопасность
- Authentication / authorization approach
- Data encryption
- API security

## Масштабируемость
- Horizontal scaling strategy
- Bottlenecks and mitigations
```

### File 6: `ui-guide.md` — Интерфейс системы / UI Guide

```markdown
# Интерфейс системы / UI Guide

## Структура интерфейса
- Main navigation layout
- Key screens and their purposes

## Основные экраны
- Dashboard / Home
- Feature-specific screens
- Settings / Admin panel

## Элементы управления
- Common UI patterns used
- Keyboard shortcuts (if any)
- Mobile / responsive behavior
```

### File 7: `user-flows.md` — Пользовательские сценарии / User & Admin Flows

```markdown
# Типовые сценарии / User & Admin Flows

## User Flow: Регистрация и первый вход
[Step-by-step with Mermaid sequence diagram]

## User Flow: Основной рабочий процесс
[Primary user journey — the main thing users do]

## User Flow: [Feature-specific flow]
[For each key feature]

## Admin Flow: Настройка системы
[Admin setup walkthrough]

## Admin Flow: Управление пользователями
[User management walkthrough]

## Admin Flow: Мониторинг
[Monitoring and maintenance walkthrough]
```

## Step 4: Generate Output

1. Create directory structure:
```bash
mkdir -p README/rus README/eng
```

2. Generate files for each language:
   - Russian files go to `README/rus/`
   - English files go to `README/eng/`
   - Use proper language throughout (not machine-translated fragments)

3. Generate `README/index.md` — table of contents linking both languages:
```markdown
# Project Documentation

## 🇷🇺 Документация на русском
- [Развертывание](rus/deployment.md)
- [Руководство администратора](rus/admin-guide.md)
- [Руководство пользователя](rus/user-guide.md)
- [Требования к инфраструктуре](rus/infrastructure.md)
- [Архитектура](rus/architecture.md)
- [Интерфейс](rus/ui-guide.md)
- [Пользовательские сценарии](rus/user-flows.md)

## 🇬🇧 English Documentation
- [Deployment Guide](eng/deployment.md)
- [Administrator Guide](eng/admin-guide.md)
- [User Guide](eng/user-guide.md)
- [Infrastructure Requirements](eng/infrastructure.md)
- [Architecture](eng/architecture.md)
- [UI Guide](eng/ui-guide.md)
- [User & Admin Flows](eng/user-flows.md)
```

## Step 5: Commit and Report

```bash
git add README/
git commit -m "docs: generate project documentation (RU/EN)"
git push origin HEAD
```

Report:
```
📚 Documentation generated: README/

🇷🇺 Russian (README/rus/):
   ✅ deployment.md — развертывание
   ✅ admin-guide.md — руководство администратора
   ✅ user-guide.md — руководство пользователя
   ✅ infrastructure.md — требования к инфраструктуре
   ✅ architecture.md — архитектура
   ✅ ui-guide.md — интерфейс
   ✅ user-flows.md — пользовательские сценарии

🇬🇧 English (README/eng/):
   ✅ deployment.md — deployment guide
   ✅ admin-guide.md — admin guide
   ✅ user-guide.md — user guide
   ✅ infrastructure.md — infrastructure requirements
   ✅ architecture.md — architecture
   ✅ ui-guide.md — UI guide
   ✅ user-flows.md — user & admin flows

📄 README/index.md — documentation index
```

## Update Mode

When `$ARGUMENTS` contains "update":
1. Read existing files in `README/rus/` and `README/eng/`
2. Compare with current project state
3. Update only sections that have changed
4. Preserve any manual additions (sections not in template)
5. Commit: `git commit -m "docs: update project documentation"`

## Notes

- Documentation is generated from ACTUAL project state, not assumptions
- Mermaid diagrams are used for architecture and flow visualizations
- If UI doesn't exist yet, ui-guide.md notes this and describes planned UI
- If some information is unavailable, the section notes what's missing
- myinsights/ is checked for gotchas and important notes to include
