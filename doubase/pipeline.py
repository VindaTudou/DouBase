"""核心流水线：ingest 和 ask。"""

import hashlib
from pathlib import Path

from doubase.parsers import get_parser
from doubase.chunker.chunker import Chunker
from doubase.embedding import get_embedder
from doubase.storage.vector_store import VectorStore
from doubase.retrieval.retriever import Retriever
from doubase.generation import get_llm
from doubase.analyzer.scanner import scan_project

from rich.console import Console
from rich.table import Table

console = Console()


def _hash_file(file_path: str) -> str:
    """计算文件内容的 SHA256 哈希。"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_files(paths: list[str]) -> list[str]:
    """展开目录为文件列表。"""
    all_files = []
    for p in paths:
        path = Path(p).expanduser().resolve()
        if path.is_dir():
            for f in path.rglob("*"):
                if f.is_file():
                    all_files.append(str(f))
        elif path.is_file():
            all_files.append(str(path))
        else:
            console.print(f"[yellow]⚠️  路径不存在: {p}[/yellow]")
    return sorted(all_files)


def estimate_ingest(paths: list[str], config: dict) -> dict:
    """预扫描文件，估算 embedding 费用（不调用任何 API）。

    Returns:
        包含 files（各文件统计）、total_chunks、total_tokens、total_cost 的字典。
    """
    files = _collect_files(paths)
    chunker = Chunker(config.get("chunker", {}))
    pricing = config.get("pricing", {}).get("zhipu", {})
    embed_price = pricing.get("embed_price", 0.5)

    file_stats = []
    total_tokens = 0
    total_chunks = 0
    skipped_unsupported = []

    for file_path in files:
        parser = get_parser(file_path)
        if parser is None:
            skipped_unsupported.append(file_path)
            continue

        try:
            doc = parser.parse(file_path)
        except Exception:
            skipped_unsupported.append(file_path)
            continue

        content_hash = _hash_file(file_path)
        chunks = chunker.chunk_text(doc.text, file_path, content_hash)

        token_count = sum(len(chunker._encode(c.text)) for c in chunks)

        file_stats.append({
            "path": file_path,
            "size_kb": round(Path(file_path).stat().st_size / 1024, 1),
            "chunks": len(chunks),
            "tokens": token_count,
        })
        total_tokens += token_count
        total_chunks += len(chunks)

    total_cost = total_tokens / 1_000_000 * embed_price

    return {
        "files": file_stats,
        "skipped": skipped_unsupported,
        "total_chunks": total_chunks,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "embedding_provider": config["embedding"]["provider"],
        "embedding_model": config["embedding"].get(
            config["embedding"]["provider"], {}
        ).get("model", "unknown"),
    }


def display_ingest_estimate(estimate: dict):
    """展示 ingest 费用估算表格。"""
    console.print()
    console.print("[bold]═══ Ingest 预算估算 ═══[/bold]")
    console.print(
        f"Embedding 提供商: {estimate['embedding_provider']} "
        f"({estimate['embedding_model']})"
    )

    if estimate["files"]:
        table = Table(show_header=True, header_style="bold")
        table.add_column("文件", style="dim")
        table.add_column("大小", justify="right")
        table.add_column("Chunks", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("费用", justify="right")

        avg_cost_per_token = (
            estimate["total_cost"] / max(1, estimate["total_tokens"])
        )
        for f in estimate["files"]:
            file_cost = f["tokens"] * avg_cost_per_token
            table.add_row(
                f["path"],
                f"{f['size_kb']} KB",
                str(f["chunks"]),
                f"{f['tokens']:,}",
                f"¥{file_cost:.4f}",
            )

        table.add_section()
        table.add_row(
            "[bold]合计[/bold]",
            "",
            f"[bold]{estimate['total_chunks']}[/bold]",
            f"[bold]{estimate['total_tokens']:,}[/bold]",
            f"[bold]¥{estimate['total_cost']:.4f}[/bold]",
        )
        console.print(table)

    if estimate["skipped"]:
        console.print(
            f"\n[yellow]⚠️  跳过不支持的文件: "
            f"{len(estimate['skipped'])} 个[/yellow]"
        )


def run_ingest(paths: list[str], config: dict, skip_confirm: bool = False):
    """运行完整的 ingest 流水线：解析 → 哈希去重 → 分块 → embedding → 存储。

    Args:
        paths: 待导入的文件或目录列表。
        config: 完整配置字典。
        skip_confirm: True 时跳过确认提示。
    """
    # 阶段 1: 估算
    estimate = estimate_ingest(paths, config)
    display_ingest_estimate(estimate)

    # 阶段 2: 确认
    if not skip_confirm:
        try:
            answer = input("\n是否继续? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]已取消[/yellow]")
            return
        if answer and answer not in ("y", "yes"):
            console.print("[yellow]已取消[/yellow]")
            return

    # 阶段 3: 执行
    results = {
        "success": [],
        "skipped_unchanged": [],
        "skipped_unsupported": [],
        "failed": [],
    }

    files = _collect_files(paths)
    chunker = Chunker(config.get("chunker", {}))
    embedder = get_embedder(config)
    store = VectorStore(
        persist_dir=config["storage"]["persist_dir"],
        collection_name=config["storage"]["collection_name"],
    )

    for file_path in files:
        parser = get_parser(file_path)
        if parser is None:
            results["skipped_unsupported"].append(file_path)
            console.print(f"  ⚠️  跳过 (不支持): {file_path}")
            continue

        # 去重检查
        content_hash = _hash_file(file_path)
        existing_hash = store.get_existing_hash(file_path)
        if existing_hash == content_hash:
            results["skipped_unchanged"].append(file_path)
            console.print(f"  ⏭️  跳过 (未变更): {file_path}")
            continue

        # 如果文件已变更，先删除旧 chunks
        if existing_hash is not None:
            store.delete_by_source(file_path)

        # 解析
        try:
            doc = parser.parse(file_path)
        except Exception as e:
            results["failed"].append({"path": file_path, "error": str(e)})
            console.print(f"  ❌ 解析失败: {file_path} ({e})")
            continue

        # 分块
        chunks = chunker.chunk_text(doc.text, file_path, content_hash)
        if not chunks:
            results["skipped_unchanged"].append(file_path)
            console.print(f"  ⏭️  跳过 (空文件): {file_path}")
            continue

        # Embedding
        try:
            embeddings = embedder.embed([c.text for c in chunks])
        except Exception as e:
            results["failed"].append(
                {"path": file_path, "error": f"embedding: {e}"}
            )
            console.print(f"  ❌ Embedding 失败: {file_path} ({e})")
            continue

        # 存储
        try:
            store.add_chunks_with_embeddings(chunks, embeddings)
        except Exception as e:
            results["failed"].append(
                {"path": file_path, "error": f"storage: {e}"}
            )
            console.print(f"  ❌ 存储失败: {file_path} ({e})")
            continue

        results["success"].append({"path": file_path, "chunks": len(chunks)})
        console.print(f"  ✅ 成功导入: {file_path} ({len(chunks)} chunks)")

    # 汇总
    console.print()
    console.print("[bold]doubase ingest 结果:[/bold]")
    console.print(
        f"  总计: {len(results['success'])} 成功, "
        f"{len(results['skipped_unchanged'])} 未变更, "
        f"{len(results['skipped_unsupported'])} 跳过, "
        f"{len(results['failed'])} 失败"
    )

    return results


def _build_ask_prompt(question: str, chunks: list[dict]) -> list[dict]:
    """构建混合 RAG 提示词：本地知识 + LLM 知识。"""
    system_prompt = """你是一个知识助手。请综合以下两个来源来回答用户问题:
