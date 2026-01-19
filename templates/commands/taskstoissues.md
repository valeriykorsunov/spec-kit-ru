---
description: Преобразует существующие задачи в готовые к выполнению, упорядоченные по зависимостям GitHub Issues для функции на основе доступных артефактов проектирования.
tools: ['github/github-mcp-server/issue_write']
scripts:
  sh: scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
  ps: scripts/powershell/check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks
---

## Пользовательский ввод

```text
$ARGUMENTS
```

Вы **ОБЯЗАНЫ** учесть пользовательский ввод перед продолжением (если он не пуст).

## План

1. Запустите `{SCRIPT}` из корня репозитория и разберите `FEATURE_DIR` и список `AVAILABLE_DOCS`. Все пути должны быть абсолютными. Для одиночных кавычек в аргументах, например "I'm Groot", используйте экранирование: например, 'I'\''m Groot' (или двойные кавычки, если возможно: "I'm Groot").
1. Из выполненного скрипта извлеките путь к **tasks** (задачам).
1. Получите URL удаленного репозитория Git (remote), выполнив:

```bash
git config --get remote.origin.url
```

> [!CAUTION]
> ПЕРЕХОДИТЕ К СЛЕДУЮЩИМ ШАГАМ, ТОЛЬКО ЕСЛИ REMOTE ЯВЛЯЕТСЯ URL GITHUB

1. Для каждой задачи в списке используйте GitHub MCP server, чтобы создать новый issue в репозитории, соответствующем Git remote.

> [!CAUTION]
> НИ ПРИ КАКИХ ОБСТОЯТЕЛЬСТВАХ НЕ СОЗДАВАЙТЕ ISSUES В РЕПОЗИТОРИЯХ, КОТОРЫЕ НЕ СОВПАДАЮТ С URL REMOTE
