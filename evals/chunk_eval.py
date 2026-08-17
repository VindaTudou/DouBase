#!/usr/bin/env python3
"""分块参数 (chunk_size / chunk_overlap) 对检索召回率的影响评测。

复用 evals/recall_eval.py 的检索链与评分函数：
  - load_test_set        读取标注测试集 (JSONL)
  - build_relevant_index 在向量库中定位相关片段（text_marker 片段级匹配）
  - retrieve_chain       复刻 run_ask 检索链（向量 → 关键词融合 → LLM 精排）
  - score_query          计算 Hit@K / Recall@K / MRR

方法：对同一份 Obsidian 库（全部 .md）用不同 chunk_size/chunk_overlap 重建
临时向量库，semantic_merge 关闭（隔离滑动窗口参数的影响，避免 30+ 分钟 LLM 合并），
再对两套标注测试集逐配置打分对比。

用法:
  # 只估算各配置的 chunk 数与 embedding 费用（不调用任何 API）
  /opt/homebrew/bin/python3.11 evals/chunk_eval.py --dry-run

  # 正式评测（向量 + 混合重排序，确定性指标，不调 LLM）
  /opt/homebrew/bin/python3.11 evals/chunk_eval.py

  # 加上 LLM 精排（与线上 doubase ask 一致，较慢、有 LLM 成本）
  /opt/homebrew/bin/python3.11 evals/chunk_eval.py --llm
"""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# 让 evals 作为命名空间包可导入（evals/ 无 __init__.py，recall_eval.py 保持独立脚本）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from doubase.config import load_config
from doubase.chunker.chunker import Chunker, chunk_by_headings
from doubase.embedding import get_embedder
from doubase.generation import get_llm
from doubase.parsers import get_parser
from doubase.storage.vector_store import VectorStore

from evals.recall_eval import (
    load_test_set,
    build_relevant_index,
    retrieve_chain,
    score_query,
)

console = Console()

# 候选分块参数（围绕线上基线 512/64 展开，覆盖 小/中/大 chunk 与不同 overlap）
CONFIGS = [
    (256, 32),
    (256, 64),
    (512, 32),
    (512, 64),  # ← 线上当前值
    (512, 128),
    (768, 96),
    (1024, 128),
]

VAULT = "/Users/fangtudou/Library/Mobile Documents/iCloud~md~obsidian/Documents/Note"
TOP_K = [3, 5, 10]


def collect_md_files(vault: str) -> list[str]:
    return sorted(str(p) for p in Path(vault).rglob("*.md"))


def collect_store_sources(config: dict) -> list[str]:
    """从现有生产库读取全部唯一 source_path（含 pdf/docx/代码总结），作为完整语料。"""
    store = VectorStore(config["storage"]["persist_dir"],
                        config["storage"]["collection_name"])
    data = store._collection.get(include=["metadatas"], limit=1000000)
    seen: dict[str, None] = {}
    for m in data["metadatas"]:
        seen.setdefault(m.get("source_path", ""), None)
    return sorted(p for p in seen if p)


def _content_hash(file_path: str) -> str:
    return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()


def ingest_sources(config: dict, chunk_size: int, chunk_overlap: int,
                   sources: list[str], store: VectorStore, embedder) -> int:
    """用指定分块参数把给定文件列表解析、分块、embedding 后写入 store。

    与 run_ingest 一致：md 走 heading_split + 滑动窗口，pdf/docx 走 chunk_text；
    semantic_merge 关闭（隔离滑动窗口参数）。返回导入的 chunk 总数。
    """
    chunker = Chunker({
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "heading_split": True,
        "semantic_merge": False,
    })
    total = 0
    n_files = 0
    for fp in sources:
        parser = get_parser(fp)
        if parser is None:
            continue
        try:
            doc = parser.parse(fp)
        except Exception:
            continue
        if doc.file_type == "markdown":
            raw_chunks = chunk_by_headings(doc.text, fp, _content_hash(fp), chunker)
        else:
            raw_chunks = chunker.chunk_text(doc.text, fp, _content_hash(fp))
        if not raw_chunks:
            continue
        try:
            embeddings = embedder.embed([c.text for c in raw_chunks])
        except Exception as e:
            console.print(f"  [yellow]embedding 失败: {fp} ({e})[/yellow]")
            continue
        store.add_chunks_with_embeddings(raw_chunks, embeddings)
        total += len(raw_chunks)
        n_files += 1
    console.print(f"  [dim]导入 {n_files} 个文件 / {total} chunks[/dim]")
    return total


