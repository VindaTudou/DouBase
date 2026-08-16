#!/usr/bin/env python3
"""DouBase 检索召回率评测工具。

对带标注的测试集 (JSONL) 复刻 `run_ask` 的检索链（跳过 LLM 生成和查询优化），
输出三种检索配置的对比指标，回答"检索召回率是多少、哪个阶段贡献了多少"：

  1. 纯向量     — 只做向量检索，取 top-K
  2. 混合       — 向量 + 关键词融合 (rerank)
  3. 全链路     — 混合 + LLM 精排 (llm_rerank)   ← 与线上 run_ask 一致

指标:
  Hit@K    检索成功率 = 有多少比例的查询在 top-K 中至少命中 1 个相关片段
  Recall@K 片段级召回率 = 检索到的相关片段数 / 知识库中全部相关片段数（按 query 平均）
  MRR      首个相关片段排名的倒数均值

用法:
  /opt/homebrew/bin/python3.11 evals/recall_eval.py \
      --test-set evals/test_set.jsonl \
      --top-k 3 5 10

测试集格式 (JSONL，每行一个 JSON):
  {
    "query": "数据库事务的 ACID 特性是什么？",
    "relevant": [
      {"source_path": "/path/to/note.md", "text_marker": "原子性"}
    ]
  }

  text_marker 可选：
    - 给定时为片段级匹配 —— 该片段文本必须包含此标记才算命中；
    - 缺省时退化到文件级匹配 —— 只要 source_path 命中即算命中。
  source_path 必须与向量库中存储的元数据完全一致（可通过 --dump-sources 查看）。
"""

import argparse
import json
import sys
from collections import defaultdict

from rich.console import Console

from doubase.config import load_config
from doubase.embedding import get_embedder
from doubase.storage.vector_store import VectorStore
from doubase.retrieval.retriever import Retriever, rerank, llm_rerank
from doubase.generation import get_llm

console = Console()

# 复刻 pipeline.py 中单问题检索链的默认上游候选数（向量检索取 top_k 的 3 倍）
CANDIDATE_MULTIPLIER = 3
# 混合阶段 rerank 最多保留的候选数（与 pipeline.py 一致，之后才进入 LLM 精排）
FUSION_CAP = 10


def load_test_set(path: str) -> list[dict]:
    """读取 JSONL 测试集，并做基本校验。"""
    queries = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            assert "query" in q and q["query"].strip(), f"第 {line_no} 行缺 query"
            assert isinstance(q.get("relevant"), list) and q["relevant"], \
                f"第 {line_no} 行缺 relevant"
            for rel in q["relevant"]:
                assert rel.get("source_path"), f"第 {line_no} 行 relevant 缺 source_path"
            queries.append(q)
    return queries


def build_relevant_index(store: VectorStore, queries: list[dict]) -> dict:
    """扫描向量库，为每条 query 建立"相关片段"集合，并校验 ground-truth 标注。

    返回 {query_idx: {"chunks": {text}, "total": int, "warnings": [str]}}
    """
    # source_path -> [(text_marker, is_marker)] ，is_marker 为 True 表示片段级标注
    want: dict[str, list] = defaultdict(list)
    for q in queries:
        for rel in q["relevant"]:
            want[rel["source_path"]].append((rel.get("text_marker"), rel))

    # 一次性拉出全部文档，按 source_path 分组
    all_data = store._collection.get(include=["metadatas", "documents"], limit=1000000)
    by_source: dict[str, list[str]] = defaultdict(list)
    for m, d in zip(all_data["metadatas"], all_data["documents"]):
        by_source[m.get("source_path", "")].append(d)

    index: dict[int, dict] = {}
    for qi, q in enumerate(queries):
        relevant_chunks: set[str] = set()
        warnings = []
        for rel in q["relevant"]:
            src = rel["source_path"]
            marker = rel.get("text_marker")
            texts = by_source.get(src, [])
            if not texts:
                warnings.append(f"  ⚠️  {src} 在向量库中不存在（0 chunks）")
                continue
            if marker:
                matched = [t for t in texts if marker in t]
                if not matched:
                    warnings.append(f"  ⚠️  {src} 中找不到 text_marker「{marker}」"
                                    f"（共 {len(texts)} chunks，该 query 必然漏召）")
                relevant_chunks.update(matched)
            else:
                relevant_chunks.update(texts)
        index[qi] = {"chunks": relevant_chunks, "total": len(relevant_chunks),
                     "warnings": warnings}
    return index


