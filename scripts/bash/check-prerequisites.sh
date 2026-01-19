#!/usr/bin/env bash

# Скрипт проверки предварительных требований
#
# Этот скрипт обеспечивает единую проверку предварительных требований для рабочего процесса Spec-Driven Development.
# Он заменяет функциональность, ранее разбросанную по нескольким скриптам.
#
# Использование: ./check-prerequisites.sh [ОПЦИИ]
#
# ОПЦИИ:
#   --json              Вывод в формате JSON
#   --require-tasks     Требовать наличие tasks.md (для этапа реализации)
#   --include-tasks     Включить tasks.md в список AVAILABLE_DOCS
#   --paths-only        Выводить только переменные путей (без валидации)
#   --help, -h          Показать справку
#
# ВЫВОД:
#   Режим JSON: {"FEATURE_DIR":"...", "AVAILABLE_DOCS":["..."]}
#   Текстовый режим: FEATURE_DIR:... \n AVAILABLE_DOCS: \n ✓/✗ file.md
#   Только пути: REPO_ROOT: ... \n BRANCH: ... \n FEATURE_DIR: ... etc.

set -e

# Разбор аргументов командной строки
JSON_MODE=false
REQUIRE_TASKS=false
INCLUDE_TASKS=false
PATHS_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --json)
            JSON_MODE=true
            ;;
        --require-tasks)
            REQUIRE_TASKS=true
            ;;
        --include-tasks)
            INCLUDE_TASKS=true
            ;;
        --paths-only)
            PATHS_ONLY=true
            ;;
        --help|-h)
            cat << 'EOF'
Использование: check-prerequisites.sh [ОПЦИИ]

Единая проверка предварительных требований для рабочего процесса Spec-Driven Development.

ОПЦИИ:
  --json              Вывод в формате JSON
  --require-tasks     Требовать наличие tasks.md (для этапа реализации)
  --include-tasks     Включить tasks.md в список AVAILABLE_DOCS
  --paths-only        Выводить только переменные путей (без валидации предварительных требований)
  --help, -h          Показать это сообщение справки

ПРИМЕРЫ:
  # Проверка требований для задач (требуется plan.md)
  ./check-prerequisites.sh --json
  
  # Проверка требований для реализации (требуются plan.md и tasks.md)
  ./check-prerequisites.sh --json --require-tasks --include-tasks
  
  # Получить только пути к фичам (без валидации)
  ./check-prerequisites.sh --paths-only
  
EOF
            exit 0
            ;;
        *)
            echo "ОШИБКА: Неизвестная опция '$arg'. Используйте --help для получения информации об использовании." >&2
            exit 1
            ;;
    esac
done

# Подключение общих функций
SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Получение путей фичи и валидация ветки
eval $(get_feature_paths)
check_feature_branch "$CURRENT_BRANCH" "$HAS_GIT" || exit 1

# Если режим только путей, вывести пути и выйти (поддержка комбинации JSON + только пути)
if $PATHS_ONLY; then
    if $JSON_MODE; then
        # Минимальный набор путей в JSON (валидация не выполняется)
        printf '{"REPO_ROOT":"%s","BRANCH":"%s","FEATURE_DIR":"%s","FEATURE_SPEC":"%s","IMPL_PLAN":"%s","TASKS":"%s"}\n' \
            "$REPO_ROOT" "$CURRENT_BRANCH" "$FEATURE_DIR" "$FEATURE_SPEC" "$IMPL_PLAN" "$TASKS"
    else
        echo "REPO_ROOT: $REPO_ROOT"
        echo "BRANCH: $CURRENT_BRANCH"
        echo "FEATURE_DIR: $FEATURE_DIR"
        echo "FEATURE_SPEC: $FEATURE_SPEC"
        echo "IMPL_PLAN: $IMPL_PLAN"
        echo "TASKS: $TASKS"
    fi
    exit 0
fi

# Валидация обязательных директорий и файлов
if [[ ! -d "$FEATURE_DIR" ]]; then
    echo "ОШИБКА: Директория фичи не найдена: $FEATURE_DIR" >&2
    echo "Сначала запустите /speckit.specify, чтобы создать структуру фичи." >&2
    exit 1
fi

if [[ ! -f "$IMPL_PLAN" ]]; then
    echo "ОШИБКА: plan.md не найден в $FEATURE_DIR" >&2
    echo "Сначала запустите /speckit.plan, чтобы создать план реализации." >&2
    exit 1
fi

# Проверка tasks.md, если требуется
if $REQUIRE_TASKS && [[ ! -f "$TASKS" ]]; then
    echo "ОШИБКА: tasks.md не найден в $FEATURE_DIR" >&2
    echo "Сначала запустите /speckit.tasks, чтобы создать список задач." >&2
    exit 1
fi

# Создание списка доступных документов
docs=()

# Всегда проверять эти необязательные документы
[[ -f "$RESEARCH" ]] && docs+=("research.md")
[[ -f "$DATA_MODEL" ]] && docs+=("data-model.md")

# Проверка директории контрактов (только если она существует и содержит файлы)
if [[ -d "$CONTRACTS_DIR" ]] && [[ -n "$(ls -A "$CONTRACTS_DIR" 2>/dev/null)" ]]; then
    docs+=("contracts/")
fi

[[ -f "$QUICKSTART" ]] && docs+=("quickstart.md")

# Включить tasks.md, если запрошено и файл существует
if $INCLUDE_TASKS && [[ -f "$TASKS" ]]; then
    docs+=("tasks.md")
fi

# Вывод результатов
if $JSON_MODE; then
    # Создание JSON-массива документов
    if [[ ${#docs[@]} -eq 0 ]]; then
        json_docs="[]"
    else
        json_docs=$(printf '"%s",' "${docs[@]}")
        json_docs="[${json_docs%,}]"
    fi
    
    printf '{"FEATURE_DIR":"%s","AVAILABLE_DOCS":%s}\n' "$FEATURE_DIR" "$json_docs"
else
    # Текстовый вывод
    echo "FEATURE_DIR:$FEATURE_DIR"
    echo "AVAILABLE_DOCS:"
    
    # Показать статус каждого возможного документа
    check_file "$RESEARCH" "research.md"
    check_file "$DATA_MODEL" "data-model.md"
    check_dir "$CONTRACTS_DIR" "contracts/"
    check_file "$QUICKSTART" "quickstart.md"
    
    if $INCLUDE_TASKS; then
        check_file "$TASKS" "tasks.md"
    fi
fi
