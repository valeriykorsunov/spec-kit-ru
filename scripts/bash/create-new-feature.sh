#!/usr/bin/env bash

set -e

JSON_MODE=false
SHORT_NAME=""
BRANCH_NUMBER=""
ARGS=()
i=1
while [ $i -le $# ]; do
    arg="${!i}"
    case "$arg" in
        --json) 
            JSON_MODE=true 
            ;;
        --short-name)
            if [ $((i + 1)) -gt $# ]; then
                echo 'Ошибка: параметр --short-name требует значения' >&2
                exit 1
            fi
            i=$((i + 1))
            next_arg="${!i}"
            # Проверяем, является ли следующий аргумент другой опцией (начинается с --)
            if [[ "$next_arg" == --* ]]; then
                echo 'Ошибка: параметр --short-name требует значения' >&2
                exit 1
            fi
            SHORT_NAME="$next_arg"
            ;;
        --number)
            if [ $((i + 1)) -gt $# ]; then
                echo 'Ошибка: параметр --number требует значения' >&2
                exit 1
            fi
            i=$((i + 1))
            next_arg="${!i}"
            if [[ "$next_arg" == --* ]]; then
                echo 'Ошибка: параметр --number требует значения' >&2
                exit 1
            fi
            BRANCH_NUMBER="$next_arg"
            ;;
        --help|-h) 
            echo "Использование: $0 [--json] [--short-name <имя>] [--number N] <описание_функции>"
            echo ""
            echo "Опции:"
            echo "  --json              Вывод в формате JSON"
            echo "  --short-name <имя>  Указать пользовательское короткое имя (2-4 слова) для ветки"
            echo "  --number N          Указать номер ветки вручную (переопределяет автоопределение)"
            echo "  --help, -h          Показать это справочное сообщение"
            echo ""
            echo "Примеры:"
            echo "  $0 'Add user authentication system' --short-name 'user-auth'"
            echo "  $0 'Implement OAuth2 integration for API' --number 5"
            exit 0
            ;;
        *) 
            ARGS+=("$arg") 
            ;;
    esac
    i=$((i + 1))
done

FEATURE_DESCRIPTION="${ARGS[*]}"
if [ -z "$FEATURE_DESCRIPTION" ]; then
    echo "Использование: $0 [--json] [--short-name <имя>] [--number N] <описание_функции>" >&2
    exit 1
fi

# Функция для поиска корня репозитория по существующим маркерам проекта
find_repo_root() {
    local dir="$1"
    while [ "$dir" != "/" ]; do
        if [ -d "$dir/.git" ] || [ -d "$dir/.specify" ]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    return 1
}

