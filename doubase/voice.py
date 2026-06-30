"""语音输入模式 — 快捷键触发录音 → 语音转文字 → RAG 问答。"""

import sys
import threading
import queue

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from doubase.config import load_config
from doubase.pipeline import run_ask

console = Console(highlight=False)

HOTKEY_DESC = "Ctrl+Shift+V"
HOTKEY_COMBO = "<ctrl>+<shift>+v"

RECORDING_INDICATOR = "[bold red]🎤 正在录音... (再次按 Ctrl+Shift+V 停止)[/bold red]"
PROCESSING_TEXT = "[dim]⏳ 识别中...[/dim]"


def start_voice(config_path: str = None):
    """启动语音输入模式。"""
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]❌ 配置错误: {e}[/red]")
        sys.exit(1)

    # 尝试导入依赖
    try:
        import pynput.keyboard as keyboard
        import speech_recognition as sr
    except ImportError as e:
        console.print(f"[red]❌ 缺少语音功能依赖: {e}[/red]")
        console.print("[dim]请安装: pip install doubase[voice][/dim]")
        console.print("[dim]或: pip install SpeechRecognition pynput pyaudio[/dim]")
        sys.exit(1)

    recognizer = sr.Recognizer()
    microphone = sr.Microphone()

    # 状态标志
    recording = threading.Event()
    stop_app = threading.Event()
    cmd_queue = queue.Queue()

    # 调整环境噪音
    console.print("[dim]正在校准麦克风噪音...[/dim]")
    try:
        with microphone as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
    except Exception as e:
        console.print(f"[yellow]⚠️  麦克风校准失败: {e}[/yellow]")
        console.print("[dim]将继续尝试录音...[/dim]")

    console.print(_make_welcome())

    def on_activate():
        """热键触发：开始或停止录音。"""
        if recording.is_set():
            # 已经在录音 → 停止
            recording.clear()
            console.print()  # 换行
            console.print("[dim]录音结束，正在识别...[/dim]")
        else:
            # 开始录音
            recording.set()
            cmd_queue.put("record")

    # 注册全局热键
    try:
        listener = keyboard.GlobalHotKeys({HOTKEY_COMBO: on_activate})
        listener.start()
    except Exception as e:
        console.print(f"[red]❌ 无法注册全局快捷键 {HOTKEY_DESC}: {e}[/red]")
        console.print("[dim]可能需要在 系统设置 → 隐私与安全性 → 辅助功能 中授权终端[/dim]")
        sys.exit(1)

    console.print(f"[dim]按 {HOTKEY_DESC} 开始录音[/dim]")

    try:
        while not stop_app.is_set():
            try:
                cmd = cmd_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if cmd == "record":
                _record_and_ask(recognizer, microphone, config, recording)

    except KeyboardInterrupt:
        console.print("\n[dim]语音模式已退出[/dim]")
    finally:
        listener.stop()


def _record_and_ask(recognizer, microphone, config: dict, recording: threading.Event):
    """录音 → 语音识别 → RAG 问答。"""
    import speech_recognition as sr

    console.print(RECORDING_INDICATOR)

    # 持续录音直到 recording 被清除
    audio_frames = []
    try:
        with microphone as source:
            # 流式录音，分块检查停止信号
            chunk_duration = 0.5  # 每 0.5 秒检查一次
            while recording.is_set():
                try:
                    chunk = recognizer.listen(source, timeout=chunk_duration, phrase_time_limit=chunk_duration)
                    audio_frames.append(chunk)
                except sr.WaitTimeoutError:
                    # 超时，继续循环检查停止标志
                    continue
    except Exception as e:
        console.print(f"[red]❌ 录音失败: {e}[/red]")
        return

    if not audio_frames:
        console.print("[yellow]未检测到语音输入[/yellow]")
        return

    # 合并所有音频片段用于识别
    console.print(PROCESSING_TEXT)

    try:
        # 将音频片段合并
        full_audio = audio_frames[0]
        for chunk in audio_frames[1:]:
            full_audio.frame_data += chunk.frame_data

        # 使用 Google 免费语音识别（支持中文）
        text = recognizer.recognize_google(full_audio, language="zh-CN")
    except sr.UnknownValueError:
        console.print("[yellow]未能识别语音内容[/yellow]")
        return
    except sr.RequestError as e:
        console.print(f"[red]❌ 语音识别服务请求失败: {e}[/red]")
        return
    except Exception as e:
        console.print(f"[red]❌ 识别失败: {e}[/red]")
        return

    # 显示识别结果
    console.print(f"\n[bold cyan]🗣 识别结果:[/bold cyan] {text}\n")

    # 走 RAG 问答 pipeline (Markdown 渲染)
    try:
        run_ask(question=text, config=config, render_markdown=True)
    except Exception as e:
        console.print(f"[red]❌ 问答失败: {e}[/red]")


def _make_welcome() -> Panel:
    """构建欢迎面板。"""
    guide = Text.from_markup(
        f"按下 [bold cyan]{HOTKEY_DESC}[/bold cyan] 开始语音输入\n"
        "再次按下停止录音 → 自动识别 → RAG 问答\n"
        "按 Ctrl+C 退出语音模式"
    )
    return Panel(guide, title="🎙️ 语音输入模式", border_style="bold cyan")
