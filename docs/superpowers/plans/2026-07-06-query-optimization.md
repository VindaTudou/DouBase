# 查询优化 — 实现计划

> **目标：** 新增上下文补全 + 子问题拆解，提升 RAG 检索精度。两阶段独立执行，各自 LLM 判断。

**架构：** 新增 `doubase/query_optimizer.py`（`rewrite_query` + `decompose_query`），`pipeline.py` 中 `run_ask` 在检索前插入 Phase 1（补全）和 Phase 2（拆解）。拆解时各子问题独立检索，合并去重后综合回答。

**技术栈：** Python >=3.11

## 全局约束

- Python >=3.11（`/opt/homebrew/bin/python3.11`）
- 现有 75 个测试不能破坏
- Phase 1（上下文补全）仅在有对话历史时执行
- Phase 2（子问题拆解）独立于 Phase 1，无论补全与否都执行
- 补全/拆解的 LLM 调用失败时优雅降级（使用原问题继续）
- 新增配置项 `query_optimization` 在 `config.yaml` 中

---

### 任务 1: query_optimizer.py + 测试

**文件:**
- 创建: `doubase/query_optimizer.py`
- 创建: `tests/test_query_optimizer.py`

**接口:**
- 产出: `rewrite_query(question: str, history: list[dict], llm: BaseLLM) -> str` — 返回补全后的问题（或原问题）
- 产出: `decompose_query(question: str, llm: BaseLLM, max_count: int = 3) -> list[str]` — 返回子问题列表（至少 1 个）

- [ ] **步骤 1: 编写测试**

创建 `tests/test_query_optimizer.py`:

```python
from unittest.mock import MagicMock
from doubase.query_optimizer import rewrite_query, decompose_query


def test_rewrite_query_with_pronoun():
    """包含代词 → 应补全"""
    history = [
        {"role": "user", "content": "Redis 持久化是什么？"},
        {"role": "assistant", "content": "Redis 有 RDB 和 AOF 两种持久化方式。"},
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "RDB 持久化有什么优缺点？"

    result = rewrite_query("它有什么优缺点？", history, mock_llm)
    mock_llm.chat.assert_called_once()
    assert "RDB" in result


def test_rewrite_query_complete_question():
    """完整独立问题 → LLM 返回原问题"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "Redis 是什么？"

    result = rewrite_query("Redis 是什么？", [], mock_llm)
    result = rewrite_query("Redis 是什么？", [], mock_llm)
    assert "Redis" in result


def test_rewrite_no_history_skips_llm():
    """无历史 → 不调 LLM，直接返回原问题"""
    mock_llm = MagicMock()
    result = rewrite_query("它怎么样？", [], mock_llm)
    mock_llm.chat.assert_not_called()
    assert result == "它怎么样？"


def test_decompose_simple_question():
    """单问题 → 返回单元素列表"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "1. Redis 是什么？"
    result = decompose_query("Redis 是什么？", mock_llm)
    assert len(result) == 1


def test_decompose_multi_question():
    """多问题 → 拆解为子问题列表"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = (
        "1. RDB 持久化的特点\n"
        "2. AOF 持久化的特点\n"
        "3. RDB 和 AOF 的对比"
    )
    result = decompose_query("RDB 和 AOF 的区别？", mock_llm, max_count=3)
    assert len(result) == 3
    assert any("RDB" in r for r in result)
    assert any("AOF" in r for r in result)


def test_decompose_empty_response_falls_back():
    """LLM 返回空 → 回退到原问题"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = ""
    result = decompose_query("test question", mock_llm)
    assert result == ["test question"]


def test_decompose_llm_error_falls_back():
    """LLM 调用失败 → 回退到原问题"""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = Exception("API error")
    result = decompose_query("RDB 和 AOF 的区别？", mock_llm)
    assert result == ["RDB 和 AOF 的区别？"]
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/test_query_optimizer.py -v`
预期: FAIL — 模块未找到

- [ ] **步骤 3: 编写实现**

创建 `doubase/query_optimizer.py`:

