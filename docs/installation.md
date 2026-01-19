# Руководство по установке

## Предварительные требования

- **Linux/macOS** (или Windows; скрипты PowerShell теперь поддерживаются без WSL)
- ИИ-агент для кодинга: [Claude Code](https://www.anthropic.com/claude-code), [GitHub Copilot](https://code.visualstudio.com/), [Codebuddy CLI](https://www.codebuddy.ai/cli) или [Gemini CLI](https://github.com/google-gemini/gemini-cli)
- [uv](https://docs.astral.sh/uv/) для управления пакетами
- [Python 3.11+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)

## Установка

### Инициализация нового проекта

Самый простой способ начать — инициализировать новый проект:

```bash
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init <PROJECT_NAME>
```

Или инициализировать в текущем каталоге:

```bash
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init .
# или используйте флаг --here
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init --here
```

### Указание ИИ-агента

Вы можете заранее указать своего ИИ-агента во время инициализации:

```bash
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init <project_name> --ai claude
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init <project_name> --ai gemini
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init <project_name> --ai copilot
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init <project_name> --ai codebuddy
```

### Указание типа скрипта (Shell vs PowerShell)

Все скрипты автоматизации теперь имеют варианты как для Bash (`.sh`), так и для PowerShell (`.ps1`).

Автоматическое поведение:

- Windows по умолчанию: `ps`
- Другие ОС по умолчанию: `sh`
- Интерактивный режим: вам будет предложено выбрать, если вы не передадите `--script`

Принудительный выбор типа скрипта:

```bash
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init <project_name> --script sh
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init <project_name> --script ps
```

### Игнорирование проверки инструментов агента

Если вы предпочитаете получить шаблоны без проверки наличия правильных инструментов:

```bash
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git specify init <project_name> --ai claude --ignore-agent-tools
```

## Проверка

После инициализации вы должны увидеть следующие команды, доступные в вашем ИИ-агенте:

- `/speckit.specify` - Создать спецификации
- `/speckit.plan` - Сгенерировать планы реализации
- `/speckit.tasks` - Разбить на выполнимые задачи

Каталог `.specify/scripts` будет содержать скрипты как `.sh`, так и `.ps1`.

## Устранение неполадок

### Git Credential Manager на Linux

Если у вас возникли проблемы с аутентификацией Git на Linux, вы можете установить Git Credential Manager:

```bash
#!/usr/bin/env bash
set -e
echo "Downloading Git Credential Manager v2.6.1..."
wget https://github.com/git-ecosystem/git-credential-manager/releases/download/v2.6.1/gcm-linux_amd64.2.6.1.deb
echo "Installing Git Credential Manager..."
sudo dpkg -i gcm-linux_amd64.2.6.1.deb
echo "Configuring Git to use GCM..."
git config --global credential.helper manager
echo "Cleaning up..."
rm gcm-linux_amd64.2.6.1.deb
```
