# DouBase 查询优化 — 设计文档

> 创建日期: 2026-07-06
> 状态: 设计中 → 待评审

## 1. 目标

在已有记忆系统基础上增加两项查询优化：

1. **上下文补全** — LLM 利用对话记忆，将简短追问补全为完整语义（"它的优缺点？"→"RDB 持久化的优缺点？"）
2. **子问题拆解** — LLM 将复杂多问拆为独立子问题，各子问题分别检索后合并回答

两者均在 `run_ask` 内部、检索之前执行，对 REPL/CLI 透明。

## 2. 架构

```
run_ask(question, history):
       │
       ▼
┌──────────────────────┐
│  Phase 1: 上下文补全   │  仅当有 history 时执行
│  _rewrite_query()    │  LLM 判断是否需要补全
│  in: 原始问题 + 历史  │
│  out: 补全后的问题    │  (补全与否都继续 ↓)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Phase 2: 子问题拆解  │  独立执行，不依赖 Phase 1
│  _decompose_query()  │  LLM 独立判断是否需拆解
│  in: Phase1 结果      │
│  out: 1-N 个子问题    │
└──────────┬───────────┘
           │ N 个子问题
           ▼
┌──────────────────────┐
│  Phase 3: 各子问题检索 │  对每个子问题独立 Embed + Search
│  合并去重 chunks      │  去重策略: source_path + text 前缀
└──────────┬───────────┘
           │ 合并后的 chunks
           ▼
┌──────────────────────┐
│  Phase 4: LLM 回答    │  Prompt 中展示原始问题 + 子问题 + 检索结果
│  返回一个综合答案      │
└──────────────────────┘
```

## 3. 上下文补全 (Phase 1)

### 3.1 触发判断

LLM 一步完成"判断是否需要补全"和"输出补全后的问题"：

```
系统指令: 你是一个查询优化器。根据对话历史，判断用户当前问题是否需要上下文补全。

补全标准:
- 问题包含代词（它、这个、那个）→ 需要补全
- 问题是简短的追问（< 15 字）且依赖前文 → 需要补全
- 问题是独立的完整问题 → 不需要补全，直接返回原问题

输出格式: 仅输出最终问题文本，不要任何解释。
```

Phase 1 和 Phase 2 完全独立。无论补全与否，Phase 2 都会执行。

### 3.2 Prompt 模板

```python
REWRITE_PROMPT = """你是一个查询优化器。根据对话历史判断用户当前问题是否需要上下文补全。

补全条件（满足其一即补全）:
1. 问题包含代词（它、他、她、这个、那个、这些、那些）
2. 问题 < 15 字且依赖前文内容
3. 问题是简短的确认/追问（"为什么？""怎么做？""比如？"）

不需要补全: 问题是完整独立的疑问。

对话历史:
{history}

用户当前问题: {question}

{examples}

请输出最终问题文本（补全后或原问题），不要任何解释或额外文字。"""
```

### 3.3 示例

| 历史 | 输入 | 输出 |
|------|------|------|
| 聊 RDB 持久化 | "它有什么优缺点？" | "RDB 持久化有什么优缺点？" |
| 聊 Transformer | "注意力机制怎么算？" | "Transformer 的注意力机制怎么算？" |
| 无历史 | "Redis 是什么？" | "Redis 是什么？"（不需要补全） |

## 4. 子问题拆解 (Phase 2)

### 4.1 拆解逻辑

LLM 判断问题是否包含多个独立疑问，若是则拆分为子问题：

```python
DECOMPOSE_PROMPT = """判断以下问题是否包含多个独立子问题。如果包含，请拆分为独立子问题；否则返回原问题。

拆分标准:
- "A 和 B 的区别" → 拆成 "A 的特点"、"B 的特点"、"A 和 B 的对比"
- "X 是什么？怎么用？" → 拆成 "X 的定义"、"X 的使用方法"
- "为什么 Y？有什么影响？" → 拆成 "Y 的原因"、"Y 的影响"
- 单一问题 → 直接返回原问题

输出格式: 每个子问题一行，用数字编号。最多 {max_count} 个。
不需要任何解释。

问题: {question}"""
```

### 4.2 示例

| 输入 | 输出 |
|------|------|
| "Redis 是什么？" | `1. Redis 是什么？` |
| "RDB 和 AOF 的区别？" | `1. RDB 持久化的特点`<br>`2. AOF 持久化的特点`<br>`3. RDB 和 AOF 的对比` |
| "智能体有哪些组件？怎么交互的？"| `1. 智能体有哪些核心组件`<br>`2. 智能体组件之间如何交互` |

### 4.3 子问题结果合并

对 N 个子问题各自检索 top-K chunks，合并去重：

