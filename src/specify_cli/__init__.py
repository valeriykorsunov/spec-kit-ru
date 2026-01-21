#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer",
#     "rich",
#     "platformdirs",
#     "readchar",
#     "httpx",
# ]
# ///
"""
Specify CLI - Инструмент настройки проектов Specify

Использование:
    uvx specify-cli.py init <имя-проекта>
    uvx specify-cli.py init .
    uvx specify-cli.py init --here

Или установка глобально:
    uv tool install --from specify-cli.py specify-cli
    specify init <имя-проекта>
    specify init .
    specify init --here
"""

import os
import subprocess
import sys
import zipfile
import tempfile
import shutil
import shlex
import json
import codecs
from pathlib import Path
from typing import Optional, Tuple

import typer
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich.table import Table
from rich.tree import Tree
from typer.core import TyperGroup

# Для кроссплатформенного ввода с клавиатуры
import readchar
import ssl
import truststore
from datetime import datetime, timezone

ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
client = httpx.Client(verify=ssl_context)

def _github_token(cli_token: str | None = None) -> str | None:
    """Возвращает очищенный токен GitHub (аргумент CLI имеет приоритет) или None."""
    return ((cli_token or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()) or None

def _github_auth_headers(cli_token: str | None = None) -> dict:
    """Возвращает словарь заголовков Authorization только если существует непустой токен."""
    token = _github_token(cli_token)
    return {"Authorization": f"Bearer {token}"} if token else {}

def _parse_rate_limit_headers(headers: httpx.Headers) -> dict:
    """Извлекает и парсит заголовки ограничения скорости GitHub."""
    info = {}
    
    # Стандартные заголовки ограничения скорости GitHub
    if "X-RateLimit-Limit" in headers:
        info["limit"] = headers.get("X-RateLimit-Limit")
    if "X-RateLimit-Remaining" in headers:
        info["remaining"] = headers.get("X-RateLimit-Remaining")
    if "X-RateLimit-Reset" in headers:
        reset_epoch = int(headers.get("X-RateLimit-Reset", "0"))
        if reset_epoch:
            reset_time = datetime.fromtimestamp(reset_epoch, tz=timezone.utc)
            info["reset_epoch"] = reset_epoch
            info["reset_time"] = reset_time
            info["reset_local"] = reset_time.astimezone()
    
    # Заголовок Retry-After (секунды или HTTP-дата)
    if "Retry-After" in headers:
        retry_after = headers.get("Retry-After")
        try:
            info["retry_after_seconds"] = int(retry_after)
        except ValueError:
            # Формат HTTP-date - не реализовано, просто сохраняем как строку
            info["retry_after"] = retry_after
    
    return info

def _format_rate_limit_error(status_code: int, headers: httpx.Headers, url: str) -> str:
    """Форматирует понятное сообщение об ошибке с информацией об ограничении скорости."""
    rate_info = _parse_rate_limit_headers(headers)
    
    lines = [f"GitHub API вернул статус {status_code} для {url}"]
    lines.append("")
    
    if rate_info:
        lines.append("[bold]Информация об ограничениях скорости:[/bold]")
        if "limit" in rate_info:
            lines.append(f"  • Лимит: {rate_info['limit']} запросов/час")
        if "remaining" in rate_info:
            lines.append(f"  • Осталось: {rate_info['remaining']}")
        if "reset_local" in rate_info:
            reset_str = rate_info["reset_local"].strftime("%Y-%m-%d %H:%M:%S %Z")
            lines.append(f"  • Сброс: {reset_str}")
        if "retry_after_seconds" in rate_info:
            lines.append(f"  • Повторить через: {rate_info['retry_after_seconds']} секунд")
        lines.append("")
    
    # Добавление советов по устранению неполадок
    lines.append("[bold]Советы по устранению неполадок:[/bold]")
    lines.append("  • Если вы находитесь в общей CI или корпоративной среде, вы можете быть ограничены.")
    lines.append("  • Подумайте об использовании токена GitHub через --github-token или переменную окружения")
    lines.append("    GH_TOKEN/GITHUB_TOKEN для увеличения лимитов.")
    lines.append("  • Аутентифицированные запросы имеют лимит 5,000/час против 60/час для неаутентифицированных.")
    
    return "\n".join(lines)

# Конфигурация агентов с именем, папкой, URL установки и требованием CLI инструмента
AGENT_CONFIG = {
    "copilot": {
        "name": "GitHub Copilot",
        "folder": ".github/",
        "install_url": None,  # IDE-based, проверка CLI не требуется
        "requires_cli": False,
    },
    "claude": {
        "name": "Claude Code",
        "folder": ".claude/",
        "install_url": "https://docs.anthropic.com/en/docs/claude-code/setup",
        "requires_cli": True,
    },
    "gemini": {
        "name": "Gemini CLI",
        "folder": ".gemini/",
        "install_url": "https://github.com/google-gemini/gemini-cli",
        "requires_cli": True,
    },
    "cursor-agent": {
        "name": "Cursor",
        "folder": ".cursor/",
        "install_url": None,  # IDE-based
        "requires_cli": False,
    },
    "qwen": {
        "name": "Qwen Code",
        "folder": ".qwen/",
        "install_url": "https://github.com/QwenLM/qwen-code",
        "requires_cli": True,
    },
    "opencode": {
        "name": "opencode",
        "folder": ".opencode/",
        "install_url": "https://opencode.ai",
        "requires_cli": True,
    },
    "codex": {
        "name": "Codex CLI",
        "folder": ".codex/",
        "install_url": "https://github.com/openai/codex",
        "requires_cli": True,
    },
    "windsurf": {
        "name": "Windsurf",
        "folder": ".windsurf/",
        "install_url": None,  # IDE-based
        "requires_cli": False,
    },
    "kilocode": {
        "name": "Kilo Code",
        "folder": ".kilocode/",
        "install_url": None,  # IDE-based
        "requires_cli": False,
    },
    "auggie": {
        "name": "Auggie CLI",
        "folder": ".augment/",
        "install_url": "https://docs.augmentcode.com/cli/setup-auggie/install-auggie-cli",
        "requires_cli": True,
    },
    "codebuddy": {
        "name": "CodeBuddy",
        "folder": ".codebuddy/",
        "install_url": "https://www.codebuddy.ai/cli",
        "requires_cli": True,
    },
    "qoder": {
        "name": "Qoder CLI",
        "folder": ".qoder/",
        "install_url": "https://qoder.com/cli",
        "requires_cli": True,
    },
    "roo": {
        "name": "Roo Code",
        "folder": ".roo/",
        "install_url": None,  # IDE-based
        "requires_cli": False,
    },
    "q": {
        "name": "Amazon Q Developer CLI",
        "folder": ".amazonq/",
        "install_url": "https://aws.amazon.com/developer/learning/q-developer-cli/",
        "requires_cli": True,
    },
    "amp": {
        "name": "Amp",
        "folder": ".agents/",
        "install_url": "https://ampcode.com/manual#install",
        "requires_cli": True,
    },
    "shai": {
        "name": "SHAI",
        "folder": ".shai/",
        "install_url": "https://github.com/ovh/shai",
        "requires_cli": True,
    },
    "bob": {
        "name": "IBM Bob",
        "folder": ".bob/",
        "install_url": None,  # IDE-based
        "requires_cli": False,
    },
}

SCRIPT_TYPE_CHOICES = {"sh": "POSIX Shell (bash/zsh)", "ps": "PowerShell"}

CLAUDE_LOCAL_PATH = Path.home() / ".claude" / "local" / "claude"

BANNER = """
███████╗██████╗ ███████╗ ██████╗██╗███████╗██╗   ██╗
██╔════╝██╔══██╗██╔════╝██╔════╝██║██╔════╝╚██╗ ██╔╝
███████╗██████╔╝█████╗  ██║     ██║█████╗   ╚████╔╝ 
╚════██║██╔═══╝ ██╔══╝  ██║     ██║██╔══╝    ╚██╔╝  
███████║██║     ███████╗╚██████╗██║██║        ██║   
╚══════╝╚═╝     ╚══════╝ ╚═════╝╚═╝╚═╝        ╚═╝   
"""

TAGLINE = "GitHub Spec Kit - Инструментарий разработки через спецификации"

class StepTracker:
    """Отслеживает и отображает иерархические шаги без эмодзи, аналогично выводу дерева Claude Code.
    Поддерживает живое автообновление через прикрепленный callback обновления.
    """
    def __init__(self, title: str):
        self.title = title
        self.steps = []  # список словарей: {key, label, status, detail}
        self.status_order = {"pending": 0, "running": 1, "done": 2, "error": 3, "skipped": 4}
        self._refresh_cb = None  # callable для запуска обновления UI

    def attach_refresh(self, cb):
        self._refresh_cb = cb

    def add(self, key: str, label: str):
        if key not in [s["key"] for s in self.steps]:
            self.steps.append({"key": key, "label": label, "status": "pending", "detail": ""})
            self._maybe_refresh()

    def start(self, key: str, detail: str = ""):
        self._update(key, status="running", detail=detail)

    def complete(self, key: str, detail: str = ""):
        self._update(key, status="done", detail=detail)

    def error(self, key: str, detail: str = ""):
        self._update(key, status="error", detail=detail)

    def skip(self, key: str, detail: str = ""):
        self._update(key, status="skipped", detail=detail)

    def _update(self, key: str, status: str, detail: str):
        for s in self.steps:
            if s["key"] == key:
                s["status"] = status
                if detail:
                    s["detail"] = detail
                self._maybe_refresh()
                return

        self.steps.append({"key": key, "label": key, "status": status, "detail": detail})
        self._maybe_refresh()

    def _maybe_refresh(self):
        if self._refresh_cb:
            try:
                self._refresh_cb()
            except Exception:
                pass

    def render(self):
        tree = Tree(f"[cyan]{self.title}[/cyan]", guide_style="grey50")
        for step in self.steps:
            label = step["label"]
            detail_text = step["detail"].strip() if step["detail"] else ""

            status = step["status"]
            if status == "done":
                symbol = "[green]●[/green]"
            elif status == "pending":
                symbol = "[green dim]○[/green dim]"
            elif status == "running":
                symbol = "[cyan]○[/cyan]"
            elif status == "error":
                symbol = "[red]●[/red]"
            elif status == "skipped":
                symbol = "[yellow]○[/yellow]"
            else:
                symbol = " "

            if status == "pending":
                # Вся строка светло-серая (pending)
                if detail_text:
                    line = f"{symbol} [bright_black]{label} ({detail_text})[/bright_black]"
                else:
                    line = f"{symbol} [bright_black]{label}[/bright_black]"
            else:
                # Метка белая, детали (если есть) светло-серые в скобках
                if detail_text:
                    line = f"{symbol} [white]{label}[/white] [bright_black]({detail_text})[/bright_black]"
                else:
                    line = f"{symbol} [white]{label}[/white]"

            tree.add(line)
        return tree

def get_key():
    """Получает одно нажатие клавиши кроссплатформенным способом используя readchar."""
    key = readchar.readkey()

    if key == readchar.key.UP or key == readchar.key.CTRL_P:
        return 'up'
    if key == readchar.key.DOWN or key == readchar.key.CTRL_N:
        return 'down'

    if key == readchar.key.ENTER:
        return 'enter'

    if key == readchar.key.ESC:
        return 'escape'

    if key == readchar.key.CTRL_C:
        raise KeyboardInterrupt

    return key

def select_with_arrows(options: dict, prompt_text: str = "Выберите опцию", default_key: str = None) -> str:
    """
    Интерактивный выбор с помощью стрелок с отображением через Rich Live.
    
    Args:
        options: Словарь с ключами опций и значениями описаний
        prompt_text: Текст для отображения над опциями
        default_key: Ключ опции по умолчанию
        
    Returns:
        Ключ выбранной опции
    """
    option_keys = list(options.keys())
    if default_key and default_key in option_keys:
        selected_index = option_keys.index(default_key)
    else:
        selected_index = 0

    selected_key = None

    def create_selection_panel():
        """Создает панель выбора с подсветкой текущего выбора."""
        table = Table.grid(padding=(0, 2))
        table.add_column(style="cyan", justify="left", width=3)
        table.add_column(style="white", justify="left")

        for i, key in enumerate(option_keys):
            if i == selected_index:
                table.add_row("▶", f"[cyan]{key}[/cyan] [dim]({options[key]})[/dim]")
            else:
                table.add_row(" ", f"[cyan]{key}[/cyan] [dim]({options[key]})[/dim]")

        table.add_row("", "")
        table.add_row("", "[dim]Используйте ↑/↓ для навигации, Enter для выбора, Esc для отмены[/dim]")

        return Panel(
            table,
            title=f"[bold]{prompt_text}[/bold]",
            border_style="cyan",
            padding=(1, 2)
        )

    console.print()

    def run_selection_loop():
        nonlocal selected_key, selected_index
        with Live(create_selection_panel(), console=console, transient=True, auto_refresh=False) as live:
            while True:
                try:
                    key = get_key()
                    if key == 'up':
                        selected_index = (selected_index - 1) % len(option_keys)
                    elif key == 'down':
                        selected_index = (selected_index + 1) % len(option_keys)
                    elif key == 'enter':
                        selected_key = option_keys[selected_index]
                        break
                    elif key == 'escape':
                        console.print("\n[yellow]Выбор отменен[/yellow]")
                        raise typer.Exit(1)

                    live.update(create_selection_panel(), refresh=True)

                except KeyboardInterrupt:
                    console.print("\n[yellow]Выбор отменен[/yellow]")
                    raise typer.Exit(1)

    run_selection_loop()

    if selected_key is None:
        console.print("\n[red]Выбор не удался.[/red]")
        raise typer.Exit(1)

    return selected_key

console = Console()

class BannerGroup(TyperGroup):
    """Пользовательская группа, показывающая баннер перед справкой."""

    def format_help(self, ctx, formatter):
        # Показать баннер перед справкой
        show_banner()
        super().format_help(ctx, formatter)


app = typer.Typer(
    name="specify",
    help="Инструмент настройки для проектов Specify (разработка через спецификации)",
    add_completion=False,
    invoke_without_command=True,
    cls=BannerGroup,
)

def show_banner():
    """Отображает ASCII арт баннер."""
    banner_lines = BANNER.strip().split('\n')
    colors = ["bright_blue", "blue", "cyan", "bright_cyan", "white", "bright_white"]

    styled_banner = Text()
    for i, line in enumerate(banner_lines):
        color = colors[i % len(colors)]
        styled_banner.append(line + "\n", style=color)

    console.print(Align.center(styled_banner))
    console.print(Align.center(Text(TAGLINE, style="italic bright_yellow")))
    console.print()

@app.callback()
def callback(ctx: typer.Context):
    """Показывает баннер, когда подкоманда не указана."""
    if ctx.invoked_subcommand is None and "--help" not in sys.argv and "-h" not in sys.argv:
        show_banner()
        console.print(Align.center("[dim]Запустите 'specify --help' для информации об использовании[/dim]"))
        console.print()

def run_command(cmd: list[str], check_return: bool = True, capture: bool = False, shell: bool = False) -> Optional[str]:
    """Запускает команду оболочки и опционально захватывает вывод."""
    try:
        if capture:
            result = subprocess.run(cmd, check=check_return, capture_output=True, text=True, shell=shell)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, check=check_return, shell=shell)
            return None
    except subprocess.CalledProcessError as e:
        if check_return:
            console.print(f"[red]Ошибка при выполнении команды:[/red] {' '.join(cmd)}")
            console.print(f"[red]Код выхода:[/red] {e.returncode}")
            if hasattr(e, 'stderr') and e.stderr:
                console.print(f"[red]Вывод ошибки:[/red] {e.stderr}")
            raise
        return None