1. 用户本地笔记中的相关内容 (见下文)
2. 你自己的通用知识

规则:
- 如果本地笔记有相关信息，优先引用，并注明来源文件路径
- 如果本地笔记没有覆盖的部分，用你自己的知识补充，并标注"[通用知识]"
- 不要编造本地笔记中不存在的内容
- 用中文回答"""

    user_parts = [question]
    if chunks:
        user_parts.append("\n---\n本地检索结果:")
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source_path", "unknown")
            user_parts.append(f"\n[来源 {i}: {source}]\n{chunk['text']}")
    else:
        user_parts.append(
            "\n(本地笔记中未找到相关内容，请使用你的通用知识回答)"
        )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def run_ask(
    question: str,
    config: dict,
    llm_override: str = None,
    embedding_override: str = None,
):
    """运行 RAG 问答流水线：检索 + 生成回答。

    Args:
        question: 用户问题。
        config: 完整配置字典。
        llm_override: 覆盖 LLM provider（如 "openai"）。
        embedding_override: 覆盖 embedding provider（如 "local"）。
    """
    top_k = config.get("retrieval", {}).get("top_k", 5)

    # 设置组件
    if embedding_override:
        embed_config = config.copy()
        embed_config["embedding"] = embed_config["embedding"].copy()
        embed_config["embedding"]["provider"] = embedding_override
        embedder = get_embedder(embed_config)
    else:
        embedder = get_embedder(config)

    store = VectorStore(
        persist_dir=config["storage"]["persist_dir"],
        collection_name=config["storage"]["collection_name"],
    )

    llm = get_llm(config, override_provider=llm_override)

    # 检查知识库是否为空
    if store.count() == 0:
        console.print(
            "[yellow]知识库为空。请先执行 doubase ingest 导入笔记。[/yellow]"
        )
        console.print("[dim]将仅使用 LLM 自身知识回答...[/dim]")
        chunks = []
    else:
        # 检索
        retriever = Retriever(embedder=embedder, vector_store=store)
        chunks = retriever.retrieve(question, top_k=top_k)

        if not chunks:
            console.print(
                "[dim]本地笔记中未找到相关内容，将仅使用通用知识回答。[/dim]"
            )
        else:
            console.print(f"[dim]检索到 {len(chunks)} 个相关片段[/dim]")

    # 构建提示词
    messages = _build_ask_prompt(question, chunks)

    # 流式输出回答
    console.print()
    try:
        for token in llm.chat_stream(messages):
            console.print(token, end="", highlight=False)
        console.print()
    except Exception as e:
        console.print(f"\n[red]❌ LLM 调用失败: {e}[/red]")
        console.print("[dim]请检查网络连接和 API Key 配置。[/dim]")


def estimate_analyze(project_dir: str, config: dict, focus: str = None) -> dict:
    """估算项目分析的费用（不调用任何付费 API）。"""
    files = scan_project(project_dir, focus=focus)
    llm_provider = config["llm"]["provider"]
    pricing = config.get("pricing", {}).get(llm_provider, {})
    input_price = pricing.get("input_price", 1.0)
    output_price = pricing.get("output_price", 2.0)
    embed_price = (
        config.get("pricing", {}).get("zhipu", {}).get("embed_price", 0.5)
    )

    chunker = Chunker(config.get("chunker", {}))
    total_llm_input = 0
    total_llm_output = 0
    file_estimates = []

    for f in files:
        code_tokens = len(chunker._encode(f["content"]))
        input_tokens = 200 + code_tokens
        output_tokens = int(input_tokens * 0.3)
        total_llm_input += input_tokens
        total_llm_output += output_tokens
        file_estimates.append({
            "path": f["path"],
            "size_kb": round(len(f["content"]) / 1024, 1),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        })

    synthesis_input = total_llm_output + 2000
    synthesis_output = 2000
    total_llm_input += synthesis_input
    total_llm_output += synthesis_output

    llm_cost = (
        total_llm_input * input_price + total_llm_output * output_price
    ) / 1_000_000

    total_embed_tokens = total_llm_output
    embed_cost = total_embed_tokens / 1_000_000 * embed_price

    return {
        "project_dir": project_dir,
        "project_name": Path(project_dir).name,
        "total_files": len(file_estimates),
        "scanned_total": len(files),
        "file_estimates": file_estimates,
        "total_llm_input": total_llm_input,
        "total_llm_output": total_llm_output,
        "llm_cost": llm_cost,
        "total_embed_tokens": total_embed_tokens,
        "embed_cost": embed_cost,
        "total_cost": llm_cost + embed_cost,
        "llm_provider": llm_provider,
        "llm_model": config["llm"][llm_provider]["model"],
        "embedding_provider": config["embedding"]["provider"],
    }


def display_analyze_estimate(estimate: dict):
    """展示 analyze 费用估算表格。"""
    console.print()
    console.print("[bold]═══ Analyze 预算估算 ═══[/bold]")
    console.print(f"项目: {estimate['project_name']}")
    console.print(
        f"源码文件: {estimate['scanned_total']} 个 -> "
        f"重要性排序后选取 {estimate['total_files']} 个"
    )
    console.print(
        f"LLM: {estimate['llm_provider']} ({estimate['llm_model']}) | "
        f"Embedding: {estimate['embedding_provider']}"
    )

    console.print("\n[bold]—— LLM 分析花费 ——[/bold]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("文件", style="dim")
    table.add_column("代码量", justify="right")
    table.add_column("预估输入", justify="right")
    table.add_column("预估输出", justify="right")
    table.add_column("费用", justify="right")

    total_file_tokens = sum(
        fe["input_tokens"] + fe["output_tokens"]
        for fe in estimate["file_estimates"]
    )
    for fe in estimate["file_estimates"][:20]:
        proportion = (fe["input_tokens"] + fe["output_tokens"]) / max(1, total_file_tokens)
        file_cost = estimate["llm_cost"] * proportion * 0.85
        table.add_row(
            fe["path"][-50:],
            f"{fe['size_kb']} KB",
            f"{fe['input_tokens']:,} tk",
            f"{fe['output_tokens']:,} tk",
            f"¥{file_cost:.4f}",
        )

    if len(estimate["file_estimates"]) > 20:
        table.add_row("...", "...", "...", "...", "...")

    table.add_section()
    table.add_row(
        "[bold]LLM 小计[/bold]",
        "-",
        f"[bold]{estimate['total_llm_input']:,} tk[/bold]",
        f"[bold]{estimate['total_llm_output']:,} tk[/bold]",
        f"[bold]¥{estimate['llm_cost']:.4f}[/bold]",
    )
    console.print(table)

    console.print(f"\n[bold]—— Embedding 入库花费 ——[/bold]")
    console.print(
        f"生成 .md 总结 -> 约 {estimate['total_embed_tokens']:,} tokens -> "
        f"¥{estimate['embed_cost']:.4f}"
    )

    total = estimate['total_cost']
    console.print(
        f"\n[bold green]💰 总花费预估: ¥{total:.4f} "
        f"(LLM ¥{estimate['llm_cost']:.4f} + Embedding ¥{estimate['embed_cost']:.4f})"
        f"[/bold green]"
    )


def run_analyze(
    project_dir: str,
    config: dict,
    focus: str = None,
    skip_confirm: bool = False,
):
    """运行完整的 analyze 流水线：扫描 -> 分析 -> 写入 -> 入库。

    Args:
        project_dir: 待分析项目路径。
        config: 完整配置字典。
        focus: 可选的优先子目录。
        skip_confirm: True 时跳过确认提示。
    """
    from doubase.analyzer.analyzer import analyze_file, synthesize_overview
    from doubase.analyzer.writer import write_summary, write_overview

    # 阶段 1: 估算
    estimate = estimate_analyze(project_dir, config, focus)
    display_analyze_estimate(estimate)

    # 阶段 2: 确认
    if not skip_confirm:
        try:
            answer = input("\n是否继续? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]已取消[/yellow]")
            return
        if answer and answer not in ("y", "yes"):
            console.print("[yellow]已取消[/yellow]")
            return

    # 阶段 3: 执行
    project_name = Path(project_dir).expanduser().resolve().name
    output_dir = str(
        Path(project_dir).expanduser().resolve().parent / "doubase_summaries"
    )
    project_source = str(Path(project_dir).expanduser().resolve())

    files = scan_project(project_dir, focus=focus)
    llm = get_llm(config)

    console.print(f"\n[bold]分析 {len(files)} 个文件...[/bold]")

    file_analyses = []
    success_count = 0
    fail_count = 0

    for i, f in enumerate(files, 1):
        console.print(f"  [{i}/{len(files)}] {f['path'][-60:]}")
        try:
            analysis = analyze_file(
                llm, f["path"], f["content"], f["language"]
            )
            write_summary(
                output_dir, project_name, project_source,
                f["path"], f["language"], analysis,
            )
            file_analyses.append({"file": f["path"], "analysis": analysis})
            success_count += 1
        except Exception as e:
            console.print(f"    [red]❌ 失败: {e}[/red]")
            fail_count += 1
            continue

    # 综述
    console.print(f"\n[bold]生成项目综述...[/bold]")
    try:
        overview = synthesize_overview(llm, project_name, file_analyses)
        overview_path = write_overview(
            output_dir, project_name, project_source, overview
        )
        console.print(f"  ✅ 综述已保存: {overview_path}")
    except Exception as e:
        console.print(f"  [red]❌ 综述生成失败: {e}[/red]")

    # 将分析结果入库
    console.print(f"\n[bold]将分析结果导入知识库...[/bold]")
    summary_dir = Path(output_dir) / project_name
    if summary_dir.exists():
        summary_files = list(summary_dir.glob("*.md"))
        if summary_files:
            try:
                run_ingest(
                    [str(s) for s in summary_files], config, skip_confirm=True
                )
            except Exception as e:
                console.print(f"  [red]❌ 导入失败: {e}[/red]")

    console.print(f"\n[bold]doubase analyze 结果:[/bold]")
    console.print(f"  ✅ 分析成功: {success_count} 个文件")
    if fail_count:
        console.print(f"  ❌ 分析失败: {fail_count} 个文件")
    console.print(f"  📁 总结文件: {output_dir}/{project_name}/")