```python
all_chunks = []
seen = set()
for sub_q in sub_questions:
    q_vector = embedder.embed_query(sub_q)
    chunks = store.search(q_vector, top_k=top_k)
    for c in chunks:
        key = (c["source_path"], c["text"][:50])  # 去重
        if key not in seen:
            seen.add(key)
            all_chunks.append(c)

# 按 distance 排序，取 top 2*top_k 个
all_chunks.sort(key=lambda c: c["distance"])
all_chunks = all_chunks[:top_k * 2]
```

## 5. Prompt 变更

### 5.1 _build_ask_prompt 新增参数

```python
def _build_ask_prompt(
    question: str,
    chunks: list[dict],
    history: list[dict] = None,
    original_question: str = None,     # 新增: 用户原始问题
    sub_questions: list[str] = None,   # 新增: 拆解出的子问题列表
) -> list[dict]:
```

当存在 sub_questions 时，在 system prompt 中增加拆解信息：

```
系统提示:
...
[查询优化] 用户原始问题: "RDB 和 AOF 的区别是什么？"
已拆解为以下子问题分别检索了知识库:
1. RDB 持久化的特点
2. AOF 持久化的特点
3. RDB 和 AOF 的对比

请综合以下所有检索结果，给出一个完整的回答，覆盖每个子问题。
```

### 5.2 run_ask 流程伪代码

```python
def run_ask(question, config, ..., history=None):
    llm = get_llm(config)
    opt_config = config.get("query_optimization", {})
    original_question = question
    sub_questions = None
    rewrite_token_cost = 0
    decompose_token_cost = 0
    
    # Phase 1: 上下文补全（独立执行，仅在有历史时）
    if history and opt_config.get("context_rewrite", True):
        rewritten = _rewrite_query(question, history, llm)
        if rewritten and rewritten != question:
            question = rewritten
    
    # Phase 2: 子问题拆解（独立执行，不依赖 Phase 1 结果）
    if opt_config.get("decompose", True):
        max_count = opt_config.get("decompose_max", 3)
        sub_questions = _decompose_query(question, llm, max_count)
        if sub_questions and len(sub_questions) > 1:
            # 各子问题独立检索 + 合并
            ...
        else:
            sub_questions = None
    
    # 正常检索（单问题或合并后）
    if sub_questions is None:
        # 原有单问题检索逻辑
        retriever = Retriever(embedder, store)
        chunks = retriever.retrieve(question, top_k)
    else:
        # 子问题结果已合并为 chunks
        pass
    
    # Phase 4: 回答
    messages = _build_ask_prompt(
        question, chunks, history=history,
        original_question=original_question,
        sub_questions=sub_questions,
    )
    ...
```

## 6. 费用估算更新

`estimate_ingest` 不受影响（ingest 不涉及查询优化）。

查询优化增加的费用（每次 ask）：
- 上下文补全: ~200 tokens prompt + ~30 tokens 输出 ≈ ¥0.0003
- 子问题拆解: ~200 tokens prompt + ~50 tokens 输出 ≈ ¥0.0004
- 总增加 < ¥0.001 / 次

## 7. 新增文件

`doubase/query_optimizer.py` — 两个独立函数：

```python
def rewrite_query(question: str, history: list[dict], llm: BaseLLM) -> str:
    """LLM 判断并补全问题上下文。返回补全后的问题（或原问题）。"""
    ...

def decompose_query(question: str, llm: BaseLLM, max_count: int = 3) -> list[str]:
    """LLM 拆解复杂问题为子问题列表。只有 1 个时返回单元素列表。"""
    ...
```

## 8. 测试策略

- `tests/test_query_optimizer.py` — mock LLM 测试 rewrite / decompose
- `tests/test_pipeline.py` 追加 — 测试 `_build_ask_prompt` with sub_questions
- 手动 REPL 测试多轮追问 + 复杂问题拆解

## 9. 配置

```yaml
# config.yaml 新增
query_optimization:
  context_rewrite: true    # 上下文补全（需多轮记忆）
  decompose: true          # 子问题拆解
  decompose_max: 3         # 最多拆成几个子问题
```

## 10. 总结

| 维度 | 决策 |
|------|------|
| 上下文补全触发 | LLM 判断（一步完成判断+补全） |
| 子问题拆解 | LLM 判断是否多问，拆分为 1-N 个子问题 |
| 子问题检索 | 各独立检索 top-K，合并去重 |
| 回答方式 | 所有子问题结果汇总到一个综合回答 |
| 新增文件 | `query_optimizer.py` |
| Pipeline 改动 | `run_ask` 增加 Phase 1-4 流程 |
| 费用增加 | < ¥0.001 / 次 |

## 11. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-06 | 初始版本 |
