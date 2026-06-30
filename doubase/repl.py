"""DouBase 交互式 REPL — 直接对话模式，支持 / 命令。"""

import shlex
import sys
import threading
import time

from rich.console import Console
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

# 纯文本欢迎框，避免 Rich markup 导致边框对不齐
WELCOME = """
╔══════════════════════════════════════════╗
║  🧠 DouBase REPL                        ║
║  直接输入问题，或用 / 命令操作           ║
║  输入 /help 查看可用命令                 ║
╚══════════════════════════════════════════╝
"""

PROMPT = "[bold green]\n›[/bold green] "


class IdleHint:
    """闲置提示：闲置期间自动显示一次命令提示。"""

    def __init__(self):
        self._last_activity = time.time()
        self._hint_shown = False
        self._running = True
        self._paused = False
        self._lock = threading.Lock()

    def touch(self):
        with self._lock:
            self._last_activity = time.time()
            self._hint_shown = False

    def pause(self):
        with self._lock:
            self._paused = True

    def resume(self):
        with self._lock:
            self._paused = False
            self._last_activity = time.time()
            self._hint_shown = False

    def stop(self):
        self._running = False

    def should_hint(self) -> bool:
        with self._lock:
            if self._paused or self._hint_shown:
                return False
            if time.time() - self._last_activity >= IDLE_HINT_INTERVAL:
                self._hint_shown = True
                return True
            return False


def _print_hint():
    """打印闲置提示——写在 Prompt 的上方。"""
    console.print(HINT_TEXT)


def _parse_command(text: str) -> tuple[str | None, str]:
    """解析用户输入，返回 (command, args_string)。
    command 为 None 表示纯文本提问（走 ask）。
    以 / 开头的是命令。
    """
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
    """处理一条 / 命令。返回 False 表示应退出 REPL。"""
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

    idle_hint = IdleHint()

    # 后台空闲提示线程
    def hint_loop():
        while idle_hint._running:
            time.sleep(1)
            if idle_hint.should_hint():
                _print_hint()

    hint_thread = threading.Thread(target=hint_loop, daemon=True)
    hint_thread.start()

    # 欢迎界面
    console.print(WELCOME)

    while True:
        try:
            console.print(PROMPT, end="")
            sys.stdout.flush()
            user_input = sys.stdin.readline()
            if not user_input:  # EOF
                raise EOFError
            user_input = user_input.strip()
            idle_hint.touch()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            break

        cmd, content = _parse_command(user_input)

        if cmd is None:
            if not content:
                continue
            idle_hint.pause()
            try:
                # 绿色圆点提示这是 agent 的回答
                console.print("[bold green]●[/bold green]")
                run_ask(question=content, config=config)
            except ValueError as e:
                console.print(f"[red]❌ {e}[/red]")
            except Exception as e:
                console.print(f"[red]❌ 出错了: {e}[/red]")
            finally:
                idle_hint.resume()
        else:
            idle_hint.pause()
            try:
                keep_running = _handle_command(cmd, content, config)
                if not keep_running:
                    break
            except Exception as e:
                console.print(f"[red]❌ 命令执行失败: {e}[/red]")
            finally:
                idle_hint.resume()

    idle_hint.stop()
