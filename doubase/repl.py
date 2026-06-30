"""DouBase 交互式 REPL — 直接对话模式，支持 / 命令。"""

import shlex
import sys
import threading
import time

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from doubase.config import load_config
from doubase.pipeline import run_ingest, run_ask, run_analyze

console = Console(highlight=False)

IDLE_HINT_INTERVAL = 30
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

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


class RunningIndicator:
    """后台运行动画 — TTY 下显示旋转动画，管道模式下显示静态文本。

    支持动态切换标签文本（change_label）。
    """

    def __init__(self, label: str = "处理中"):
        self._label = label
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        self._is_tty = sys.stdout.isatty()
        self._lock = threading.Lock()

    def start(self):
        self._running.set()
        if self._is_tty:
            console.print()
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()
        else:
            console.print(f"[dim]⏳ {self._label}...[/dim]")

    def change_label(self, new_label: str):
        """运行中切换标签文本。"""
        with self._lock:
            self._label = new_label
        if not self._is_tty:
            console.print(f"[dim]⏳ {self._label}...[/dim]")

    def stop(self):
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        if self._is_tty:
            sys.stdout.write("\r\033[K\n")
            sys.stdout.flush()

    def _animate(self):
        i = 0
        while self._running.is_set():
            with self._lock:
                label = self._label
            frame = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
            sys.stdout.write(f"\r\033[K  {frame} {label}...")
            sys.stdout.flush()
            i += 1
            time.sleep(0.08)
        # stop() 负责最终清理


def _make_welcome() -> Panel:
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
    global _hint_shown
    if not _hint_shown and time.time() - _last_input_time >= IDLE_HINT_INTERVAL:
        _hint_shown = True
        console.print(HINT_TEXT)


def _parse_command(text: str) -> tuple[str | None, str]:
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
            spinner = RunningIndicator("正在导入文档")
            spinner.start()
            try:
                run_ingest(paths=paths, config=config, skip_confirm=skip_confirm)
            finally:
                spinner.stop()

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
        spinner = RunningIndicator("正在分析代码项目")
        spinner.start()
        try:
            run_analyze(project_dir=project, config=config, focus=focus, skip_confirm=skip_confirm)
        finally:
            spinner.stop()

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
    console.print(_make_welcome())

    while True:
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
            spinner = RunningIndicator("正在检索")
            spinner.start()
            try:
                run_ask(
                    question=content, config=config, render_markdown=True,
                    on_retrieval_done=lambda: spinner.change_label("正在思考"),
                    on_before_stream=spinner.stop,
                )
            except ValueError as e:
                console.print(f"[red]❌ {e}[/red]")
            except Exception as e:
                console.print(f"[red]❌ 出错了: {e}[/red]")
            finally:
                spinner.stop()
        else:
            try:
                keep_running = _handle_command(cmd, content, config)
                if not keep_running:
                    break
            except Exception as e:
                console.print(f"[red]❌ 命令执行失败: {e}[/red]")

        _touch_activity()