def check_tool(tool: str, tracker: StepTracker = None) -> bool:
    """Проверяет, установлен ли инструмент. Опционально обновляет трекер.
    
    Args:
        tool: Имя инструмента для проверки
        tracker: Опциональный StepTracker для обновления результатов
        
    Returns:
        True если инструмент найден, False иначе
    """
    # Специальная обработка для Claude CLI после `claude migrate-installer`
    # См.: https://github.com/github/spec-kit/issues/123
    # Команда migrate-installer УДАЛЯЕТ оригинальный исполняемый файл из PATH
    # и создает алиас в ~/.claude/local/claude
    # Этот путь должен быть приоритетнее других исполняемых файлов claude в PATH
    if tool == "claude":
        if CLAUDE_LOCAL_PATH.exists() and CLAUDE_LOCAL_PATH.is_file():
            if tracker:
                tracker.complete(tool, "доступен")
            return True
    
    found = shutil.which(tool) is not None
    
    if tracker:
        if found:
            tracker.complete(tool, "доступен")
        else:
            tracker.error(tool, "не найден")
    
    return found

def is_git_repo(path: Path = None) -> bool:
    """Проверяет, находится ли указанный путь внутри git репозитория."""
    if path is None:
        path = Path.cwd()
    
    if not path.is_dir():
        return False

    try:
        # Использование команды git для проверки, находимся ли мы в рабочем дереве
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
            cwd=path,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def init_git_repo(project_path: Path, quiet: bool = False) -> Tuple[bool, Optional[str]]:
    """Инициализирует git репозиторий в указанном пути.
    
    Args:
        project_path: Путь для инициализации git репозитория
        quiet: если True, подавляет вывод в консоль (трекер обрабатывает статус)
    
    Returns:
        Кортеж из (успех: bool, сообщение_об_ошибке: Optional[str])
    """
    try:
        original_cwd = Path.cwd()
        os.chdir(project_path)
        if not quiet:
            console.print("[cyan]Инициализация git репозитория...[/cyan]")
        subprocess.run(["git", "init"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "Initial commit from Specify template"], check=True, capture_output=True, text=True)
        if not quiet:
            console.print("[green]✓[/green] Git репозиторий инициализирован")
        return True, None

    except subprocess.CalledProcessError as e:
        error_msg = f"Команда: {' '.join(e.cmd)}\nКод выхода: {e.returncode}"
        if e.stderr:
            error_msg += f"\nОшибка: {e.stderr.strip()}"
        elif e.stdout:
            error_msg += f"\nВывод: {e.stdout.strip()}"
        
        if not quiet:
            console.print(f"[red]Ошибка инициализации git репозитория:[/red] {e}")
        return False, error_msg
    finally:
        os.chdir(original_cwd)

