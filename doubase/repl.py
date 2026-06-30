"""DouBase 交互式 REPL — 直接对话模式，支持 / 命令。"""

import shlex
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from doubase.config import load_config
from doubase.pipeline import run_ingest, run_ask, run_analyze

console = Console(highlight=False)

IDLE_HINT_INTERVAL = 30  # 闲置多少秒后显示提示

HELP_TEXT = """[bold]可用命令:[/bold]
  直接输入问题即可向知识库提问
  [cyan]/ingest <路径>[/cyan]      导入文档到知识库
  [cyan]/ingest --watch <目录>[/cyan] 监控目录自动导入
  [cyan]/analyze <项目路径>[/cyan]  分析代码项目并入库
  [cyan]/analyze <路径> --focus <子目录>[/cyan]
  [cyan]/help[/cyan]              显示此帮助
  [cyan]/exit[/cyan]              退出"""

HINT_TEXT = "[dim]💡 直接输入问题即可提问 | /ingest 导入 | /analyze 分析 | /help 帮助 | /exit 退出[/dim]"

PROMPT = "[bold green]\n›[/bold green] "


def _make_welcome() -> Panel:
    """构建欢迎面板（Rich 自动处理中文/emoji 对齐）。"""
    content = Text.from_markup(
        "直接输入问题，或用 [cyan]/[/cyan] 命令操作\n"
        "输入 [cyan]/help[/cyan] 查看可用命令"
    )
    return Panel(content, title="🧠 DouBase REPL", border_style="bold")


_last_input_time = 0.0
_hint_shown = False


def _touch_activity():
    global _last_input_time, _hint_shown
    _last_input_time = time.time()
    _hint_shown = False


def _check_idle_hint():
    """两次输入之间闲置超时则显示提示（不干扰用户打字）。"""
    global _hint_shown
    if not _hint_shown and time.time() - _last_input_time >= IDLE_HINT_INTERVAL:
        _hint_shown = True
        console.print(HINT_TEXT)


def _parse_command(text: str) -> tuple[str | None, str]:
    """返回 (command, args_string)。command 为 None 表示纯文本提问。"""
    text = text.strip()
    if not text:
        return None, ""

    if text.startswith("/"):
        parts = shlex.split(text)
        cmd = parts[0][1:]
        if len(parts) > 1:
            return cmd, text[len(cmd) + 2:].strip()
        return cmd, ""
    else:
        return None, text


def _handle_command(cmd: str, args: str, config: dict) -> bool:
    """处理一条 / 命令。返回 False 表示退出 REPL。"""
    if cmd == "exit" or cmd == "quit":
        console.print("[dim]再见！[/dim]")
        return False

    elif cmd == "help":
        console.print(HELP_TEXT)

    elif cmd == "ingest":
        if not args:
            console.print("[yellow]用法: /ingest <文件或目录路径> [--watch] [--yes][/yellow]")
            return True
        try:
            parse_args = shlex.split(args)
        except ValueError:
            console.print("[red]参数解析失败，请检查路径中的引号。[/red]")
            return True
        skip_confirm = "--yes" in parse_args or "-y" in parse_args
        watch = "--watch" in parse_args or "-w" in parse_args
        paths = [a for a in parse_args if not a.startswith("-")]
        if watch:
            from doubase.watch import run_watch
            run_watch(config)
        else:
            run_ingest(paths=paths, config=config, skip_confirm=skip_confirm)

    elif cmd == "analyze":
        if not args:
            console.print("[yellow]用法: /analyze <项目路径> [--focus <子目录>] [--yes][/yellow]")
            return True
        try:
            parse_args = shlex.split(args)
        except ValueError:
            console.print("[red]参数解析失败，请检查路径中的引号。[/red]")
            return True
        skip_confirm = "--yes" in parse_args or "-y" in parse_args
        project = parse_args[0] if parse_args else ""
        focus_idx = None
        for i, a in enumerate(parse_args):
            if a in ("--focus", "-f") and i + 1 < len(parse_args):
                focus_idx = i + 1
                break
        focus = parse_args[focus_idx] if focus_idx else None
        run_analyze(project_dir=project, config=config, focus=focus, skip_confirm=skip_confirm)

    else:
        console.print(f"[yellow]未知命令: /{cmd}。输入 /help 查看可用命令。[/yellow]")

    return True


def start_repl(config_path: str = None):
    """启动 DouBase 交互式 REPL。"""
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]❌ 配置错误: {e}[/red]")
        sys.exit(1)

    _touch_activity()

    # 欢迎界面
    console.print(_make_welcome())

    while True:
        # 两次输入之间检查闲置提示
        _check_idle_hint()

        try:
            console.print(PROMPT, end="")
            sys.stdout.flush()
            user_input = sys.stdin.readline()
            if not user_input:
                raise EOFError
            user_input = user_input.strip()
            _touch_activity()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            break

        cmd, content = _parse_command(user_input)

        if cmd is None:
            if not content:
                continue
            try:
                console.print("[bold green]●[/bold green]")
                run_ask(question=content, config=config)
            except ValueError as e:
                console.print(f"[red]❌ {e}[/red]")
            except Exception as e:
                console.print(f"[red]❌ 出错了: {e}[/red]")
        else:
            try:
                keep_running = _handle_command(cmd, content, config)
                if not keep_running:
                    break
            except Exception as e:
                console.print(f"[red]❌ 命令执行失败: {e}[/red]")

        _touch_activity()
