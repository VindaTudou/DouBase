"""监控模式 — 监控目录中的新文件并自动导入。"""

import time
from pathlib import Path

from rich.console import Console

console = Console()


def run_watch(config: dict):
    """启动监控目录，自动导入新增的 .md/.docx/.pdf 文件。"""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        console.print(
            "[red]watchdog 库未安装。请执行: pip install watchdog[/red]"
        )
        return

    watch_dir = config.get("watch", {}).get("inbox_dir", "~/Documents/inbox")
    watch_path = Path(watch_dir).expanduser().resolve()
    watch_path.mkdir(parents=True, exist_ok=True)

    processed = set()

    class IngestHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            file_path = event.src_path
            ext = Path(file_path).suffix.lower()
            if ext not in (".md", ".docx", ".pdf"):
                return

            if file_path in processed:
                return
            processed.add(file_path)

            time.sleep(1)

            console.print(f"\n[bold]📥 检测到新文件: {file_path}[/bold]")
            from doubase.pipeline import run_ingest
            try:
                run_ingest([file_path], config, skip_confirm=True)
            except Exception as e:
                console.print(f"[red]❌ 导入失败: {e}[/red]")

    observer = Observer()
    observer.schedule(IngestHandler(), str(watch_path), recursive=True)
    observer.start()

    console.print(f"[bold]👀 正在监控目录: {watch_path}[/bold]")
    console.print("[dim]支持: .md / .docx / .pdf  按 Ctrl+C 停止[/dim]")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[yellow]监控已停止[/yellow]")

    observer.join()
