#!/usr/bin/env bash

set -e

# Разбор аргументов командной строки
JSON_MODE=false
ARGS=()

for arg in "$@"; do
    case "$arg" in
        --json) 
            JSON_MODE=true 
            ;;
        --help|-h) 
            echo "Использование: $0 [--json]"
            echo "  --json    Вывод результатов в формате JSON"
            echo "  --help    Показать это справочное сообщение"
            exit 0 
            ;;
        *) 
            ARGS+=("$arg") 
            ;;
    esac
done

# Получение директории скрипта и загрузка общих функций
SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Получение всех путей и переменных из общих функций
eval $(get_feature_paths)

# Проверка, находимся ли мы в правильной ветке функции (только для git-репозиториев)
check_feature_branch "$CURRENT_BRANCH" "$HAS_GIT" || exit 1

# Убедиться, что директория функции существует
mkdir -p "$FEATURE_DIR"

# Копирование шаблона плана, если он существует
TEMPLATE="$REPO_ROOT/.specify/templates/plan-template.md"
if [[ -f "$TEMPLATE" ]]; then
    cp "$TEMPLATE" "$IMPL_PLAN"
    echo "Шаблон плана скопирован в $IMPL_PLAN"
else
    echo "Предупреждение: Шаблон плана не найден по пути $TEMPLATE"
    # Создание базового файла плана, если шаблон не существует
    touch "$IMPL_PLAN"
fi

# Вывод результатов
if $JSON_MODE; then
    printf '{"FEATURE_SPEC":"%s","IMPL_PLAN":"%s","SPECS_DIR":"%s","BRANCH":"%s","HAS_GIT":"%s"}\n' \
        "$FEATURE_SPEC" "$IMPL_PLAN" "$FEATURE_DIR" "$CURRENT_BRANCH" "$HAS_GIT"
else
    echo "FEATURE_SPEC: $FEATURE_SPEC"
    echo "IMPL_PLAN: $IMPL_PLAN" 
    echo "SPECS_DIR: $FEATURE_DIR"
    echo "BRANCH: $CURRENT_BRANCH"
    echo "HAS_GIT: $HAS_GIT"
fi