def handle_vscode_settings(sub_item, dest_file, rel_path, verbose=False, tracker=None) -> None:
    """Обрабатывает слияние или копирование файлов .vscode/settings.json."""
    def log(message, color="green"):
        if verbose and not tracker:
            console.print(f"[{color}]{message}[/] {rel_path}")

    try:
        with open(sub_item, 'r', encoding='utf-8') as f:
            new_settings = json.load(f)

        if dest_file.exists():
            merged = merge_json_files(dest_file, new_settings, verbose=verbose and not tracker)
            with open(dest_file, 'w', encoding='utf-8') as f:
                json.dump(merged, f, indent=4)
                f.write('\n')
            log("Объединено:", "green")
        else:
            shutil.copy2(sub_item, dest_file)
            log("Скопировано (settings.json не существовал):", "blue")

    except Exception as e:
        log(f"Предупреждение: Не удалось объединить, копирование вместо этого: {e}", "yellow")
        shutil.copy2(sub_item, dest_file)

def merge_json_files(existing_path: Path, new_content: dict, verbose: bool = False) -> dict:
    """Объединяет новый JSON контент с существующим JSON файлом.

    Выполняет глубокое слияние, где:
    - Добавляются новые ключи
    - Существующие ключи сохраняются, если не перезаписаны новым контентом
    - Вложенные словари объединяются рекурсивно
    - Списки и другие значения заменяются (не объединяются)

    Args:
        existing_path: Путь к существующему JSON файлу
        new_content: Новый JSON контент для слияния
        verbose: Печатать ли детали слияния

    Returns:
        Объединенный JSON контент как словарь
    """
    try:
        with open(existing_path, 'r', encoding='utf-8') as f:
            existing_content = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Если файл не существует или некорректен, просто используем новый контент
        return new_content

    def deep_merge(base: dict, update: dict) -> dict:
        """Рекурсивно объединяет словарь update в словарь base."""
        result = base.copy()
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Рекурсивно объединяем вложенные словари
                result[key] = deep_merge(result[key], value)
            else:
                # Добавляем новый ключ или заменяем существующее значение
                result[key] = value
        return result

    merged = deep_merge(existing_content, new_content)

    if verbose:
        console.print(f"[cyan]JSON файл объединен:[/cyan] {existing_path.name}")

    return merged

