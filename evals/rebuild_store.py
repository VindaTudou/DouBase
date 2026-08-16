#!/usr/bin/env python3
"""用当前分块器全量重建向量库（清洗）。

做法：
  1. 从现有 collection 读取全部唯一 source_path，作为语料清单 —— 保证"不增不减"，
     即重建后仍包含完全相同的文件（含 doubase analyze 生成的 doubase_summaries）。
  2. 备份持久化目录到 ~/.doubase/vectors.bak.<时间戳>（默认保留）。
  3. 清空 collection。
  4. 用当前 config 的 chunker 参数 + 修复后的 chunk_by_headings（标题并回 chunk 文本）
     重新解析 → 分块 → embedding → 入库。semantic_merge 关闭（与评测一致，
     且避免 30+ 分钟的 LLM 合并；本脚本不调用 merge_semantically）。

用法:
  /opt/homebrew/bin/python3.11 evals/rebuild_store.py --dry-run   # 只估算，不碰库
  /opt/homebrew/bin/python3.11 evals/rebuild_store.py             # 正式重建
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 让 evals 作为命名空间包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from doubase.config import load_config
from doubase.chunker.chunker import Chunker, chunk_by_headings
from doubase.chunker.semantic_merger import merge_semantically
from doubase.embedding import get_embedder
from doubase.generation import get_llm
from doubase.parsers import get_parser
from doubase.storage.vector_store import VectorStore

console = Console()


def collect_sources(store: VectorStore) -> list[str]:
    """从现有 collection 读取全部唯一 source_path（语料清单）。"""
    all_data = store._collection.get(include=["metadatas"], limit=1000000)
    seen: dict[str, None] = {}
    for m in all_data["metadatas"]:
        seen.setdefault(m.get("source_path", ""), None)
    return sorted(p for p in seen if p)


def _content_hash(file_path: str) -> str:
    return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()


def _estimate(sources: list[str], config: dict, chunker: Chunker) -> Table:
    """本地估算各文件的 chunk 数与 embedding 费用，不调 API。"""
    embed_price = config["pricing"]["zhipu"]["embed_price"]
    table = Table(title=f"重建预估（{len(sources)} 个文件）")
    table.add_column("类型", justify="right")
    table.add_column("文件数", justify="right")
    table.add_column("chunks", justify="right")
    table.add_column("tokens", justify="right")
    by_type: dict[str, dict] = {}
    for fp in sources:
        parser = get_parser(fp)
        if parser is None:
            by_type.setdefault("skip", {"n": 0, "chunks": 0, "tokens": 0})
            by_type["skip"]["n"] += 1
            continue
        try:
            doc = parser.parse(fp)
        except Exception:
            by_type.setdefault("parse失败", {"n": 0, "chunks": 0, "tokens": 0})
            by_type["parse失败"]["n"] += 1
            continue
        key = doc.file_type
        e = by_type.setdefault(key, {"n": 0, "chunks": 0, "tokens": 0})
        e["n"] += 1
        if doc.file_type == "markdown":
            raw = chunk_by_headings(doc.text, fp, "x", chunker)
        else:
            raw = chunker.chunk_text(doc.text, fp, "x")
        e["chunks"] += len(raw)
        e["tokens"] += sum(len(chunker._encode(c.text)) for c in raw)
    total_chunks = total_tokens = 0
    for key, e in by_type.items():
        total_chunks += e["chunks"]
        total_tokens += e["tokens"]
        cost = e["tokens"] / 1_000_000 * embed_price
        table.add_row(key, str(e["n"]), str(e["chunks"]), str(e["tokens"]))
    table.add_row("合计", str(len(sources)), str(total_chunks), str(total_tokens))
    console.print(table)
    console.print(
        f"[dim]预计 embedding 费用 ≈ ¥{total_tokens / 1_000_000 * embed_price:.3f}"
        f"（chunk_size={chunker.chunk_size}, overlap={chunker.chunk_overlap}）[/dim]"
    )
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description="全量重建向量库")
    parser.add_argument("--dry-run", action="store_true",
                        help="只估算，不碰库")
    parser.add_argument("--no-backup", action="store_true",
                        help="不保留持久化目录备份")
    parser.add_argument("--merge", dest="merge", action="store_true",
                        default=None, help="对 markdown 文件启用 LLM 语义合并")
    parser.add_argument("--no-merge", dest="merge", action="store_false",
                        help="关闭 LLM 语义合并")
    parser.add_argument("--resume", action="store_true",
                        help="断点续传：跳过已入库的源，从最近备份读取完整清单继续")
    config = load_config()
    parser.set_defaults(merge=bool(config.get("chunker", {}).get("semantic_merge", True)))
    args = parser.parse_args()

    chunker = Chunker(config.get("chunker", {}))
    store = VectorStore(config["storage"]["persist_dir"],
                        config["storage"]["collection_name"])

    col_name = config["storage"]["collection_name"]

    if args.resume:
        # 断点续传：完整清单 = 最近备份库的源；跳过当前库已入库的源
        persist = Path(config["storage"]["persist_dir"]).expanduser().resolve()
        baks = sorted(persist.parent.glob(persist.name + ".bak.*"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        if not baks:
            console.print("[red]未找到备份目录，无法 resume[/red]")
            sys.exit(1)
        full_store = VectorStore(str(baks[0]), col_name)
        full_sources = collect_sources(full_store)
        existing = set(collect_sources(store))
        sources = [s for s in full_sources if s not in existing]
        console.print(f"[bold]resume[/bold]: 全清单 {len(full_sources)}, "
                      f"已入库 {len(existing)}, 待处理 {len(sources)}")
        if not sources:
            console.print("[green]没有待处理的源，已全部完成[/green]")
            return
        do_backup = False
        do_wipe = False
    else:
        sources = collect_sources(store)
        console.print(f"[bold]当前 collection[/bold]: {store.count()} chunks, "
                      f"{len(sources)} 个唯一源文件")
        if args.dry_run:
            _estimate(sources, config, chunker)
            return
        do_backup = not args.no_backup
        do_wipe = True

    # 备份持久化目录（仅全量模式）
    persist = Path(config["storage"]["persist_dir"]).expanduser().resolve()
    if do_backup and persist.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = Path(str(persist) + f".bak.{stamp}")
        console.print(f"[dim]备份持久化目录 -> {bak}[/dim]")
        shutil.copytree(persist, bak, dirs_exist_ok=True)

    # 清空 collection（删除后重建，仅全量模式）
    if do_wipe:
        store._client.delete_collection(col_name)
        store = VectorStore(config["storage"]["persist_dir"], col_name)

    # 全量重入库
    embedder = get_embedder(config)
    llm = get_llm(config) if args.merge else None
    if args.merge:
        console.print("[bold]LLM 语义合并: 开启[/bold]（仅 markdown；pdf/docx 无标题结构，不合并）")
    ok = failed = skipped = 0
    for i, fp in enumerate(sources, 1):
        short = fp.rsplit("/", 1)[-1]
        console.print(f"  ▶ [{i}/{len(sources)}] {short}")
        parser = get_parser(fp)
        if parser is None:
            skipped += 1
            console.print(f"     ⏭️  不支持: {fp}")
            continue
        try:
            doc = parser.parse(fp)
        except Exception as e:
            failed += 1
            console.print(f"     ❌ 解析失败: {fp} ({e})")
            continue
        content_hash = _content_hash(fp)
        if doc.file_type == "markdown":
            raw = chunk_by_headings(doc.text, fp, content_hash, chunker)
            # Excalidraw 画图文件：Drawing 节是大段 base64，合并纯属浪费（一个文件上百对）
            if args.merge and "excalidraw" not in fp.lower():
                try:
                    raw = merge_semantically(raw, llm)
                except Exception as e:
                    console.print(f"  [yellow]合并失败，退回原始分块: {fp} ({e})[/yellow]")
        else:
            raw = chunker.chunk_text(doc.text, fp, content_hash)
        if not raw:
            skipped += 1
            continue
        try:
            embeddings = embedder.embed([c.text for c in raw])
        except Exception as e:
            failed += 1
            console.print(f"  ❌ [{i}/{len(sources)}] embedding 失败: {fp} ({e})")
            continue
        store.add_chunks_with_embeddings(raw, embeddings)
        ok += 1
        if i % 20 == 0 or i == len(sources):
            console.print(f"  [dim][{i}/{len(sources)}] 已导入 {ok} 个文件[/dim]")

    console.print(f"\n[bold green]重建完成[/bold green]: 成功 {ok}, 跳过 {skipped}, 失败 {failed}")
    console.print(f"[bold]新 collection[/bold]: {store.count()} chunks")


if __name__ == "__main__":
    main()
