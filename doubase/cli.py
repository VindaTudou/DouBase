"""CLI 入口 — 基于 argparse 的命令路由。"""

import argparse
import sys
from pathlib import Path

# Python 版本检查
if sys.version_info < (3, 10):
    print(
        f"❌ DouBase 需要 Python >= 3.11，当前版本: {sys.version}"
        f"\n   请使用: /opt/homebrew/bin/python3.11 doubase/cli.py"
        f"\n   或通过 pip install -e . 安装后使用 doubase 命令",
        file=sys.stderr,
    )
    sys.exit(1)

# 确保项目根目录在 sys.path 中，支持直接运行 python doubase/cli.py
_sys_path_inserted = Path(__file__).resolve().parent.parent
if str(_sys_path_inserted) not in sys.path:
    sys.path.insert(0, str(_sys_path_inserted))

try:
    from doubase.config import load_config
    from doubase.pipeline import run_ingest, run_ask, run_analyze
except ImportError as e:
    print(
        f"❌ 导入失败: {e}\n"
        f"   请确保已安装依赖: pip install -e .\n"
        f"   或使用正确的 Python 版本 (>= 3.11)",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="doubase",
        description="本地 RAG agent，支持笔记检索与代码分析",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # --- ask ---
    ask_parser = subparsers.add_parser("ask", help="提问（RAG + LLM）")
    ask_parser.add_argument("question", help="你的问题")
    ask_parser.add_argument(
        "--llm", help="覆盖 LLM provider（deepseek, openai, openai_compat）"
    )
    ask_parser.add_argument(
        "--embedding", help="覆盖 embedding provider（zhipu, local）"
    )

    # --- ingest ---
    ingest_parser = subparsers.add_parser("ingest", help="导入文档到知识库")
    ingest_parser.add_argument("paths", nargs="+", help="待导入的文件或目录")
    ingest_parser.add_argument(
        "--yes", "-y", action="store_true", help="跳过确认提示"
    )
    ingest_parser.add_argument(
        "--watch", "-w", action="store_true", help="监控目录，自动导入新文件"
    )

    # --- analyze ---
    analyze_parser = subparsers.add_parser(
        "analyze", help="分析代码项目并将结果入库"
    )
    analyze_parser.add_argument("project", help="项目目录路径")
    analyze_parser.add_argument(
        "--focus", "-f", help="优先分析的子目录"
    )
    analyze_parser.add_argument(
        "--yes", "-y", action="store_true", help="跳过确认提示"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        print("\n💡 快速开始:")
        print("  1. 设置 API Key:")
        print("     export DEEPSEEK_API_KEY=sk-...")
        print("     export ZHIPU_API_KEY=...")
        print("  2. 导入笔记:")
        print("     doubase ingest ~/Documents/notes/")
        print("  3. 开始提问:")
        print('     doubase ask "你的问题"')
        sys.exit(0)

    # 加载配置
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"❌ 配置错误: {e}")
        sys.exit(1)

    # 路由命令
    try:
        if args.command == "ask":
            run_ask(
                question=args.question,
                config=config,
                llm_override=args.llm,
                embedding_override=args.embedding,
            )

        elif args.command == "ingest":
            if args.watch:
                from doubase.watch import run_watch
                run_watch(config)
            else:
                run_ingest(
                    paths=args.paths,
                    config=config,
                    skip_confirm=args.yes,
                )

        elif args.command == "analyze":
            run_analyze(
                project_dir=args.project,
                config=config,
                focus=args.focus,
                skip_confirm=args.yes,
            )
    except ValueError as e:
        print(f"❌ 配置错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
