#!/usr/bin/env pwsh

# Скрипт проверки предварительных условий (PowerShell)
#
# Этот скрипт обеспечивает единую проверку предварительных условий для рабочего процесса разработки на основе спецификаций (Spec-Driven Development).
# Он заменяет функциональность, ранее разбросанную по нескольким скриптам.
#
# Использование: ./check-prerequisites.ps1 [ОПЦИИ]
#
# ОПЦИИ:
#   -Json               Вывод в формате JSON
#   -RequireTasks       Требовать наличие tasks.md (для этапа реализации)
#   -IncludeTasks       Включить tasks.md в список AVAILABLE_DOCS
#   -PathsOnly          Вывести только переменные путей (без валидации)
#   -Help, -h           Показать справку

[CmdletBinding(PositionalBinding=$false)]
param(
    [switch]$Json,
    [switch]$RequireTasks,
    [switch]$IncludeTasks,
    [switch]$PathsOnly,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

# Показать справку, если запрошено
if ($Help) {
    Write-Output @"
Использование: check-prerequisites.ps1 [ОПЦИИ]

Единая проверка предварительных условий для рабочего процесса Spec-Driven Development.

ОПЦИИ:
  -Json               Вывод в формате JSON
  -RequireTasks       Требовать наличие tasks.md (для этапа реализации)
  -IncludeTasks       Включить tasks.md в список AVAILABLE_DOCS
  -PathsOnly          Вывести только переменные путей (без проверки условий)
  -Help, -h           Показать это справочное сообщение

ПРИМЕРЫ:
  # Проверка условий для задач (требуется plan.md)
  .\check-prerequisites.ps1 -Json
  
  # Проверка условий реализации (требуются plan.md + tasks.md)
  .\check-prerequisites.ps1 -Json -RequireTasks -IncludeTasks
  
  # Получить только пути к функциональности (без валидации)
  .\check-prerequisites.ps1 -PathsOnly

"@
    exit 0
}

# Подключение общих функций
. "$PSScriptRoot/common.ps1"

# Получение путей функциональности и проверка ветки
$paths = Get-FeaturePathsEnv

if (-not (Test-FeatureBranch -Branch $paths.CURRENT_BRANCH -HasGit:$paths.HAS_GIT)) { 
    exit 1 
}

# Если режим только путей, вывести пути и выйти (поддержка комбинации -Json -PathsOnly)
if ($PathsOnly) {
    if ($Json) {
        [PSCustomObject]@{
            REPO_ROOT    = $paths.REPO_ROOT
            BRANCH       = $paths.CURRENT_BRANCH
            FEATURE_DIR  = $paths.FEATURE_DIR
            FEATURE_SPEC = $paths.FEATURE_SPEC
            IMPL_PLAN    = $paths.IMPL_PLAN
            TASKS        = $paths.TASKS
        } | ConvertTo-Json -Compress
    } else {
        Write-Output "REPO_ROOT: $($paths.REPO_ROOT)"
        Write-Output "BRANCH: $($paths.CURRENT_BRANCH)"
        Write-Output "FEATURE_DIR: $($paths.FEATURE_DIR)"
        Write-Output "FEATURE_SPEC: $($paths.FEATURE_SPEC)"
        Write-Output "IMPL_PLAN: $($paths.IMPL_PLAN)"
        Write-Output "TASKS: $($paths.TASKS)"
    }
    exit 0
}

# Проверка обязательных директорий и файлов
if (-not (Test-Path $paths.FEATURE_DIR -PathType Container)) {
    Write-Output "ОШИБКА: Директория функциональности не найдена: $($paths.FEATURE_DIR)"
    Write-Output "Сначала запустите /speckit.specify, чтобы создать структуру функциональности."
    exit 1
}

if (-not (Test-Path $paths.IMPL_PLAN -PathType Leaf)) {
    Write-Output "ОШИБКА: plan.md не найден в $($paths.FEATURE_DIR)"
    Write-Output "Сначала запустите /speckit.plan, чтобы создать план реализации."
    exit 1
}

# Проверка tasks.md, если требуется
if ($RequireTasks -and -not (Test-Path $paths.TASKS -PathType Leaf)) {
    Write-Output "ОШИБКА: tasks.md не найден в $($paths.FEATURE_DIR)"
    Write-Output "Сначала запустите /speckit.tasks, чтобы создать список задач."
    exit 1
}

# Построение списка доступных документов
$docs = @()

# Всегда проверять эти необязательные документы
if (Test-Path $paths.RESEARCH) { $docs += 'research.md' }
if (Test-Path $paths.DATA_MODEL) { $docs += 'data-model.md' }

# Проверка директории contracts (только если она существует и содержит файлы)
if ((Test-Path $paths.CONTRACTS_DIR) -and (Get-ChildItem -Path $paths.CONTRACTS_DIR -ErrorAction SilentlyContinue | Select-Object -First 1)) { 
    $docs += 'contracts/' 
}

if (Test-Path $paths.QUICKSTART) { $docs += 'quickstart.md' }

# Включить tasks.md, если запрошено и файл существует
if ($IncludeTasks -and (Test-Path $paths.TASKS)) { 
    $docs += 'tasks.md' 
}

# Вывод результатов
if ($Json) {
    # Вывод в JSON
    [PSCustomObject]@{ 
        FEATURE_DIR = $paths.FEATURE_DIR
        AVAILABLE_DOCS = $docs 
    } | ConvertTo-Json -Compress
} else {
    # Текстовый вывод
    Write-Output "FEATURE_DIR:$($paths.FEATURE_DIR)"
    Write-Output "AVAILABLE_DOCS:"
    
    # Показать статус каждого потенциального документа
    Test-FileExists -Path $paths.RESEARCH -Description 'research.md' | Out-Null
    Test-FileExists -Path $paths.DATA_MODEL -Description 'data-model.md' | Out-Null
    Test-DirHasFiles -Path $paths.CONTRACTS_DIR -Description 'contracts/' | Out-Null
    Test-FileExists -Path $paths.QUICKSTART -Description 'quickstart.md' | Out-Null
    
    if ($IncludeTasks) {
        Test-FileExists -Path $paths.TASKS -Description 'tasks.md' | Out-Null
    }
}