def dry_run(config: dict, vault: str) -> None:
    """本地估算各配置的 chunk 数、token 数与 embedding 费用，不调用任何 API。"""
    embed_price = config["pricing"]["zhipu"]["embed_price"]
    rows = []
    for cs, ov in CONFIGS:
        chunker = Chunker({"chunk_size": cs, "chunk_overlap": ov})
        n_chunks = 0
        n_tokens = 0
        n_files = 0
        for fp in collect_md_files(vault):
            parser = get_parser(fp)
            if parser is None:
                continue
            try:
                doc = parser.parse(fp)
            except Exception:
                continue
            if doc.file_type != "markdown":
                continue
            raw = chunk_by_headings(doc.text, fp, "x", chunker)
            if not raw:
                continue
            n_files += 1
            n_chunks += len(raw)
            n_tokens += sum(len(chunker._encode(c.text)) for c in raw)
        cost = n_tokens / 1_000_000 * embed_price
        rows.append((cs, ov, n_files, n_chunks, n_tokens, cost))

    table = Table(title="分块参数 → 预估 chunk 数 / 费用（不调用 API）")
    table.add_column("chunk_size", justify="right", style="bold")
    table.add_column("overlap", justify="right", style="bold")
    table.add_column("文件数", justify="right")
    table.add_column("chunks", justify="right")
    table.add_column("tokens", justify="right")
    table.add_column("embed 费用 (¥)", justify="right")
    for cs, ov, nf, nc, nt, cost in rows:
        tag = "  ← 当前" if (cs, ov) == (512, 64) else ""
        table.add_row(str(cs), str(ov), str(nf), f"{nc:,}", f"{nt:,}",
                      f"{cost:.3f}{tag}")
    console.print(table)


def score_variant(per_query: list, idx: int, k: int, relevant_index: dict,
                  n_queries: int) -> tuple[float, float, float]:
    hit = hit_mrr = 0
    recall_sum = 0.0
    for qi in range(n_queries):
        ranked = per_query[qi][idx][:k]
        hit_count, total, mrr = score_query(ranked, relevant_index[qi])
        if hit_count > 0:
            hit += 1
            hit_mrr += mrr
        if total > 0:
            recall_sum += hit_count / total
    return hit / n_queries, recall_sum / n_queries, hit_mrr / n_queries