def retrieve_chain(query: str, config: dict, embedder, store, llm,
                   max_top_k: int) -> tuple[list[dict], list[dict], list[dict]]:
    """复刻 run_ask 的检索链，返回 (向量结果, 混合结果, 全链路结果)。

    三条链共享同一批向量候选（top_k×3），只做一次向量检索；
    混合 / 全链路在其上叠加，LLM 精排每条 query 只调用一次 LLM。
    """
    ret_config = config.get("retrieval", {})
    vw = float(ret_config.get("vector_weight", 0.6))
    kw = float(ret_config.get("keyword_weight", 0.4))

    retriever = Retriever(embedder=embedder, vector_store=store)
    candidates = retriever.retrieve(query, top_k=max_top_k * CANDIDATE_MULTIPLIER)

    if not candidates:
        return [], [], []

    # 纯向量：按向量距离升序（与 search 返回顺序一致）
    vector_only = candidates[:max_top_k]

    # 混合：关键词融合重排（上限 FUSION_CAP，与 pipeline.py 一致）
    fusion = rerank(query, candidates, top_k=min(FUSION_CAP, len(candidates)),
                    vector_weight=vw, keyword_weight=kw)
    hybrid = fusion[:max_top_k]

    # 全链路：LLM 精排（调用失败时 llm_rerank 内部已回退为原顺序）
    full = llm_rerank(query, fusion, llm, top_k=max_top_k)
    if full and all(c.get("llm_score", 0) == 3 for c in full):
        full = hybrid  # 与 pipeline.py 一致：LLM 评分解析失败时回退
    return vector_only, hybrid, full


def score_query(retrieved: list[dict], relevant: dict) -> tuple[int, int, float]:
    """计算单条 query 的 (命中片段数, 相关片段总数, 首个命中 MRR 贡献)。

    relevant: build_relevant_index 返回的 {chunks, total, warnings}
    """
    rel_texts = relevant["chunks"]
    hit_count = sum(1 for c in retrieved if c["text"] in rel_texts)
    mrr = 0.0
    for i, c in enumerate(retrieved, 1):
        if c["text"] in rel_texts:
            mrr = 1.0 / i
            break
    return hit_count, relevant["total"], mrr


def main() -> None:
    parser = argparse.ArgumentParser(description="DouBase 检索召回率评测")
    parser.add_argument("--test-set", default="evals/test_set.jsonl",
                        help="标注测试集路径 (JSONL)")
    parser.add_argument("--top-k", nargs="+", type=int, default=[3, 5, 10],
                        help="要评测的 K 值列表")
    parser.add_argument("--dump-sources", action="store_true",
                        help="只打印向量库中的全部 source_path，用于核对标注")
    args = parser.parse_args()

    config = load_config()
    embedder = get_embedder(config)
    store = VectorStore(config["storage"]["persist_dir"],
                        config["storage"]["collection_name"])

    if args.dump_sources:
        all_data = store._collection.get(include=["metadatas"], limit=1000000)
        seen = set()
        for m in all_data["metadatas"]:
            p = m.get("source_path", "")
            if p not in seen:
                seen.add(p)
                print(p)
        return

    queries = load_test_set(args.test_set)
    if not queries:
        console.print("[red]测试集为空[/red]")
        sys.exit(1)

    console.print(f"[bold]知识库[/bold]: {store._collection.count()} chunks, "
                  f"collection={config['storage']['collection_name']}")
    console.print(f"[bold]测试集[/bold]: {len(queries)} 条 query")

    relevant_index = build_relevant_index(store, queries)
    n_warn = 0
    for qi, q in enumerate(queries):
        for w in relevant_index[qi]["warnings"]:
            n_warn += 1
            console.print(f"[yellow]{w}[/yellow]")
    if n_warn:
        console.print(f"[yellow]共 {n_warn} 条标注警告，请检查测试集[/yellow]\n")
    else:
        console.print("[green]✓ 所有 ground-truth 标注在向量库中均可命中[/green]\n")

    max_top_k = max(args.top_k)
    llm = get_llm(config)

    # 每条 query 只检索一次，得到三条排序结果（LLM 精排只调用一次）
    per_query = []  # [(vector_only, hybrid, full)]
    for qi, q in enumerate(queries):
        per_query.append(retrieve_chain(q["query"], config, embedder,
                                        store, llm, max_top_k))
        console.print(f"[dim]检索中 {qi+1}/{len(queries)}[/dim]", end="\r")
    console.print()

    variants = {
        "纯向量 (vector)": 0,
        "混合 (vector+keyword)": 1,
        "全链路 (vector+keyword+LLM)": 2,
    }

    for k in args.top_k:
        console.print(f"\n[bold]═══ Top-{k} ═══[/bold]")
        for name, idx in variants.items():
            hit = hit_mrr = 0
            recall_sum = 0.0
            for qi in range(len(queries)):
                ranked = per_query[qi][idx][:k]
                hit_count, total, mrr = score_query(ranked, relevant_index[qi])
                if hit_count > 0:
                    hit += 1
                    hit_mrr += mrr
                if total > 0:
                    recall_sum += hit_count / total
            n = len(queries)
            console.print(f"  {name:<28} Hit@{k}={hit/n:.3f}   "
                          f"Recall@{k}={recall_sum/n:.3f}   MRR={hit_mrr/n:.3f}")

    console.print("\n[dim]注: Hit@K 即检索成功率（至少命中一个相关片段），"
                  "是个人知识库 RAG 最常用的召回指标；\n"
                  "    Recall@K 为片段级召回（按 query 平均）。两者结合看："
                  "Hit 高而 Recall 低 → 相关片段虽被检索到但排得太散。[/dim]")


if __name__ == "__main__":
    main()
