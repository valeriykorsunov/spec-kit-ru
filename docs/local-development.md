# Руководство по локальной разработке

Это руководство показывает, как итерировать `specify` CLI локально, не публикуя релиз и не делая коммит в `main`.

> Скрипты теперь имеют варианты как для Bash (`.sh`), так и для PowerShell (`.ps1`). CLI автоматически выбирает нужный вариант в зависимости от ОС, если вы не передадите флаг `--script sh|ps`.

## 1. Клонирование и переключение веток

```bash
git clone https://github.com/valeriykorsunov/spec-kit-ru.git
cd spec-kit
# Работайте в ветке фичи
git checkout -b your-feature-branch
```

## 2. Запуск CLI напрямую (самая быстрая обратная связь)

Вы можете выполнить CLI через точку входа модуля, ничего не устанавливая:

```bash
# Из корня репозитория
python -m src.specify_cli --help
python -m src.specify_cli init demo-project --ai claude --ignore-agent-tools --script sh
```

Если вы предпочитаете стиль вызова файла скрипта (использует shebang):

```bash
python src/specify_cli/__init__.py init demo-project --script ps
```

## 3. Использование Editable Install (Изолированная среда)

Создайте изолированную среду с помощью `uv`, чтобы зависимости разрешались именно так, как их получают конечные пользователи:

```bash
# Создать и активировать виртуальное окружение (uv автоматически управляет .venv)
uv venv
source .venv/bin/activate  # или в Windows PowerShell: .venv\Scripts\Activate.ps1

# Установить проект в редактируемом режиме
uv pip install -e .

# Теперь точка входа 'specify' доступна
specify --help
```

Повторный запуск после редактирования кода не требует переустановки благодаря редактируемому режиму.

## 4. Вызов с помощью uvx напрямую из Git (Текущая ветка)

`uvx` может запускаться из локального пути (или ссылки Git) для симуляции пользовательских потоков:

```bash
uvx --from . specify init demo-uvx --ai copilot --ignore-agent-tools --script sh
```

Вы также можете направить uvx на конкретную ветку без слияния:

```bash
# Сначала отправьте вашу рабочую ветку
git push origin your-feature-branch
uvx --from git+https://github.com/valeriykorsunov/spec-kit-ru.git@your-feature-branch specify init demo-branch-test --script ps
```

### 4a. Абсолютный путь uvx (Запуск откуда угодно)

Если вы находитесь в другом каталоге, используйте абсолютный путь вместо `.`:

```bash
uvx --from /mnt/c/GitHub/spec-kit specify --help
uvx --from /mnt/c/GitHub/spec-kit specify init demo-anywhere --ai copilot --ignore-agent-tools --script sh
```

Установите переменную окружения для удобства:

```bash
export SPEC_KIT_SRC=/mnt/c/GitHub/spec-kit
uvx --from "$SPEC_KIT_SRC" specify init demo-env --ai copilot --ignore-agent-tools --script ps
```

(Опционально) Определите функцию оболочки:

```bash
specify-dev() { uvx --from /mnt/c/GitHub/spec-kit specify "$@"; }
# Затем
specify-dev --help
```

## 5. Тестирование логики прав доступа скриптов

После запуска `init`, проверьте, что shell-скрипты исполняемые в POSIX системах:

```bash
ls -l scripts | grep .sh
# Ожидается бит выполнения у владельца (например, -rwxr-xr-x)
```

В Windows вы вместо этого будете использовать скрипты `.ps1` (chmod не требуется).