def run_eval(test_sets: list[str], config: dict, embedder, use_llm: bool,
             corpus: str = "vault", configs: list[tuple[int, int]] = None) -> list[dict]:
    """对 configs（默认全部 CONFIGS）逐配置建库一次，对每套测试集打分。

    corpus:
      - "vault"：Obsidian 库全部 .md（默认，历史口径）
      - "store"：从现有生产库读取全部 source_path（含 pdf/docx/代码总结，完整语料）

    Returns:
        每配置一个 dict：{chunk_size, chunk_overlap, chunks, marker_warnings,
                           by_set: {测试集名: {K: {vector, hybrid}}}}
    """
    if configs is None:
        configs = CONFIGS
    if corpus == "store":
        sources = collect_store_sources(config)
        console.print(f"[bold]语料[/bold]: 生产库 {len(sources)} 个源文件（完整语料）")
    else:
        sources = collect_md_files(VAULT)
        console.print(f"[bold]语料[/bold]: Obsidian 库 {len(sources)} 个 .md")
    llm = get_llm(config) if use_llm else None
    all_queries = {ts: load_test_set(ts) for ts in test_sets}
    n_queries = {ts: len(qs) for ts, qs in all_queries.items()}

    results = []
    for cs, ov in configs:
        tag = " ← 当前" if (cs, ov) == (512, 64) else ""
        console.print(f"\n[bold]═══ {cs}/{ov}{tag} ═══[/bold]")
        tmp = tempfile.mkdtemp(prefix="doubase_chunk_eval_")
        try:
            store = VectorStore(tmp, "notes")
            n_chunks = ingest_sources(config, cs, ov, sources, store, embedder)

            by_set = {}
            n_marker_warn = 0
            for ts in test_sets:
                queries = all_queries[ts]
                relevant_index = build_relevant_index(store, queries)
                n_marker_warn += sum(
                    len([w for w in relevant_index[qi]["warnings"]
                         if "找不到 text_marker" in w])
                    for qi in range(n_queries[ts])
                )
                max_top_k = max(TOP_K)
                per_query = []
                for qi, q in enumerate(queries):
                    per_query.append(retrieve_chain(q["query"], config, embedder,
                                                    store, llm, max_top_k))
                variants = {}
                for k in TOP_K:
                    variants[k] = {
                        "vector": score_variant(per_query, 0, k, relevant_index,
                                                n_queries[ts]),
                        "hybrid": score_variant(per_query, 1, k, relevant_index,
                                                n_queries[ts]),
                    }
                by_set[Path(ts).name] = variants
            results.append({
                "chunk_size": cs, "chunk_overlap": ov, "chunks": n_chunks,
                "marker_warnings": n_marker_warn, "by_set": by_set,
            })
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return results


def print_results(results: list[dict], test_sets: list[str]) -> None:
    for ts in test_sets:
        set_name = Path(ts).name
        for k in TOP_K:
            table = Table(title=f"召回率对比 Top-{k}（{set_name}，片段级标注）")
            table.add_column("chunk_size/overlap", style="bold")
            table.add_column("chunks", justify="right")
            for name, tag in (("纯向量", "vector"), ("混合", "hybrid")):
                table.add_column(f"{name} Hit@{k}", justify="right")
                table.add_column(f"{name} Recall@{k}", justify="right")
                table.add_column(f"{name} MRR", justify="right")
            for r in results:
                cs, ov = r["chunk_size"], r["chunk_overlap"]
                label = f"{cs}/{ov}" + (" ←当前" if (cs, ov) == (512, 64) else "")
                row = [label, str(r["chunks"])]
                for tag in ("vector", "hybrid"):
                    hit, recall, mrr = r["by_set"][set_name][k][tag]
                    row += [f"{hit:.3f}", f"{recall:.3f}", f"{mrr:.3f}"]
                table.add_row(*row)
            console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="分块参数对检索召回率的影响")
    parser.add_argument("--test-set", nargs="+", default=[
        "evals/test_set.jsonl", "evals/test_set_hard.jsonl",
    ], help="标注测试集路径（默认直述 + 改述两套）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只本地估算 chunk 数 / 费用，不调 API")
    parser.add_argument("--llm", action="store_true",
                        help="加入 LLM 精排（与线上一致，较慢）")
    parser.add_argument("--vault", default=VAULT, help="Obsidian 库路径")
    parser.add_argument("--corpus", choices=["vault", "store"], default="vault",
                        help="语料：vault=Obsidian 库全部 .md；store=生产库全部源文件（含 pdf/docx）")
    parser.add_argument("--only", default="",
                        help="只跑指定配置，逗号分隔，如 '256/64,512/64'")
    args = parser.parse_args()

    config = load_config()
    if args.dry_run:
        dry_run(config, args.vault)
        return

    configs = None
    if args.only:
        configs = []
        for part in args.only.split(","):
            cs, ov = part.strip().split("/")
            configs.append((int(cs), int(ov)))

    embedder = get_embedder(config)
    results = run_eval(args.test_set, config, embedder, args.llm,
                       corpus=args.corpus, configs=configs)
    print_results(results, args.test_set)

    # 保存结果
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    out = results_dir / f"{stamp}-chunk-eval.md"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    console.print(f"\n[green]结果已保存: {out}[/green]")


if __name__ == "__main__":
    main()