def download_template_from_github(ai_assistant: str, download_dir: Path, *, script_type: str = "sh", verbose: bool = True, show_progress: bool = True, client: httpx.Client = None, debug: bool = False, github_token: str = None) -> Tuple[Path, dict]:
    repo_owner = "valeriykorsunov"
    repo_name = "spec-kit-ru"
    if client is None:
        client = httpx.Client(verify=ssl_context)

    if verbose:
        console.print("[cyan]Получение информации о последнем релизе...[/cyan]")
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"

    try:
        response = client.get(
            api_url,
            timeout=30,
            follow_redirects=True,
            headers=_github_auth_headers(github_token),
        )
        status = response.status_code
        if status != 200:
            # Форматируем подробное сообщение об ошибке с информацией о лимите
            error_msg = _format_rate_limit_error(status, response.headers, api_url)
            if debug:
                error_msg += f"\n\n[dim]Тело ответа (обрезано 500):[/dim]\n{response.text[:500]}"
            raise RuntimeError(error_msg)
        try:
            release_data = response.json()
        except ValueError as je:
            raise RuntimeError(f"Не удалось распарсить JSON релиза: {je}\nСырые данные (обрезано 400): {response.text[:400]}")
    except Exception as e:
        console.print(f"[red]Ошибка при получении информации о релизе[/red]")
        console.print(Panel(str(e), title="Ошибка получения", border_style="red"))
        raise typer.Exit(1)

    assets = release_data.get("assets", [])
    pattern = f"spec-kit-template-{ai_assistant}-{script_type}"
    matching_assets = [
        asset for asset in assets
        if pattern in asset["name"] and asset["name"].endswith(".zip")
    ]

    asset = matching_assets[0] if matching_assets else None

    if asset is None:
        console.print(f"[red]Не найден подходящий актив релиза[/red] для [bold]{ai_assistant}[/bold] (ожидаемый шаблон: [bold]{pattern}[/bold])")
        asset_names = [a.get('name', '?') for a in assets]
        console.print(Panel("\n".join(asset_names) or "(нет активов)", title="Доступные активы", border_style="yellow"))
        raise typer.Exit(1)

    download_url = asset["browser_download_url"]
    filename = asset["name"]
    file_size = asset["size"]

    if verbose:
        console.print(f"[cyan]Найден шаблон:[/cyan] {filename}")
        console.print(f"[cyan]Размер:[/cyan] {file_size:,} байт")
        console.print(f"[cyan]Релиз:[/cyan] {release_data['tag_name']}")

    zip_path = download_dir / filename
    if verbose:
        console.print(f"[cyan]Загрузка шаблона...[/cyan]")

    try:
        with client.stream(
            "GET",
            download_url,
            timeout=60,
            follow_redirects=True,
            headers=_github_auth_headers(github_token),
        ) as response:
            if response.status_code != 200:
                # Обработка ограничения скорости при загрузке
                error_msg = _format_rate_limit_error(response.status_code, response.headers, download_url)
                if debug:
                    error_msg += f"\n\n[dim]Тело ответа (обрезано 400):[/dim]\n{response.text[:400]}"
                raise RuntimeError(error_msg)
            total_size = int(response.headers.get('content-length', 0))
            with open(zip_path, 'wb') as f:
                if total_size == 0:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                else:
                    if show_progress:
                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                            console=console,
                        ) as progress:
                            task = progress.add_task("Загрузка...", total=total_size)
                            downloaded = 0
                            for chunk in response.iter_bytes(chunk_size=8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                progress.update(task, completed=downloaded)
                    else:
                        for chunk in response.iter_bytes(chunk_size=8192):
                            f.write(chunk)
    except Exception as e:
        console.print(f"[red]Ошибка загрузки шаблона[/red]")
        detail = str(e)
        if zip_path.exists():
            zip_path.unlink()
        console.print(Panel(detail, title="Ошибка загрузки", border_style="red"))
        raise typer.Exit(1)
    if verbose:
        console.print(f"Загружено: {filename}")
    metadata = {
        "filename": filename,
        "size": file_size,
        "release": release_data["tag_name"],
        "asset_url": download_url
    }
    return zip_path, metadata

def download_and_extract_template(project_path: Path, ai_assistant: str, script_type: str, is_current_dir: bool = False, *, verbose: bool = True, tracker: StepTracker | None = None, client: httpx.Client = None, debug: bool = False, github_token: str = None) -> Path:
    """Скачивает последний релиз и распаковывает его для создания нового проекта.
    Возвращает project_path. Использует трекер если предоставлен (ключи: fetch, download, extract, cleanup)
    """
    current_dir = Path.cwd()

    if tracker:
        tracker.start("fetch", "соединение с GitHub API")
    try:
        zip_path, meta = download_template_from_github(
            ai_assistant,
            current_dir,
            script_type=script_type,
            verbose=verbose and tracker is None,
            show_progress=(tracker is None),
            client=client,
            debug=debug,
            github_token=github_token
        )
        if tracker:
            tracker.complete("fetch", f"релиз {meta['release']} ({meta['size']:,} байт)")
            tracker.add("download", "Загрузка шаблона")
            tracker.complete("download", meta['filename'])
    except Exception as e:
        if tracker:
            tracker.error("fetch", str(e))
        else:
            if verbose:
                console.print(f"[red]Ошибка загрузки шаблона:[/red] {e}")
        raise

    if tracker:
        tracker.add("extract", "Распаковка шаблона")
        tracker.start("extract")
    elif verbose:
        console.print("Распаковка шаблона...")

    try:
        if not is_current_dir:
            project_path.mkdir(parents=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_contents = zip_ref.namelist()
            if tracker:
                tracker.start("zip-list")
                tracker.complete("zip-list", f"{len(zip_contents)} записей")
            elif verbose:
                console.print(f"[cyan]ZIP содержит {len(zip_contents)} элементов[/cyan]")

            if is_current_dir:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    zip_ref.extractall(temp_path)

                    extracted_items = list(temp_path.iterdir())
                    if tracker:
                        tracker.start("extracted-summary")
                        tracker.complete("extracted-summary", f"temp {len(extracted_items)} элементов")
                    elif verbose:
                        console.print(f"[cyan]Распаковано {len(extracted_items)} элементов во временную директорию[/cyan]")

                    source_dir = temp_path
                    if len(extracted_items) == 1 and extracted_items[0].is_dir():
                        source_dir = extracted_items[0]
                        if tracker:
                            tracker.add("flatten", "Выравнивание вложенной структуры")
                            tracker.complete("flatten")
                        elif verbose:
                            console.print(f"[cyan]Найдена вложенная структура директорий[/cyan]")

                    for item in source_dir.iterdir():
                        dest_path = project_path / item.name
                        if item.is_dir():
                            if dest_path.exists():
                                if verbose and not tracker:
                                    console.print(f"[yellow]Слияние директории:[/yellow] {item.name}")
                                for sub_item in item.rglob('*'):
                                    if sub_item.is_file():
                                        rel_path = sub_item.relative_to(item)
                                        dest_file = dest_path / rel_path
                                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                                        # Специальная обработка для .vscode/settings.json - слияние вместо перезаписи
                                        if dest_file.name == "settings.json" and dest_file.parent.name == ".vscode":
                                            handle_vscode_settings(sub_item, dest_file, rel_path, verbose, tracker)
                                        else:
                                            shutil.copy2(sub_item, dest_file)
                            else:
                                shutil.copytree(item, dest_path)
                        else:
                            if dest_path.exists() and verbose and not tracker:
                                console.print(f"[yellow]Перезапись файла:[/yellow] {item.name}")
                            shutil.copy2(item, dest_path)
                    if verbose and not tracker:
                        console.print(f"[cyan]Файлы шаблона объединены с текущей директорией[/cyan]")
            else:
                zip_ref.extractall(project_path)

                extracted_items = list(project_path.iterdir())
                if tracker:
                    tracker.start("extracted-summary")
                    tracker.complete("extracted-summary", f"{len(extracted_items)} элементов верхнего уровня")
                elif verbose:
                    console.print(f"[cyan]Распаковано {len(extracted_items)} элементов в {project_path}:[/cyan]")
                    for item in extracted_items:
                        console.print(f"  - {item.name} ({'папка' if item.is_dir() else 'файл'})")

                if len(extracted_items) == 1 and extracted_items[0].is_dir():
                    nested_dir = extracted_items[0]
                    temp_move_dir = project_path.parent / f"{project_path.name}_temp"

                    shutil.move(str(nested_dir), str(temp_move_dir))

                    project_path.rmdir()

                    shutil.move(str(temp_move_dir), str(project_path))
                    if tracker:
                        tracker.add("flatten", "Выравнивание вложенной структуры")
                        tracker.complete("flatten")
                    elif verbose:
                        console.print(f"[cyan]Выровнена вложенная структура директорий[/cyan]")

    except Exception as e:
        if tracker:
            tracker.error("extract", str(e))
        else:
            if verbose:
                console.print(f"[red]Ошибка распаковки шаблона:[/red] {e}")
                if debug:
                    console.print(Panel(str(e), title="Ошибка распаковки", border_style="red"))

        if not is_current_dir and project_path.exists():
            shutil.rmtree(project_path)
        raise typer.Exit(1)
    else:
        if tracker:
            tracker.complete("extract")
    finally:
        if tracker:
            tracker.add("cleanup", "Удаление временного архива")

        if zip_path.exists():
            zip_path.unlink()
            if tracker:
                tracker.complete("cleanup")
            elif verbose:
                console.print(f"Очищено: {zip_path.name}")

    if os.name == "nt" and script_type == "ps":
        ensure_powershell_scripts_utf8_bom(project_path, tracker=tracker)

    return project_path


def ensure_powershell_scripts_utf8_bom(project_path: Path, tracker: StepTracker | None = None) -> None:
    scripts_root = project_path / ".specify" / "scripts" / "powershell"
    if not scripts_root.is_dir():
        return

    if tracker:
        tracker.add("ps-encoding", "Кодировка PowerShell")
        tracker.start("ps-encoding")

    converted = 0
    for ps1_file in scripts_root.rglob("*.ps1"):
        data = ps1_file.read_bytes()
        if data.startswith(codecs.BOM_UTF8):
            continue

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue

        ps1_file.write_bytes(codecs.BOM_UTF8 + text.encode("utf-8"))
        converted += 1

    if tracker:
        tracker.complete("ps-encoding", f"обновлено: {converted}")


def ensure_executable_scripts(project_path: Path, tracker: StepTracker | None = None) -> None:
    """Гарантирует, что POSIX .sh скрипты в .specify/scripts (рекурсивно) имеют биты исполнения (no-op на Windows)."""
    if os.name == "nt":
        return  # Windows: пропускаем молча
    scripts_root = project_path / ".specify" / "scripts"
    if not scripts_root.is_dir():
        return
    failures: list[str] = []
    updated = 0
    for script in scripts_root.rglob("*.sh"):
        try:
            if script.is_symlink() or not script.is_file():
                continue
            try:
                with script.open("rb") as f:
                    if f.read(2) != b"#!":
                        continue
            except Exception:
                continue
            st = script.stat(); mode = st.st_mode
            if mode & 0o111:
                continue
            new_mode = mode
            if mode & 0o400: new_mode |= 0o100
            if mode & 0o040: new_mode |= 0o010
            if mode & 0o004: new_mode |= 0o001
            if not (new_mode & 0o100):
                new_mode |= 0o100
            os.chmod(script, new_mode)
            updated += 1
        except Exception as e:
            failures.append(f"{script.relative_to(scripts_root)}: {e}")
    if tracker:
        detail = f"{updated} обновлено" + (f", {len(failures)} сбоев" if failures else "")
        tracker.add("chmod", "Установка прав выполнения скриптов рекурсивно")
        (tracker.error if failures else tracker.complete)("chmod", detail)
    else:
        if updated:
            console.print(f"[cyan]Обновлены права выполнения на {updated} скриптах рекурсивно[/cyan]")
        if failures:
            console.print("[yellow]Некоторые скрипты не удалось обновить:[/yellow]")
            for f in failures:
                console.print(f"  - {f}")

@app.command()
def init(
    project_name: str = typer.Argument(None, help="Имя для директории вашего нового проекта (необязательно при использовании --here, или используйте '.' для текущей директории)"),
    ai_assistant: str = typer.Option(None, "--ai", help="AI ассистент для использования: claude, gemini, copilot, cursor-agent, qwen, opencode, codex, windsurf, kilocode, auggie, codebuddy, amp, shai, q, bob, или qoder "),
    script_type: str = typer.Option(None, "--script", help="Тип скрипта: sh или ps"),
    ignore_agent_tools: bool = typer.Option(False, "--ignore-agent-tools", help="Пропустить проверку инструментов AI агентов, например Claude Code"),
    no_git: bool = typer.Option(False, "--no-git", help="Пропустить инициализацию git репозитория"),
    here: bool = typer.Option(False, "--here", help="Инициализировать проект в текущей директории вместо создания новой"),
    force: bool = typer.Option(False, "--force", help="Принудительное слияние/перезапись при использовании --here (пропуск подтверждения)"),
    skip_tls: bool = typer.Option(False, "--skip-tls", help="Пропустить проверку SSL/TLS (не рекомендуется)"),
    debug: bool = typer.Option(False, "--debug", help="Показать подробный диагностический вывод для сетевых сбоев и ошибок распаковки"),
    github_token: str = typer.Option(None, "--github-token", help="Токен GitHub для запросов API (или установите переменную окружения GH_TOKEN или GITHUB_TOKEN)"),
):
    """
    Инициализация нового проекта Specify из последнего шаблона.
    
    Эта команда:
    1. Проверит наличие необходимых инструментов (git опционален)
    2. Позволит выбрать вашего AI ассистента
    3. Скачает соответствующий шаблон с GitHub
    4. Распакует шаблон в новую директорию проекта или текущую директорию
    5. Инициализирует свежий git репозиторий (если не указано --no-git и нет существующего репо)
    6. Опционально настроит команды AI ассистента
    
    Примеры:
        specify init my-project
        specify init my-project --ai claude
        specify init my-project --ai copilot --no-git
        specify init --ignore-agent-tools my-project
        specify init . --ai claude         # Инициализация в текущей директории
        specify init .                     # Инициализация в текущей директории (интерактивный выбор AI)
        specify init --here --ai claude    # Альтернативный синтаксис для текущей директории
        specify init --here --ai codex
        specify init --here --ai codebuddy
        specify init --here
        specify init --here --force  # Пропуск подтверждения, если текущая директория не пуста
    """

    show_banner()

    if project_name == ".":
        here = True
        project_name = None  # Очищаем project_name для использования существующей логики валидации

    if here and project_name:
        console.print("[red]Ошибка:[/red] Нельзя указать имя проекта и флаг --here одновременно")
        raise typer.Exit(1)

    if not here and not project_name:
        console.print("[red]Ошибка:[/red] Необходимо указать имя проекта, использовать '.' для текущей директории или использовать флаг --here")
        raise typer.Exit(1)

    if here:
        project_name = Path.cwd().name
        project_path = Path.cwd()

        existing_items = list(project_path.iterdir())
        if existing_items:
            console.print(f"[yellow]Предупреждение:[/yellow] Текущая директория не пуста ({len(existing_items)} элементов)")
            console.print("[yellow]Файлы шаблона будут объединены с существующим контентом и могут перезаписать существующие файлы[/yellow]")
            if force:
                console.print("[cyan]--force указан: пропуск подтверждения и выполнение слияния[/cyan]")
            else:
                response = typer.confirm("Вы хотите продолжить?")
                if not response:
                    console.print("[yellow]Операция отменена[/yellow]")
                    raise typer.Exit(0)
    else:
        project_path = Path(project_name).resolve()
        if project_path.exists():
            error_panel = Panel(
                f"Директория '[cyan]{project_name}[/cyan]' уже существует\n"
                "Пожалуйста, выберите другое имя проекта или удалите существующую директорию.",
                title="[red]Конфликт директорий[/red]",
                border_style="red",
                padding=(1, 2)
            )
            console.print()
            console.print(error_panel)
            raise typer.Exit(1)

    current_dir = Path.cwd()

    setup_lines = [
        "[cyan]Настройка проекта Specify[/cyan]",
        "",
        f"{'Проект':<15} [green]{project_path.name}[/green]",
        f"{'Рабочий путь':<15} [dim]{current_dir}[/dim]",
    ]

    if not here:
        setup_lines.append(f"{'Целевой путь':<15} [dim]{project_path}[/dim]")

    console.print(Panel("\n".join(setup_lines), border_style="cyan", padding=(1, 2)))

    should_init_git = False
    if not no_git:
        should_init_git = check_tool("git")
        if not should_init_git:
            console.print("[yellow]Git не найден - инициализация репозитория будет пропущена[/yellow]")

    if ai_assistant:
        if ai_assistant not in AGENT_CONFIG:
            console.print(f"[red]Ошибка:[/red] Неверный AI ассистент '{ai_assistant}'. Выберите из: {', '.join(AGENT_CONFIG.keys())}")
            raise typer.Exit(1)
        selected_ai = ai_assistant
    else:
        # Создание словаря опций для выбора (agent_key: display_name)
        ai_choices = {key: config["name"] for key, config in AGENT_CONFIG.items()}
        selected_ai = select_with_arrows(
            ai_choices, 
            "Выберите вашего AI ассистента:", 
            "copilot"
        )

    if not ignore_agent_tools:
        agent_config = AGENT_CONFIG.get(selected_ai)
        if agent_config and agent_config["requires_cli"]:
            install_url = agent_config["install_url"]
            if not check_tool(selected_ai):
                error_panel = Panel(
                    f"[cyan]{selected_ai}[/cyan] не найден\n"
                    f"Установите с: [cyan]{install_url}[/cyan]\n"
                    f"{agent_config['name']} требуется для продолжения с этим типом проекта.\n\n"
                    "Совет: Используйте [cyan]--ignore-agent-tools[/cyan] для пропуска этой проверки",
                    title="[red]Ошибка обнаружения агента[/red]",
                    border_style="red",
                    padding=(1, 2)
                )
                console.print()
                console.print(error_panel)
                raise typer.Exit(1)

    if script_type:
        if script_type not in SCRIPT_TYPE_CHOICES:
            console.print(f"[red]Ошибка:[/red] Неверный тип скрипта '{script_type}'. Выберите из: {', '.join(SCRIPT_TYPE_CHOICES.keys())}")
            raise typer.Exit(1)
        selected_script = script_type
    else:
        default_script = "ps" if os.name == "nt" else "sh"

        if sys.stdin.isatty():
            selected_script = select_with_arrows(SCRIPT_TYPE_CHOICES, "Выберите тип скрипта (или нажмите Enter)", default_script)
        else:
            selected_script = default_script

    console.print(f"[cyan]Выбранный AI ассистент:[/cyan] {selected_ai}")
    console.print(f"[cyan]Выбранный тип скрипта:[/cyan] {selected_script}")

    tracker = StepTracker("Инициализация проекта Specify")

    sys._specify_tracker_active = True

    tracker.add("precheck", "Проверка необходимых инструментов")
    tracker.complete("precheck", "ок")
    tracker.add("ai-select", "Выбор AI ассистента")
    tracker.complete("ai-select", f"{selected_ai}")
    tracker.add("script-select", "Выбор типа скрипта")
    tracker.complete("script-select", selected_script)
    for key, label in [
        ("fetch", "Получение последнего релиза"),
        ("download", "Загрузка шаблона"),
        ("extract", "Распаковка шаблона"),
        ("zip-list", "Содержимое архива"),
        ("extracted-summary", "Сводка распаковки"),
        ("chmod", "Права выполнения скриптов"),
        ("cleanup", "Очистка"),
        ("git", "Инициализация git репозитория"),
        ("final", "Финализация")
    ]:
        tracker.add(key, label)

    # Отслеживание сообщения об ошибке git вне контекста Live, чтобы оно сохранилось
    git_error_message = None

    with Live(tracker.render(), console=console, refresh_per_second=8, transient=True) as live:
        tracker.attach_refresh(lambda: live.update(tracker.render()))
        try:
            verify = not skip_tls
            local_ssl_context = ssl_context if verify else False
            local_client = httpx.Client(verify=local_ssl_context)

            download_and_extract_template(project_path, selected_ai, selected_script, here, verbose=False, tracker=tracker, client=local_client, debug=debug, github_token=github_token)

            ensure_executable_scripts(project_path, tracker=tracker)

            if not no_git:
                tracker.start("git")
                if is_git_repo(project_path):
                    tracker.complete("git", "существующий репо обнаружен")
                elif should_init_git:
                    success, error_msg = init_git_repo(project_path, quiet=True)
                    if success:
                        tracker.complete("git", "инициализирован")
                    else:
                        tracker.error("git", "ошибка инициализации")
                        git_error_message = error_msg
                else:
                    tracker.skip("git", "git недоступен")
            else:
                tracker.skip("git", "флаг --no-git")

            tracker.complete("final", "проект готов")
        except Exception as e:
            tracker.error("final", str(e))
            console.print(Panel(f"Инициализация не удалась: {e}", title="Сбой", border_style="red"))
            if debug:
                _env_pairs = [
                    ("Python", sys.version.split()[0]),
                    ("Platform", sys.platform),
                    ("CWD", str(Path.cwd())),
                ]
                _label_width = max(len(k) for k, _ in _env_pairs)
                env_lines = [f"{k.ljust(_label_width)} → [bright_black]{v}[/bright_black]" for k, v in _env_pairs]
                console.print(Panel("\n".join(env_lines), title="Среда отладки", border_style="magenta"))
            if not here and project_path.exists():
                shutil.rmtree(project_path)
            raise typer.Exit(1)
        finally:
            pass

    console.print(tracker.render())
    console.print("\n[bold green]Проект готов.[/bold green]")
    
    # Показать детали ошибки git, если инициализация не удалась
    if git_error_message:
        console.print()
        git_error_panel = Panel(
            f"[yellow]Предупреждение:[/yellow] Инициализация Git репозитория не удалась\n\n"
            f"{git_error_message}\n\n"
            f"[dim]Вы можете инициализировать git вручную позже с помощью:[/dim]\n"
            f"[cyan]cd {project_path if not here else '.'}[/cyan]\n"
            f"[cyan]git init[/cyan]\n"
            f"[cyan]git add .[/cyan]\n"
            f"[cyan]git commit -m \"Initial commit\"[/cyan]",
            title="[red]Сбой инициализации Git[/red]",
            border_style="red",
            padding=(1, 2)
        )
        console.print(git_error_panel)

    # Уведомление о безопасности папки агента
    agent_config = AGENT_CONFIG.get(selected_ai)
    if agent_config:
        agent_folder = agent_config["folder"]
        security_notice = Panel(
            f"Некоторые агенты могут хранить учетные данные, токены авторизации или другие личные артефакты в папке агента внутри вашего проекта.\n"
            f"Подумайте о добавлении [cyan]{agent_folder}[/cyan] (или его частей) в [cyan].gitignore[/cyan], чтобы предотвратить случайную утечку учетных данных.",
            title="[yellow]Безопасность папки агента[/yellow]",
            border_style="yellow",
            padding=(1, 2)
        )
        console.print()
        console.print(security_notice)

    steps_lines = []
    if not here:
        steps_lines.append(f"1. Перейдите в папку проекта: [cyan]cd {project_name}[/cyan]")
        step_num = 2
    else:
        steps_lines.append("1. Вы уже в директории проекта!")
        step_num = 2

    # Добавление шага настройки Codex, если необходимо
    if selected_ai == "codex":
        codex_path = project_path / ".codex"
        quoted_path = shlex.quote(str(codex_path))
        if os.name == "nt":  # Windows
            cmd = f"setx CODEX_HOME {quoted_path}"
        else:  # Unix-like системы
            cmd = f"export CODEX_HOME={quoted_path}"
        
        steps_lines.append(f"{step_num}. Установите переменную окружения [cyan]CODEX_HOME[/cyan] перед запуском Codex: [cyan]{cmd}[/cyan]")
        step_num += 1

    steps_lines.append(f"{step_num}. Начните использовать слэш-команды с вашим AI агентом:")

    steps_lines.append("   2.1 [cyan]/speckit.constitution[/] - Установить принципы проекта")
    steps_lines.append("   2.2 [cyan]/speckit.specify[/] - Создать базовую спецификацию")
    steps_lines.append("   2.3 [cyan]/speckit.plan[/] - Создать план реализации")
    steps_lines.append("   2.4 [cyan]/speckit.tasks[/] - Сгенерировать задачи к действию")
    steps_lines.append("   2.5 [cyan]/speckit.implement[/] - Выполнить реализацию")

    steps_panel = Panel("\n".join(steps_lines), title="Следующие шаги", border_style="cyan", padding=(1,2))
    console.print()
    console.print(steps_panel)

    enhancement_lines = [
        "Опциональные команды, которые вы можете использовать для ваших спецификаций [bright_black](улучшение качества и уверенности)[/bright_black]",
        "",
        f"○ [cyan]/speckit.clarify[/] [bright_black](опционально)[/bright_black] - Задать структурированные вопросы для устранения рисков в неоднозначных областях перед планированием (запустите перед [cyan]/speckit.plan[/], если используется)",
        f"○ [cyan]/speckit.analyze[/] [bright_black](опционально)[/bright_black] - Отчет о согласованности и выравнивании артефактов (после [cyan]/speckit.tasks[/], перед [cyan]/speckit.implement[/])",
        f"○ [cyan]/speckit.checklist[/] [bright_black](опционально)[/bright_black] - Сгенерировать чеклисты качества для валидации полноты, ясности и согласованности требований (после [cyan]/speckit.plan[/])"
    ]
    enhancements_panel = Panel("\n".join(enhancement_lines), title="Команды улучшения", border_style="cyan", padding=(1,2))
    console.print()
    console.print(enhancements_panel)

@app.command()
def check():
    """Проверка установки всех необходимых инструментов."""
    show_banner()
    console.print("[bold]Проверка установленных инструментов...[/bold]\n")

    tracker = StepTracker("Проверка доступных инструментов")

    tracker.add("git", "Управление версиями Git")
    git_ok = check_tool("git", tracker=tracker)

    agent_results = {}
    for agent_key, agent_config in AGENT_CONFIG.items():
        agent_name = agent_config["name"]
        requires_cli = agent_config["requires_cli"]

        tracker.add(agent_key, agent_name)

        if requires_cli:
            agent_results[agent_key] = check_tool(agent_key, tracker=tracker)
        else:
            # IDE-based agent - пропускаем проверку CLI и помечаем как опциональный
            tracker.skip(agent_key, "IDE-based, проверка CLI не требуется")
            agent_results[agent_key] = False  # Не считаем IDE агентов как "найденные"

    # Проверка вариантов VS Code (нет в конфиге агентов)
    tracker.add("code", "Visual Studio Code")
    code_ok = check_tool("code", tracker=tracker)

    tracker.add("code-insiders", "Visual Studio Code Insiders")
    code_insiders_ok = check_tool("code-insiders", tracker=tracker)

    console.print(tracker.render())

    console.print("\n[bold green]Specify CLI готов к использованию![/bold green]")

    if not git_ok:
        console.print("[dim]Совет: Установите git для управления репозиторием[/dim]")

    if not any(agent_results.values()):
        console.print("[dim]Совет: Установите AI ассистента для лучшего опыта[/dim]")

@app.command()
def version():
    """Отображение версии и системной информации."""
    import platform
    import importlib.metadata
    
    show_banner()
    
    # Получение версии CLI из метаданных пакета
    cli_version = "unknown"
    try:
        cli_version = importlib.metadata.version("specify-cli")
    except Exception:
        # Fallback: попытка чтения из pyproject.toml при запуске из исходников
        try:
            import tomllib
            pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    data = tomllib.load(f)
                    cli_version = data.get("project", {}).get("version", "unknown")
        except Exception:
            pass
    
    # Получение версии последнего релиза шаблона
    repo_owner = "github"
    repo_name = "spec-kit"
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
    
    template_version = "unknown"
    release_date = "unknown"
    
    try:
        response = client.get(
            api_url,
            timeout=10,
            follow_redirects=True,
            headers=_github_auth_headers(),
        )
        if response.status_code == 200:
            release_data = response.json()
            template_version = release_data.get("tag_name", "unknown")
            # Удаление префикса 'v' если есть
            if template_version.startswith("v"):
                template_version = template_version[1:]
            release_date = release_data.get("published_at", "unknown")
            if release_date != "unknown":
                # Красивое форматирование даты
                try:
                    dt = datetime.fromisoformat(release_date.replace('Z', '+00:00'))
                    release_date = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass
    except Exception:
        pass

    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column("Key", style="cyan", justify="right")
    info_table.add_column("Value", style="white")

    info_table.add_row("Версия CLI", cli_version)
    info_table.add_row("Версия шаблона", template_version)
    info_table.add_row("Выпущен", release_date)
    info_table.add_row("", "")
    info_table.add_row("Python", platform.python_version())
    info_table.add_row("Платформа", platform.system())
    info_table.add_row("Архитектура", platform.machine())
    info_table.add_row("Версия ОС", platform.version())

    panel = Panel(
        info_table,
        title="[bold cyan]Информация Specify CLI[/bold cyan]",
        border_style="cyan",
        padding=(1, 2)
    )

    console.print(panel)
    console.print()

def main():
    app()

if __name__ == "__main__":
    main()
