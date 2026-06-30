# DouBase Chunk 策略优化 — 设计文档

> 创建日期: 2026-06-30
> 状态: 设计中 → 待评审

## 1. 目标

将当前的纯滑动窗口分块替换为**三级分块策略**，提升 RAG 检索的语义完整性和准确率：

1. **按 `#` 标题切分** — 利用 Markdown 文档的层级结构，每个标题段落作为自然语义单元
2. **滑动窗口兜底** — 超长段落（token 数超过 chunk_size）用滑动窗口二次切分
3. **LLM 保守合并** — 同标题下被切分出的多个 chunk，由 LLM 判断语义相关性后合并

所有新增逻辑在 ingest 时默认执行，对 ask 流程无任何变动。

## 2. 三级分块流程

```
文档解析 (ParsedDocument)
       │
       ▼
┌──────────────────────────┐
│  Stage 1: 按 # 标题切分   │
│                          │
│  遍历文本，按 # 标题行    │
│  分割成 N 个段落           │
│  每个段落记录:             │
│    - heading_level (1-6) │
│    - heading_text        │
│    - body_text           │
│    - start_line          │
└────────┬─────────────────┘
         │ N 个标题段落
         ▼
┌──────────────────────────┐
│  Stage 2: 滑动窗口兜底    │
│                          │
│  对每个段落 body_text:    │
│    tokens > chunk_size   │
│    → 滑动窗口切分         │
│    tokens ≤ chunk_size   │
│    → 保持为单个 chunk     │
│                          │
│  每个 chunk 保留:         │
│    - heading_path (上下文)│
│    - source_path         │
│    - content_hash        │
└────────┬─────────────────┘
         │ M 个 chunks
         ▼
┌──────────────────────────┐
│  Stage 3: LLM 保守合并    │
│                          │
│  按标题分组: 同标题下     │
│     chunk 数 = 1 → 跳过   │
│     chunk 数 > 1 → 合并  │
│                          │
│  合并规则:                │
│    相邻 chunk pair →     │
│    LLM 判断语义相关?      │
│    是 → 合并              │
│    否 → 保持独立           │
└────────┬─────────────────┘
         │ K 个 chunks (K ≤ M)
         ▼
   Embedding → ChromaDB
```

## 3. 各阶段详细设计

### 3.1 Stage 1: 按 `#` 标题切分

在 `doubase/chunker/` 中新增 `heading_splitter.py`：

```python
@dataclass
class HeadingSection:
    heading_level: int        # 1-6
    heading_text: str         # 标题文本（不含 # 号）
    heading_path: list[str]   # 标题路径，如 ["智能体", "核心组件"]
    body_text: str            # 段落正文
    start_line: int           # 在原文件中的起始行号
```

**切分规则：**
- 从文件开头到第一个 `#` 标题之间的内容，视为 `heading_level=0, heading_path=[]` 的 preamble
- 遇到 `#` 标题行即开始新段落，当前段落结束
- 标题路径：维护一个栈，根据 heading_level 推入/弹出，确保每个段落携带完整父标题上下文
- `.md` 文件走此流程；`.docx`、`.pdf` 暂保持原有滑动窗口（无 Markdown 标题结构）

占位：`heading_path` 字段为未来检索阶段的上下文前缀预留。当前 MVP 不使用，但写入 chunk metadata 中。

### 3.2 Stage 2: 滑动窗口兜底

复用现有 `Chunker.chunk_text()` 的逻辑，但输入由整篇文档改为**单个标题段落的 body_text**：

```python
def chunk_section(section: HeadingSection, chunker: Chunker, 
                   source_path: str, content_hash: str) -> list[Chunk]:
    tokens = chunker._encode(section.body_text)
    if len(tokens) <= chunker.chunk_size:
        # 短段落：直接作为单个 chunk
        return [Chunk(
            text=section.body_text,
            source_path=source_path,
            chunk_index=0,  # 后续在全局编号
            content_hash=content_hash,
            metadata={
                "heading_path": section.heading_path,
                "heading_text": section.heading_text,
                "strategy": "heading",
            },
        )]
    else:
        # 长段落：滑动窗口切分，每个子 chunk 带 heading 上下文
        sub_chunks = chunker.chunk_text(
            section.body_text, source_path, content_hash
        )
        for c in sub_chunks:
            c.metadata = {
                "heading_path": section.heading_path,
                "heading_text": section.heading_text,
                "strategy": "sliding_window",
            }
        return sub_chunks
```