```python
"""查询优化 — 上下文补全 + 子问题拆解。"""

from doubase.generation.base import BaseLLM

REWRITE_PROMPT = """你是一个查询优化器。根据对话历史判断用户当前问题是否需要上下文补全。

补全条件（满足其一即补全）:
1. 问题包含代词（它、他、她、这个、那个、这些、那些）
2. 问题 < 15 字且依赖前文内容
3. 问题是简短的确认/追问（"为什么？""怎么做？""比如？"）

不需要补全: 问题是完整独立的疑问。

对话历史:
{history}

用户当前问题: {question}

请输出最终问题文本（补全后或原问题），不要任何解释或额外文字。"""

DECOMPOSE_PROMPT = """判断以下问题是否包含多个独立子问题。如果包含，请拆分为独立子问题；否则返回原问题。

拆分标准:
- "A 和 B 的区别" → 拆成 "A 的特点"、"B 的特点"、"A 和 B 的对比"
- "X 是什么？怎么用？" → 拆成 "X 的定义"、"X 的使用方法"
- "为什么 Y？有什么影响？" → 拆成 "Y 的原因"、"Y 的影响"
- 单一问题 → 直接返回原问题

输出格式: 每个子问题一行，用数字编号。最多 {max_count} 个。
不需要任何解释。

问题: {question}"""


def rewrite_query(question: str, history: list[dict], llm: BaseLLM) -> str:
    """LLM 利用对话历史补全问题上下文。

    Args:
        question: 用户原始问题。
        history: 对话历史 [{role, content}, ...]。
        llm: LLM 实例。

    Returns:
        补全后的问题。无历史时返回原问题。
    """
    # 无历史 → 不需要补全
    if not history:
        return question

    # 格式化历史
    history_text = "\n".join(
        f"[{h['role']}]: {h['content'][:200]}" for h in history
    )
    prompt = REWRITE_PROMPT.format(
        question=question,
        history=history_text,
    )
    try:
        rewritten = llm.chat([{"role": "user", "content": prompt}]).strip()
        return rewritten if rewritten else question
    except Exception:
        return question


def decompose_query(question: str, llm: BaseLLM, max_count: int = 3) -> list[str]:
    """LLM 拆解复杂问题为独立子问题。

    Args:
        question: 用户问题（可能已经过上下文补全）。
        llm: LLM 实例。
        max_count: 最多拆几个子问题。

    Returns:
        子问题列表，至少 1 个元素。
    """
    prompt = DECOMPOSE_PROMPT.format(
        question=question,
        max_count=max_count,
    )
    try:
        reply = llm.chat([{"role": "user", "content": prompt}]).strip()
        if not reply:
            return [question]

        # 解析编号列表: "1. xxx\n2. yyy\n3. zzz"
        lines = reply.split("\n")
        sub_questions = []
        import re
        for line in lines:
            # 匹配 "1. " "1) " "1、" 等格式
            m = re.match(r"\d+[\.\)、]\s*(.+)", line.strip())
            if m:
                sub_questions.append(m.group(1).strip())
        return sub_questions if sub_questions else [question]
    except Exception:
        return [question]
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/test_query_optimizer.py -v`
预期: 7 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/query_optimizer.py tests/test_query_optimizer.py
git commit -m "feat: add query optimizer with context rewrite and question decomposition"
```

---

### 任务 2: Pipeline 集成 Phase 1+2

**文件:**
- 修改: `doubase/pipeline.py` — `run_ask` 中在检索前插入 Phase 1 和 Phase 2

**接口:**
- 消耗: `rewrite_query`, `decompose_query`, 现有检索逻辑
- 产出: 更新后的 `run_ask` — 补全 → 拆解 → 各子问题检索合并 → 回答

- [ ] **步骤 1: 修改 run_ask**

读取 `doubase/pipeline.py`，在 `run_ask` 函数体中，找到检索逻辑（`messages = _build_ask_prompt(...)` 之前），插入 Phase 1+2。修改具体位置：在 `llm = get_llm(...)` 行**之后**，在 `# 检索` 注释**之前**。

替换掉现有的检索前逻辑（`# 检查知识库是否为空` + `# 检索` 的两段），改为：

```python
    # --- Phase 1: 上下文补全 ---
    opt_config = config.get("query_optimization", {})
    if history and opt_config.get("context_rewrite", True):
        from doubase.query_optimizer import rewrite_query
        rewritten = rewrite_query(question, history, llm)
        if rewritten and rewritten.strip() and rewritten != question:
            question = rewritten

    # --- Phase 2: 子问题拆解 ---
    sub_questions = None
    if opt_config.get("decompose", True):
        from doubase.query_optimizer import decompose_query
        max_count = opt_config.get("decompose_max", 3)
        sub_qs = decompose_query(question, llm, max_count)
        if len(sub_qs) > 1:
            sub_questions = sub_qs

    # --- 检索 ---
    if store.count() == 0:
        console.print(
            "[yellow]知识库为空。请先执行 doubase ingest 导入笔记。[/yellow]"
        )
        console.print("[dim]将仅使用 LLM 自身知识回答...[/dim]")
        chunks = []
    elif sub_questions:
        # 多子问题：各独立检索 + 合并去重
        all_chunks = []
        seen = set()
        for sub_q in sub_questions:
            retriever = Retriever(embedder=embedder, vector_store=store)
            sub_chunks = retriever.retrieve(sub_q, top_k=top_k)
            for c in sub_chunks:
                key = (c["source_path"], c["text"][:80])
                if key not in seen:
                    seen.add(key)
                    all_chunks.append(c)
        all_chunks.sort(key=lambda c: c["distance"])
        chunks = all_chunks[:top_k * 2]
        console.print(
            f"[dim]问题已拆解为 {len(sub_questions)} 个子问题, "
            f"检索到 {len(chunks)} 个去重片段[/dim]"
        )
    else:
        # 单问题：原有检索逻辑
        retriever = Retriever(embedder=embedder, vector_store=store)
        chunks = retriever.retrieve(question, top_k=top_k)

        if not chunks:
            console.print(
                "[dim]本地笔记中未找到相关内容，将仅使用通用知识回答。[/dim]"
            )
        else:
            console.print(f"[dim]检索到 {len(chunks)} 个相关片段[/dim]")
```

