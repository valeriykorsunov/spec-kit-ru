#!/usr/bin/env pwsh
# Создание новой функциональности
[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ShortName,
    [int]$Number = 0,
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$FeatureDescription
)
$ErrorActionPreference = 'Stop'

# Показать справку по запросу
if ($Help) {
    Write-Host "Использование: ./create-new-feature.ps1 [-Json] [-ShortName <имя>] [-Number N] <описание функциональности>"
    Write-Host ""
    Write-Host "Опции:"
    Write-Host "  -Json               Вывод в формате JSON"
    Write-Host "  -ShortName <имя>    Указать короткое имя (2-4 слова) для ветки вручную"
    Write-Host "  -Number N           Указать номер ветки вручную (переопределяет автоопределение)"
    Write-Host "  -Help               Показать это справочное сообщение"
    Write-Host ""
    Write-Host "Примеры:"
    Write-Host "  ./create-new-feature.ps1 'Add user authentication system' -ShortName 'user-auth'"
    Write-Host "  ./create-new-feature.ps1 'Implement OAuth2 integration for API'"
    Write-Host "  (Примечание: для автоматической генерации имени ветки рекомендуется использовать английское описание)"
    exit 0
}

# Проверка, предоставлено ли описание функциональности
if (-not $FeatureDescription -or $FeatureDescription.Count -eq 0) {
    Write-Error "Использование: ./create-new-feature.ps1 [-Json] [-ShortName <имя>] <описание функциональности>"
    exit 1
}

$featureDesc = ($FeatureDescription -join ' ').Trim()

# Определение корня репозитория. Предпочитаем информацию git, но используем запасной вариант
# поиска маркеров репозитория, чтобы рабочий процесс работал в репозиториях,
# инициализированных с --no-git.
function Find-RepositoryRoot {
    param(
        [string]$StartDir,
        [string[]]$Markers = @('.git', '.specify')
    )
    $current = Resolve-Path $StartDir
    while ($true) {
        foreach ($marker in $Markers) {
            if (Test-Path (Join-Path $current $marker)) {
                return $current
            }
        }
        $parent = Split-Path $current -Parent
        if ($parent -eq $current) {
            # Достигнут корень файловой системы, маркеры не найдены
            return $null
        }
        $current = $parent
    }
}

function Get-HighestNumberFromSpecs {
    param([string]$SpecsDir)
    
    $highest = 0
    if (Test-Path $SpecsDir) {
        Get-ChildItem -Path $SpecsDir -Directory | ForEach-Object {
            if ($_.Name -match '^(\d+)') {
                $num = [int]$matches[1]
                if ($num -gt $highest) { $highest = $num }
            }
        }
    }
    return $highest
}

function Get-HighestNumberFromBranches {
    param()
    
    $highest = 0
    try {
        $branches = git branch -a 2>$null
        if ($LASTEXITCODE -eq 0) {
            foreach ($branch in $branches) {
                # Очистка имени ветки: удаление ведущих маркеров и префиксов удаленных репозиториев
                $cleanBranch = $branch.Trim() -replace '^\*?\s+', '' -replace '^remotes/[^/]+/', ''
                
                # Извлечение номера функциональности, если ветка соответствует шаблону ###-*
                if ($cleanBranch -match '^(\d+)-') {
                    $num = [int]$matches[1]
                    if ($num -gt $highest) { $highest = $num }
                }
            }
        }
    } catch {
        # Если команда git не удалась, вернуть 0
        Write-Verbose "Не удалось проверить ветки Git: $_"
    }
    return $highest
}

function Get-NextBranchNumber {
    param(
        [string]$SpecsDir
    )

    # Получить все удаленные ветки для актуальной информации (подавить ошибки, если нет удаленных репозиториев)
    try {
        git fetch --all --prune 2>$null | Out-Null
    } catch {
        # Игнорировать ошибки fetch
    }

    # Получить максимальный номер из ВСЕХ веток
    $highestBranch = Get-HighestNumberFromBranches

    # Получить максимальный номер из ВСЕХ спецификаций
    $highestSpec = Get-HighestNumberFromSpecs -SpecsDir $SpecsDir

    # Взять максимум из обоих
    $maxNum = [Math]::Max($highestBranch, $highestSpec)

    # Вернуть следующий номер
    return $maxNum + 1
}

function ConvertTo-CleanBranchName {
    param([string]$Name)
    
    return $Name.ToLower() -replace '[^a-z0-9]', '-' -replace '-{2,}', '-' -replace '^-', '' -replace '-$', ''
}
$fallbackRoot = (Find-RepositoryRoot -StartDir $PSScriptRoot)
if (-not $fallbackRoot) {
    Write-Error "Ошибка: Не удалось определить корень репозитория. Пожалуйста, запустите этот скрипт из репозитория."
    exit 1
}

try {
    $repoRoot = git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0) {
        $hasGit = $true
    } else {
        throw "Git недоступен"
    }
} catch {
    $repoRoot = $fallbackRoot
    $hasGit = $false
}

Set-Location $repoRoot

$specsDir = Join-Path $repoRoot 'specs'
New-Item -ItemType Directory -Path $specsDir -Force | Out-Null