# Функция для получения наибольшего номера из каталога specs
get_highest_from_specs() {
    local specs_dir="$1"
    local highest=0
    
    if [ -d "$specs_dir" ]; then
        for dir in "$specs_dir"/*; do
            [ -d "$dir" ] || continue
            dirname=$(basename "$dir")
            number=$(echo "$dirname" | grep -o '^[0-9]\+' || echo "0")
            number=$((10#$number))
            if [ "$number" -gt "$highest" ]; then
                highest=$number
            fi
        done
    fi
    
    echo "$highest"
}

# Функция для получения наибольшего номера из веток git
get_highest_from_branches() {
    local highest=0
    
    # Получить все ветки (локальные и удаленные)
    branches=$(git branch -a 2>/dev/null || echo "")
    
    if [ -n "$branches" ]; then
        while IFS= read -r branch; do
            # Очистка имени ветки: удаление ведущих маркеров и префиксов удаленных репозиториев
            clean_branch=$(echo "$branch" | sed 's/^[* ]*//; s|^remotes/[^/]*/||')
            
            # Извлечение номера фичи, если ветка соответствует шаблону ###-*
            if echo "$clean_branch" | grep -q '^[0-9]\{3\}-'; then
                number=$(echo "$clean_branch" | grep -o '^[0-9]\{3\}' || echo "0")
                number=$((10#$number))
                if [ "$number" -gt "$highest" ]; then
                    highest=$number
                fi
            fi
        done <<< "$branches"
    fi
    
    echo "$highest"
}

# Функция для проверки существующих веток (локальных и удаленных) и возврата следующего доступного номера
check_existing_branches() {
    local specs_dir="$1"

    # Получить все удаленные ветки для актуальной информации (подавить ошибки, если удаленных репозиториев нет)
    git fetch --all --prune 2>/dev/null || true

    # Получить наибольший номер из ВСЕХ веток (не только совпадающих по короткому имени)
    local highest_branch=$(get_highest_from_branches)

    # Получить наибольший номер из ВСЕХ спецификаций (не только совпадающих по короткому имени)
    local highest_spec=$(get_highest_from_specs "$specs_dir")

    # Взять максимум из обоих
    local max_num=$highest_branch
    if [ "$highest_spec" -gt "$max_num" ]; then
        max_num=$highest_spec
    fi

    # Вернуть следующий номер
    echo $((max_num + 1))
}

# Функция для очистки и форматирования имени ветки
clean_branch_name() {
    local name="$1"
    # Транслитерация кириллицы в латиницу (простая реализация через sed)
    # Если echo поддерживает юникод, это должно сработать для основных символов
    # Но sed может зависеть от локали. Попробуем базовую транслитерацию.
    
    # Сначала переведем в нижний регистр (работает для латиницы)
    local lower_name=$(echo "$name" | tr '[:upper:]' '[:lower:]')
    
    # Попытка транслитерации (опционально, если input русский)
    # Здесь мы оставим оригинальную логику очистки для надежности,
    # так как полная транслитерация в bash сложна и громоздка.
    # Пользователю лучше использовать английский для имен веток.
    
    echo "$lower_name" | sed 's/[^a-z0-9]/-/g' | sed 's/-\+/-/g' | sed 's/^-//' | sed 's/-$//'
}

# Определение корня репозитория. Предпочтение git, если доступен, но откат
# к поиску маркеров репозитория, чтобы рабочий процесс работал в репозиториях,
# инициализированных с --no-git.
SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if git rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT=$(git rev-parse --show-toplevel)
    HAS_GIT=true
else
    REPO_ROOT="$(find_repo_root "$SCRIPT_DIR")"
    if [ -z "$REPO_ROOT" ]; then
        echo "Ошибка: Не удалось определить корень репозитория. Пожалуйста, запустите этот скрипт из репозитория." >&2
        exit 1
    fi
    HAS_GIT=false
fi

cd "$REPO_ROOT"

SPECS_DIR="$REPO_ROOT/specs"
mkdir -p "$SPECS_DIR"

# Функция для генерации имени ветки с фильтрацией стоп-слов и длины
generate_branch_name() {
    local description="$1"
    
    # Общие стоп-слова для фильтрации (английские)
    local stop_words="^(i|a|an|the|to|for|of|in|on|at|by|with|from|is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|should|could|can|may|might|must|shall|this|that|these|those|my|your|our|their|want|need|add|get|set)$"
    
    # Преобразование в нижний регистр и разбиение на слова
    local clean_name=$(echo "$description" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/ /g')
    
    # Фильтрация слов: удаление стоп-слов и слов короче 3 символов (если они не являются аббревиатурами в оригинале)
    local meaningful_words=()
    for word in $clean_name; do
        # Пропуск пустых слов
        [ -z "$word" ] && continue
        
        # Оставить слова, которые НЕ являются стоп-словами И (длина >= 3 ИЛИ являются потенциальными аббревиатурами)
        if ! echo "$word" | grep -qiE "$stop_words"; then
            if [ ${#word} -ge 3 ]; then
                meaningful_words+=("$word")
            elif echo "$description" | grep -q "\b${word^^}\b"; then
                # Оставить короткие слова, если они появляются в верхнем регистре в оригинале (вероятно, аббревиатуры)
                meaningful_words+=("$word")
            fi
        fi
    done
    
    # Если есть значимые слова, использовать первые 3-4 из них
    if [ ${#meaningful_words[@]} -gt 0 ]; then
        local max_words=3
        if [ ${#meaningful_words[@]} -eq 4 ]; then max_words=4; fi
        
        local result=""
        local count=0
        for word in "${meaningful_words[@]}"; do
            if [ $count -ge $max_words ]; then break; fi
            if [ -n "$result" ]; then result="$result-"; fi
            result="$result$word"
            count=$((count + 1))
        done
        echo "$result"
    else
        # Откат к оригинальной логике, если значимые слова не найдены
        local cleaned=$(clean_branch_name "$description")
        echo "$cleaned" | tr '-' '\n' | grep -v '^$' | head -3 | tr '\n' '-' | sed 's/-$//'
    fi
}

# Генерация имени ветки
if [ -n "$SHORT_NAME" ]; then
    # Использовать предоставленное короткое имя, просто очистить его
    BRANCH_SUFFIX=$(clean_branch_name "$SHORT_NAME")
else
    # Сгенерировать из описания с умной фильтрацией
    BRANCH_SUFFIX=$(generate_branch_name "$FEATURE_DESCRIPTION")
fi

# Определение номера ветки
if [ -z "$BRANCH_NUMBER" ]; then
    if [ "$HAS_GIT" = true ]; then
        # Проверить существующие ветки на удаленных репозиториях
        BRANCH_NUMBER=$(check_existing_branches "$SPECS_DIR")
    else
        # Откат к проверке локального каталога
        HIGHEST=$(get_highest_from_specs "$SPECS_DIR")
        BRANCH_NUMBER=$((HIGHEST + 1))
    fi
fi

# Принудительная интерпретация в десятичной системе для предотвращения восьмеричного преобразования (например, 010 -> 8 в восьмеричной, но должно быть 10 в десятичной)
FEATURE_NUM=$(printf "%03d" "$((10#$BRANCH_NUMBER))")
BRANCH_NAME="${FEATURE_NUM}-${BRANCH_SUFFIX}"

# GitHub накладывает ограничение в 244 байта на имена веток
# Валидация и обрезка при необходимости
MAX_BRANCH_LENGTH=244
if [ ${#BRANCH_NAME} -gt $MAX_BRANCH_LENGTH ]; then
    # Рассчитать, сколько нужно обрезать от суффикса
    # Учитывать: номер фичи (3) + дефис (1) = 4 символа
    MAX_SUFFIX_LENGTH=$((MAX_BRANCH_LENGTH - 4))
    
    # Обрезать суффикс по границе слова, если возможно
    TRUNCATED_SUFFIX=$(echo "$BRANCH_SUFFIX" | cut -c1-$MAX_SUFFIX_LENGTH)
    # Удалить висячий дефис, если обрезка создала его
    TRUNCATED_SUFFIX=$(echo "$TRUNCATED_SUFFIX" | sed 's/-$//')
    
    ORIGINAL_BRANCH_NAME="$BRANCH_NAME"
    BRANCH_NAME="${FEATURE_NUM}-${TRUNCATED_SUFFIX}"
    
    >&2 echo "[specify] Предупреждение: Имя ветки превышает лимит GitHub в 244 байта"
    >&2 echo "[specify] Оригинал: $ORIGINAL_BRANCH_NAME (${#ORIGINAL_BRANCH_NAME} байт)"
    >&2 echo "[specify] Обрезано до: $BRANCH_NAME (${#BRANCH_NAME} байт)"
fi

if [ "$HAS_GIT" = true ]; then
    git checkout -b "$BRANCH_NAME"
else
    >&2 echo "[specify] Предупреждение: Git-репозиторий не обнаружен; создание ветки для $BRANCH_NAME пропущено"
fi

FEATURE_DIR="$SPECS_DIR/$BRANCH_NAME"
mkdir -p "$FEATURE_DIR"

TEMPLATE="$REPO_ROOT/.specify/templates/spec-template.md"
SPEC_FILE="$FEATURE_DIR/spec.md"
if [ -f "$TEMPLATE" ]; then cp "$TEMPLATE" "$SPEC_FILE"; else touch "$SPEC_FILE"; fi

# Установить переменную окружения SPECIFY_FEATURE для текущей сессии
export SPECIFY_FEATURE="$BRANCH_NAME"

if $JSON_MODE; then
    printf '{"BRANCH_NAME":"%s","SPEC_FILE":"%s","FEATURE_NUM":"%s"}\n' "$BRANCH_NAME" "$SPEC_FILE" "$FEATURE_NUM"
else
    echo "BRANCH_NAME: $BRANCH_NAME"
    echo "SPEC_FILE: $SPEC_FILE"
    echo "FEATURE_NUM: $FEATURE_NUM"
    echo "Переменная окружения SPECIFY_FEATURE установлена в: $BRANCH_NAME"
fi