- [ ] **步骤 2: 更新 _build_ask_prompt 调用**

找到当前 `_build_ask_prompt` 调用行，在 `run_ask` 末尾附近的 `_build_ask_prompt(question, chunks, history=history)` 处，增加 `sub_questions` 提示。修改系统提示为动态：

不需要改 `_build_ask_prompt` 签名——直接在调用前根据 `sub_questions` 是否存在，给 history 追加一个 system 级别的拆解提示：

```python
    # 构建提示词前，如果存在拆解，在 prompt 中增加拆解信息
    if sub_questions:
        decompose_hint = (
            f"[查询优化] 用户原始问题: \"{original_question if 'original_question' in dir() else question}\"\n"
            f"已拆解为以下子问题分别检索知识库:\n" +
            "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_questions)) +
            "\n\n请综合所有检索结果，给出一个完整回答，覆盖每个子问题。"
        )
        # 将拆解提示追加到检索结果 chunk 最前面
        if chunks is None:
            chunks = []
        chunks.insert(0, {"text": "", "source_path": "", "distance": 0})
    ...
```

简化方案：在当前的 `_build_ask_prompt` 中，如果 chunks 非空，在 system prompt 中附加拆解信息。

找到 `_build_ask_prompt`（约第301行），在 `system_prompt` 定义之后，增加：

```python
    # 如果有子问题拆解，在系统提示中追加
    if history:
        # 检查 history 最后是否有拆解标记（由调用方追加的特殊 system 消息）
        pass  # 拆解信息通过 history 传入
```

实际上更简单的做法：**直接在 `run_ask` 中、`_build_ask_prompt` 返回之后，向 messages 中插入拆解信息**。

在 `messages = _build_ask_prompt(...)` 之后，追加：

```python
    # 子问题拆解提示
    if sub_questions:
        decompose_note = (
            f"[查询优化] 已拆解为以下子问题分别检索:\n"
            + "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_questions))
            + "\n请综合所有检索结果，给出一个完整回答。"
        )
        # 插入到 system message 之后、其他消息之前
        messages.insert(1, {"role": "system", "content": decompose_note})
```

- [ ] **步骤 3: 运行全量测试**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/ -q`
预期: 82 passed

- [ ] **步骤 4: 提交**

```bash
git add doubase/pipeline.py
git commit -m "feat: integrate Phase 1 (context rewrite) + Phase 2 (question decompose) into run_ask"
```

---

### 任务 3: Config 更新

**文件:**
- 修改: `config.yaml` — 添加 `query_optimization` 段

- [ ] **步骤 1: 更新 config.yaml**

在现有配置末尾追加：

```yaml
# 查询优化
query_optimization:
  context_rewrite: true    # 上下文补全（需多轮记忆）
  decompose: true          # 子问题拆解
  decompose_max: 3         # 最多拆成几个子问题
```

- [ ] **步骤 2: 确保 config 中 `query_optimization` 缺失时默认为 true**

在 `run_ask` 中已用 `config.get("query_optimization", {})` 兜底，缺失时不会崩溃。

- [ ] **步骤 3: 运行全量测试 + 端到端验证**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/ -q`
预期: 82 passed

端到端测试（需要 API key）:

```bash
printf "Redis 持久化是什么？\n它有什么优缺点？\n/exit\n" | doubase repl
```

预期：第二问能被补全为 RDB 相关优缺点。

```bash
printf "RDB 和 AOF 的区别是什么？\n/exit\n" | doubase repl
```

预期：问题被拆解，检索更多 chunks，综合回答。

- [ ] **步骤 4: 提交**

```bash
git add config.yaml
git commit -m "feat: add query_optimization config section"
```

---

## 实现注意事项

1. **Phase 1 + Phase 2 独立**: 无论补全是否改变问题，Phase 2 都执行
2. **降级策略**: 任何 LLM 调用失败 → 使用原问题继续，不影响正常问答
3. **子问题去重**: 用 `(source_path, text[:80])` 作为去重 key，避免不同子问题返回相同 chunks 导致冗余
4. **费用**: 每次 ask 额外消耗 ~500 tokens（补全 prompt + 拆解 prompt），约 ¥0.0005