### 3.3 Stage 3: LLM 保守合并

新增 `doubase/chunker/semantic_merger.py`：

**合并范围：** 仅合并属于**同一个标题段落**的相邻 chunk（即 Stage 2 中被滑动窗口拆散的片段）。

```
# RDB 持久化            ← 标题 A
  Chunk A1: "RDB 介绍段落..."
  Chunk A2: "RDB 优点..."       ← A1/A2 同标题，需 LLM 判断
  Chunk A3: "RDB 配置方式..."   ← A2/A3 同标题，需 LLM 判断
# AOF 持久化            ← 标题 B
  Chunk B1: "AOF 完整描述"       ← B1 独立，无合并对象
```

**LLM 判断 prompt：**

```
以下两段文本来自同一篇文档的相邻段落。判断它们是否应该合并为一个语义单元。

合并标准：两段文本讨论同一主题的连续内容，合并后阅读流畅、逻辑连贯。
不合并标准：两段文本讨论不同方面、不同案例，各自独立存在更有意义。

文本 1:
{chunk_1_text}

文本 2:
{chunk_2_text}

请仅回复一个词：MERGE 或 KEEP_SEPARATE。
```

**调用策略：**
- 仅同标题下 chunk 数 > 1 时才调 LLM
- 相邻 chunk pair 逐个判断（A1+A2、A2+A3），可合并的串联起来合并
- 使用 DeepSeek（配置中的 LLM provider），token 消耗极低（prompt 简短 + 单 token 回复）

**费用估算更新：** `estimate_ingest()` 中增加 LLM 合并阶段的 token 估算。对 69 篇笔记，需要 LLM 介入的段落预计 < 10 处，总费用 < ¥0.01。

## 4. Chunk 数据结构更新

```python
@dataclass
class Chunk:
    text: str
    source_path: str
    chunk_index: int
    content_hash: str
    metadata: dict = field(default_factory=dict)
    # metadata 新增:
    #   heading_path: list[str]  标题层级路径
    #   heading_text: str        所属标题文本
    #   strategy: str            生成策略: "heading" | "sliding_window" | "merged"
```

`VectorStore` 中 metadata 字段自动支持新增属性，无需修改存储层。

## 5. Pipeline 变更

### 5.1 Ingest 流程

`run_ingest()` 中 `chunk_text()` 调用替换为新的三级流程：

```python
# 旧: chunks = chunker.chunk_text(doc.text, file_path, content_hash)
# 新:
sections = split_by_headings(doc.text)  # Stage 1
raw_chunks = []
for section in sections:
    raw_chunks.extend(chunk_section(section, chunker, file_path, content_hash))
# 全局编号
for i, c in enumerate(raw_chunks):
    c.chunk_index = i
chunks = merge_semantically(raw_chunks, llm)  # Stage 3
```

### 5.2 Ask 流程

无变更。检索时返回的 chunk metadata 中包含 `heading_path`，Prompt 组装时可选展示。

### 5.3 Estimate 流程

`estimate_ingest()` 同步更新以反映 Stage 3 的 LLM 合并费用。

## 6. 配置

```yaml
# config.yaml 新增（可选覆盖默认值）
chunker:
  chunk_size: 512
  chunk_overlap: 64
  heading_split: true           # 是否启用 # 标题切分（默认 true）
  semantic_merge: true          # 是否启用 LLM 合并（默认 true）
  semantic_merge_model: default # 合并使用的 LLM，默认跟随主 LLM provider
```

## 7. 测试策略

- `test_heading_splitter.py` — 用带多级标题的 fixture `.md` 测试标题切分
- `test_semantic_merger.py` — mock LLM 回复 "MERGE" / "KEEP_SEPARATE" 测试合并逻辑
- 现有 `test_chunker.py`、`test_pipeline.py` 保持不变（滑动窗口逻辑未变）
- 集成测试：一篇包含短段落 + 长段落的 `.md` 文件，end-to-end 测试三级流程

## 8. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-30 | 初始版本 |
