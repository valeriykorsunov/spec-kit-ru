#!/usr/bin/env pwsh
# Настройка плана реализации для функциональности

[CmdletBinding()]
param(
    [switch]$Json,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

# Показать справку по запросу
if ($Help) {
    Write-Output "Использование: ./setup-plan.ps1 [-Json] [-Help]"
    Write-Output "  -Json     Вывод результатов в формате JSON"
    Write-Output "  -Help     Показать это справочное сообщение"
    exit 0
}

# Загрузка общих функций
. "$PSScriptRoot/common.ps1"

# Получение всех путей и переменных из общих функций
$paths = Get-FeaturePathsEnv

# Проверка, находимся ли мы в правильной ветке функциональности (только для git-репозиториев)
if (-not (Test-FeatureBranch -Branch $paths.CURRENT_BRANCH -HasGit $paths.HAS_GIT)) { 
    exit 1 
}

# Убедиться, что директория функциональности существует
New-Item -ItemType Directory -Path $paths.FEATURE_DIR -Force | Out-Null

# Скопировать шаблон плана, если он существует, иначе сообщить об этом или создать пустой файл
$template = Join-Path $paths.REPO_ROOT '.specify/templates/plan-template.md'
if (Test-Path $template) { 
    Copy-Item $template $paths.IMPL_PLAN -Force
    Write-Output "Шаблон плана скопирован в $($paths.IMPL_PLAN)"
} else {
    Write-Warning "Шаблон плана не найден в $template"
    # Создать базовый файл плана, если шаблон не существует
    New-Item -ItemType File -Path $paths.IMPL_PLAN -Force | Out-Null
}

# Вывод результатов
if ($Json) {
    $result = [PSCustomObject]@{ 
        FEATURE_SPEC = $paths.FEATURE_SPEC
        IMPL_PLAN = $paths.IMPL_PLAN
        SPECS_DIR = $paths.FEATURE_DIR
        BRANCH = $paths.CURRENT_BRANCH
        HAS_GIT = $paths.HAS_GIT
    }
    $result | ConvertTo-Json -Compress
} else {
    Write-Output "FEATURE_SPEC: $($paths.FEATURE_SPEC)"
    Write-Output "IMPL_PLAN: $($paths.IMPL_PLAN)"
    Write-Output "SPECS_DIR: $($paths.FEATURE_DIR)"
    Write-Output "BRANCH: $($paths.CURRENT_BRANCH)"
    Write-Output "HAS_GIT: $($paths.HAS_GIT)"
}