# Функция для генерации имени ветки с фильтрацией стоп-слов и длины
function Get-BranchName {
    param([string]$Description)
    
    # Общие стоп-слова для фильтрации (оставляем английские, так как генерация ориентирована на английский)
    $stopWords = @(
        'i', 'a', 'an', 'the', 'to', 'for', 'of', 'in', 'on', 'at', 'by', 'with', 'from',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must', 'shall',
        'this', 'that', 'these', 'those', 'my', 'your', 'our', 'their',
        'want', 'need', 'add', 'get', 'set'
    )
    
    # Преобразовать в нижний регистр и извлечь слова (только буквенно-цифровые)
    $cleanName = $Description.ToLower() -replace '[^a-z0-9\s]', ' '
    $words = $cleanName -split '\s+' | Where-Object { $_ }
    
    # Фильтрация слов: удалить стоп-слова и слова короче 3 символов (если они не были аббревиатурами)
    $meaningfulWords = @()
    foreach ($word in $words) {
        # Пропустить стоп-слова
        if ($stopWords -contains $word) { continue }
        
        # Оставить слова длиной >= 3 ИЛИ если они были в верхнем регистре в оригинале (вероятно, аббревиатуры)
        if ($word.Length -ge 3) {
            $meaningfulWords += $word
        } elseif ($Description -match "\b$($word.ToUpper())\b") {
            # Оставить короткие слова, если они были в верхнем регистре (вероятно, аббревиатуры)
            $meaningfulWords += $word
        }
    }
    
    # Если есть значимые слова, использовать первые 3-4 из них
    if ($meaningfulWords.Count -gt 0) {
        $maxWords = if ($meaningfulWords.Count -eq 4) { 4 } else { 3 }
        $result = ($meaningfulWords | Select-Object -First $maxWords) -join '-'
        return $result
    } else {
        # Запасной вариант, если значимые слова не найдены
        $result = ConvertTo-CleanBranchName -Name $Description
        $fallbackWords = ($result -split '-') | Where-Object { $_ } | Select-Object -First 3
        return [string]::Join('-', $fallbackWords)
    }
}

# Генерация имени ветки
if ($ShortName) {
    # Использовать предоставленное короткое имя, просто очистить его
    $branchSuffix = ConvertTo-CleanBranchName -Name $ShortName
} else {
    # Сгенерировать из описания с умной фильтрацией
    $branchSuffix = Get-BranchName -Description $featureDesc
}

# Определение номера ветки
if ($Number -eq 0) {
    if ($hasGit) {
        # Проверить существующие ветки на удаленных репозиториях
        $Number = Get-NextBranchNumber -SpecsDir $specsDir
    } else {
        # Вернуться к проверке локальной директории
        $Number = (Get-HighestNumberFromSpecs -SpecsDir $specsDir) + 1
    }
}

$featureNum = ('{0:000}' -f $Number)
$branchName = "$featureNum-$branchSuffix"

# GitHub устанавливает ограничение в 244 байта на имена веток
# Проверить и обрезать при необходимости
$maxBranchLength = 244
if ($branchName.Length -gt $maxBranchLength) {
    # Рассчитать, сколько нужно обрезать от суффикса
    # Учесть: номер функциональности (3) + дефис (1) = 4 символа
    $maxSuffixLength = $maxBranchLength - 4
    
    # Обрезать суффикс
    $truncatedSuffix = $branchSuffix.Substring(0, [Math]::Min($branchSuffix.Length, $maxSuffixLength))
    # Удалить завершающий дефис, если обрезка его создала
    $truncatedSuffix = $truncatedSuffix -replace '-$', ''
    
    $originalBranchName = $branchName
    $branchName = "$featureNum-$truncatedSuffix"
    
    Write-Warning "[specify] Имя ветки превысило лимит GitHub в 244 байта"
    Write-Warning "[specify] Оригинал: $originalBranchName ($($originalBranchName.Length) байт)"
    Write-Warning "[specify] Обрезано до: $branchName ($($branchName.Length) байт)"
}

if ($hasGit) {
    try {
        git checkout -b $branchName | Out-Null
    } catch {
        Write-Warning "Не удалось создать git-ветку: $branchName"
    }
} else {
    Write-Warning "[specify] Внимание: Git-репозиторий не обнаружен; создание ветки для $branchName пропущено"
}

$featureDir = Join-Path $specsDir $branchName
New-Item -ItemType Directory -Path $featureDir -Force | Out-Null

$template = Join-Path $repoRoot '.specify/templates/spec-template.md'
$specFile = Join-Path $featureDir 'spec.md'
if (Test-Path $template) { 
    Copy-Item $template $specFile -Force 
} else { 
    New-Item -ItemType File -Path $specFile | Out-Null 
}

# Установить переменную окружения SPECIFY_FEATURE для текущей сессии
$env:SPECIFY_FEATURE = $branchName

if ($Json) {
    $obj = [PSCustomObject]@{ 
        BRANCH_NAME = $branchName
        SPEC_FILE = $specFile
        FEATURE_NUM = $featureNum
        HAS_GIT = $hasGit
    }
    $obj | ConvertTo-Json -Compress
} else {
    Write-Output "BRANCH_NAME: $branchName"
    Write-Output "SPEC_FILE: $specFile"
    Write-Output "FEATURE_NUM: $featureNum"
    Write-Output "HAS_GIT: $hasGit"
    Write-Output "Переменная окружения SPECIFY_FEATURE установлена в: $branchName"
}
