# DouBase Agent — 设计文档

> 创建日期: 2026-06-26  
> 状态: 设计中 → 待评审

## 1. 项目概述

DouBase 是一个本地运行的 CLI 工具，具备两大核心能力：

1. **RAG 知识问答** — 检索本地的 Markdown/Word/PDF 笔记，结合 LLM 自身知识，混合回答用户问题
2. **代码分析入库** — 分析外部项目源码，生成关键代码与算法总结的 Markdown 文件，向量化存入知识库

### 1.1 目标用户

个人使用，管理 Obsidian 笔记 + 学习/复习开源项目代码。

### 1.2 部署形式

- Python CLI 工具，终端交互
- 所有数据本地存储（向量库、总结文件）

---

## 2. 架构决策

### 2.1 架构模式：Pipeline 分阶段模块化

数据流拆为独立管道阶段，每个阶段是一个可替换的模块：

```
Ingest → Chunk → Embed → Store → Retrieve → Generate
```

### 2.2 技术选型总览

| 维度 | 选择 | 原因 |
|------|------|------|
| 语言 | Python | RAG 生态最成熟 |
| 向量数据库 | ChromaDB | 嵌入式零运维，个人规模够用 |
| LLM 默认 | DeepSeek API | 国产便宜，中文好 |
| Embedding 默认 | 智谱 (Zhipu) API Embedding | 国产，embedding-2 模型，中文效果好 |
| LLM 扩展 | OpenAI / OpenAI 兼容 API | 可切换 |
| Embedding 扩展 | 本地模型 (BGE / Ollama) | 可切换节省费用 |
| RAG 框架 | 自研轻量 | 避免框架依赖过重 |
| 文档解析 | python-docx, PyMuPDF | 成熟稳定 |

---

## 3. 项目结构

```
DouBase/
├── doubase/                    # 主包
│   ├── __init__.py
│   ├── cli.py                  # CLI 入口 (argparse)
│   ├── config.py               # 配置管理 (YAML 加载 + 环境变量解析)
│   │
│   ├── parsers/                # 文档解析层
│   │   ├── base.py             # Parser 抽象接口
│   │   ├── markdown.py         # .md (清洗 frontmatter，保持正文)
│   │   ├── docx.py             # .docx → Markdown 文本
│   │   └── pdf.py              # .pdf → Markdown 文本
│   │
│   ├── chunker/                # 文本切分层
│   │   └── chunker.py          # 滑动窗口分块 (512 tokens, 64 overlap)
│   │
│   ├── embedding/              # 向量化层
│   │   ├── base.py             # Embedder 抽象接口
│   │   ├── zhipu.py            # 智谱 Embedding API (默认)
│   │   └── local.py            # 本地模型 (sentence-transformers)
│   │
│   ├── storage/                # 存储层
│   │   └── vector_store.py     # ChromaDB 封装 (增删查 + 去重)
│   │
│   ├── retrieval/              # 检索层
│   │   └── retriever.py        # 查询向量化 → top-K 相似度召回
│   │
│   ├── generation/             # 生成层
│   │   ├── base.py             # LLM 抽象接口
│   │   ├── deepseek.py         # DeepSeek Chat API
│   │   └── openai_compat.py    # OpenAI / 其他兼容 API
│   │
│   └── analyzer/               # 代码分析子代理
│       ├── scanner.py          # 文件发现 + 重要性排序
│       ├── analyzer.py         # 调用 LLM 逐文件分析
│       └── writer.py           # 生成 Markdown 总结 + 触发入库
│
├── config.yaml                 # 默认配置
├── pyproject.toml              # 项目依赖与 CLI 入口
├── README.md
└── tests/                      # 测试
```

---

## 4. CLI 命令设计

### 4.1 命令

```bash
# RAG 问答（混合模式：本地笔记 + LLM 自身知识）
doubase ask "Redis 持久化原理是什么？"

# 文档导入（自动检测类型 .md/.docx/.pdf，先展示估算 → 确认后执行）
doubase ingest notes/ doc.pdf report.docx

# 跳过确认直接执行
doubase ingest notes/ --yes

# 监控目录自动导入（监控模式下新增文件直接处理，不询问）
doubase ingest --watch ~/Documents/inbox/

# 代码分析（全自动扫描，先展示估算 → 确认后执行）
doubase analyze ../some-project/

# 代码分析（跳过确认）
doubase analyze ../some-project/ --yes

# 代码分析（聚焦特定目录）
doubase analyze ../some-project/ --focus src/core/

# Provider 切换（命令行覆盖配置文件）
doubase ask "问题" --llm openai --embedding local
```

### 4.2 交互确认流程

`ingest` 和 `analyze` 命令的默认行为：先本地预扫描 → 展示花费估算 → 用户确认 → 执行。

```
doubase ingest notes/ doc.pdf
                │
                ▼
    ┌──────────────────────────┐
    │  本地预处理 (不调 API)     │
    │  - 解析文件               │
    │  - 分块统计               │
    │  - token 计数             │
    └────────┬─────────────────┘
             │
             ▼
    ╔══════════════════════════════════════╗
    ║  📊 Ingest 预算估算                   ║
    ║                                      ║
    ║  Embedding: zhipu (embedding-2)      ║
    ║  文件: 3 个   Chunks: 44             ║
    ║  Tokens: 17,600                      ║
    ║  💰 预估费用: ¥0.009                  ║
    ║                                      ║
    ║  是否继续? [Y/n]                      ║
    ╚══════════════════════════════════════╝
             │
        ┌────┴────┐
        ▼         ▼
       Y         n / Ctrl+C
        │         │
        ▼         ▼
   执行导入    取消操作
```

```bash
# 跳过确认，直接执行
doubase ingest notes/ --yes
doubase analyze ../project/ --yes
```

---

## 5. 数据流设计

### 5.1 文档入库流程 (Ingest Pipeline)

```
用户执行: doubase ingest notes/ doc.pdf
                │
                ▼
    ┌──────────────────────┐
    │  Parser Layer         │
    │  .md  → 清洗 frontmatter │
    │  .docx → Markdown 转换  │
    │  .pdf  → Markdown 转换  │
    │  输出: 纯文本 + 元数据    │
    └────────┬─────────────┘
             │ 纯文本
             ▼
    ┌──────────────────────┐
    │  增量检测 (Ingest 入口) │
    │  计算文件 SHA256 哈希   │
    │  查询 ChromaDB 中是否   │
    │  已存在同 source_path   │
    │  - 哈希相同 → 跳过      │
    │  - 哈希不同 → 先删旧    │
    │    再入新 chunk        │
    │  - 新文件 → 直接入库    │
    └────────┬─────────────┘
             │ 需要处理的新/变更文件
             ▼
    ┌──────────────────────┐
    │  Chunker              │
    │  滑动窗口 512 tokens   │
    │  重叠 64 tokens       │
    │  保留: 源路径, 文件哈希 │
    └────────┬─────────────┘
             │ chunks + metadata (含 content_hash)
             ▼
    ┌──────────────────────┐
    │  Embedder (智谱/本地)  │
    │  每 chunk → 向量      │
    └────────┬─────────────┘
             │ embeddings
             ▼
    ┌──────────────────────┐
    │  ChromaDB             │
    │  collection: "notes"  │
    │  每条 chunk 存储:      │
    │  - source_path        │
    │  - content_hash       │
    │  - indexed_at (时间戳) │
    │  下次 ingest 时对比哈希 │
    └──────────────────────┘
```

### 5.2 RAG 问答流程 (混合模式)

```
用户执行: doubase ask "Redis 持久化原理？"
                │
                ▼
    ┌──────────────────────┐
    │  Embedder (智谱/本地)  │
    │  问题 → query 向量     │
    └────────┬─────────────┘
             │
             ▼
    ┌──────────────────────┐
    │  ChromaDB             │
    │  相似度检索 top-K=5   │
    └────────┬─────────────┘
             │ K 个相关 chunk + 来源路径
             ▼
    ┌──────────────────────────────────────┐
    │  Prompt 组装                          │
    │                                       │
    │  系统提示:                             │
    │  "你是一个知识助手。请综合以下两个来源  │
    │   来回答用户问题:                      │
    │   1. 用户本地笔记中的相关内容 (见下文)   │
    │   2. 你自己的通用知识                  │
    │                                       │
    │   规则:                               │
    │   - 如果本地笔记有相关信息，优先引用，   │
    │     并注明来源文件                     │
    │   - 如果本地笔记没有覆盖的部分，用你自己的│
    │     知识补充，并标注'通用知识'          │
    │   - 不要编造本地笔记中不存在的内容      │
    │                                       │
    │   本地检索结果:                        │
    │   [Chunk 1] 来源: notes/redis.md      │
    │   [Chunk 2] 来源: notes/db.md         │
    │   ..."                               │
    └────────┬──────────────────────────────┘
             │ 完整 prompt
             ▼
    ┌──────────────────────┐
    │  LLM (DeepSeek)      │
    │  → 综合回答           │
    └────────┬─────────────┘
             │
             ▼
         终端输出答案 (含来源标注)
```

### 5.3 代码分析入库流程 (Analyze Pipeline)

```
用户执行: doubase analyze ../project/ --focus src/core/
                │
                ▼
    ┌──────────────────────────┐
    │  Scanner                  │
    │  1. 遍历目录，收集源码文件  │
    │  2. 排除: node_modules,    │
    │     .git, __pycache__,    │
    │     dist, build, vendor   │
    │  3. 重要性排序 (启发式)     │
    │  4. 截断至 top-50         │
    └────────┬─────────────────┘
             │ 排序后的文件列表
             ▼
    ┌──────────────────────────┐
    │  Analyzer (LLM)           │
    │  逐文件分析:               │
    │  - 核心算法 & 复杂度       │
    │  - 关键数据结构            │
    │  - 设计模式               │
    │  - 对外接口               │
    │  - 模块间依赖             │
    └────────┬─────────────────┘
             │ 逐文件分析结果
             ▼
    ┌──────────────────────────┐
    │  整体综述 (LLM)            │
    │  汇总所有文件分析 → 生成:   │
    │  - 项目架构概述           │
    │  - 核心算法一览           │
    │  - 模块间关系             │
    └────────┬─────────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Writer                   │
    │  生成 Markdown 总结文件:   │
    │  doubase_summaries/       │
    │  └── project-name/        │
    │      ├── overview.md      │
    │      ├── core.md          │
    │      └── ...              │
    └────────┬─────────────────┘
             │ .md 文件
             ▼
    ┌──────────────────────────┐
    │  复用 Ingest Pipeline      │
    │  Parser → Chunker →       │
    │  Embed → ChromaDB         │
    └──────────────────────────┘
```

### 5.4 Scanner 重要性排序启发式规则

```
权重计算（三项加权求和）:
  total_score = 0.3 * length_score + 0.4 * name_score + 0.3 * path_score

  其中:
  - length_score = len(file_content) / max_file_len_in_project  (归一化到 0-1)
  - name_score =  文件名匹配关键词:
      "algo" | "algorithm"  → 1.0
      "core"  | "engine"    → 0.9
      "main"                → 0.8
      "init"                → 0.5
      "utils" | "helper"    → 0.3
      其他                   → 0.5 (默认)
  - path_score = 目录路径匹配:
      "src/" | "lib/"       → 0.8
      项目根目录              → 0.6
      "tests/"              → 0.2
      其他                   → 0.5 (默认)

  - 截断: 按 total_score 降序取 top-50，超过 500 个文件时触发
  - --focus 参数: 将指定目录路径权重提升为 1.0，排序后优先选择
```

### 5.5 Watch 监控目录模式

```
doubase ingest --watch ~/Documents/inbox/
                │
                ▼
    ┌──────────────────────┐
    │  Watchdog             │
    │  - 使用 watchdog 库    │
    │  - 监听文件创建/修改    │
    │  - 防抖: 2秒内只触发一次 │
    │  - 只处理 .md/.docx/.pdf│
    └────────┬─────────────┘
             │ 新文件事件
             ▼
    → 复用 Ingest Pipeline
    → 处理成功 → 可选: 移动到 processed/ 目录
    → 处理失败 → 移动到 failed/ 目录 + 记录错误
```

### 5.6 费用估算与交互确认 (内置于 ingest/analyze)

`ingest` 和 `analyze` 默认先执行本地预处理 → 展示花费估算 → 用户确认 → 才调用付费 API。全程估算不调用任何 API。

```
doubase ingest notes/ doc.pdf  (或 doubase analyze ../project/)
                │
                ▼
    ┌──────────────────────────┐
    │  本地预处理 (不调 API)     │
    │  Ingest: 解析 + 分块 +    │
    │    统计 chunks & tokens   │
    │  Analyze: Scanner 扫描 +  │
    │    排序 + 逐文件 token 计 │
    │    数 + 估算 LLM 输出量    │
    └────────┬─────────────────┘
             │
             ▼
    ╔══════════════════════════════════╗
    ║  📊 预算估算                      ║
    ║                                  ║
    ║  (Ingest 示例)                    ║
    ║  Embedding: zhipu (embedding-2)  ║
    ║  文件: 3 个   Chunks: 44         ║
    ║  Tokens: 17,600                  ║
    ║  💰 预估费用: ¥0.009              ║
    ║                                  ║
    ║  是否继续? [Y/n]                  ║
    ╚══════════════════════════════════╝
             │
        ┌────┴────┐
        ▼         ▼
       Y         n / Ctrl+C
        │         │
        ▼         ▼
   执行导入    取消操作
   (调 API)
```

**详细估算输出示例：**

```
# Ingest 的估算输出:

═══ Ingest 预算估算 ═══
Embedding 提供商: zhipu (embedding-2)

┌──────────────────────────────────────────────────────────────┐
│ 文件                │ 大小    │ Chunks │ Tokens  │ 费用     │
├──────────────────────────────────────────────────────────────┤
│ notes/redis.md      │ 12 KB   │    8   │  3,200  │ ¥0.0016 │
│ notes/db.md         │ 18 KB   │   14   │  5,600  │ ¥0.0028 │
│ reports/doc.pdf     │ 45 KB   │   22   │  8,800  │ ¥0.0044 │
├──────────────────────────────────────────────────────────────┤
│ 合计                 │ 75 KB   │   44   │ 17,600  │ ¥0.0088 │
└──────────────────────────────────────────────────────────────┘

是否继续? [Y/n]

# Analyze 的估算输出:

═══ Analyze 预算估算 ═══
项目: my-project
源码文件: 234 个 → 重要性排序后选取 50 个
LLM: deepseek (deepseek-chat) | Embedding: zhipu (embedding-2)

—— LLM 分析花费 ——
┌──────────────────────────────────────────────────────────────┐
│ 文件                │ 代码量   │ 预估输入  │ 预估输出  │ 费用  │
├──────────────────────────────────────────────────────────────┤
│ src/core/engine.py  │ 8.2 KB  │ 2,100 tk │   630 tk │ ¥0.003│
│ src/core/router.py  │ 5.1 KB  │ 1,300 tk │   390 tk │ ¥0.002│
│ ...                 │ ...     │ ...      │ ...      │ ...   │
├──────────────────────────────────────────────────────────────┤
│ 综述                  │    —    │ 8,500 tk │ 2,000 tk │ ¥0.008│
├──────────────────────────────────────────────────────────────┤
│ LLM 小计              │   —    │78,000 tk │23,400 tk │ ¥0.12 │
└──────────────────────────────────────────────────────────────┘

—— Embedding 入库花费 ——
生成 .md 总结 50 个文件 → 约 120 chunks → 48,000 tokens → ¥0.024

═══════════════════════════════════════════════════════════
💰 总花费预估: ¥0.144 (LLM ¥0.12 + Embedding ¥0.024)
═══════════════════════════════════════════════════════════

是否继续? [Y/n]
```

**跳过确认：** 使用 `--yes` / `-y` 标志直接执行，不询问。

```bash
doubase ingest notes/ --yes
doubase analyze ../project/ --yes
```

定价表配置：

```yaml
# config.yaml 补充
pricing:
  deepseek:
    input_price: 1.0     # 元/百万 tokens
    output_price: 2.0    # 元/百万 tokens
  zhipu:
    embed_price: 0.5     # 元/百万 tokens (智谱 embedding-2)
  openai:
    input_price: 2.5     # GPT-4o 参考价
    output_price: 10.0
```

---

## 6. 配置设计

### 6.1 config.yaml

```yaml
# LLM 配置
llm:
  provider: deepseek          # deepseek | openai | openai_compat
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
    base_url: https://api.deepseek.com/v1
  openai:
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o
  openai_compat:              # 任意兼容 OpenAI 接口的第三方服务
    api_key: ${CUSTOM_API_KEY}   # (如 Ollama、vLLM、其他国产模型等)
    model: your-model
    base_url: https://your-api.com/v1

# Embedding 配置
embedding:
  provider: zhipu              # zhipu | local
  zhipu:
    api_key: ${ZHIPU_API_KEY}
    model: embedding-2
    base_url: https://open.bigmodel.cn/api/paas/v4
  local:
    model_name: BAAI/bge-small-zh-v1.5

# ChromaDB
storage:
  persist_dir: ~/.doubase/vectors
  collection_name: notes

# 文档切分
chunker:
  chunk_size: 512
  chunk_overlap: 64

# 检索
retrieval:
  top_k: 5

# 监控目录
watch:
  inbox_dir: ~/Documents/inbox

# 文件类型支持
parsers:
  enabled:
    - markdown
    - docx
    - pdf

# API 定价 (元/百万 tokens，用于费用估算)
pricing:
  deepseek:
    input_price: 1.0
    output_price: 2.0
  zhipu:
    embed_price: 0.5
  openai:
    input_price: 2.5
    output_price: 10.0
```

### 6.2 Provider 切换机制

代码层使用工厂函数，切换对上层透明：

```python
# 伪代码示意
def get_embedder(config) -> Embedder:
    provider = config["embedding"]["provider"]
    if provider == "zhipu":
        return ZhipuEmbedder(...)
    elif provider == "local":
        return LocalEmbedder(...)

def get_llm(config) -> LLM:
    provider = config["llm"]["provider"]
    if provider == "deepseek":
        return DeepSeekLLM(...)
    elif provider == "openai":
        return OpenAICompatLLM(...)
    elif provider == "openai_compat":
        return OpenAICompatLLM(...)
```

切换方式：
- 修改 `config.yaml` 中的 `provider` 字段
- 或通过 CLI 参数临时覆盖: `doubase ask "..." --llm openai`

环境变量 `${VAR_NAME}` 在加载配置时自动从环境变量解析。

---

## 7. 抽象接口

### 7.1 Parser 接口

```python
class BaseParser(ABC):
    """将文档解析为纯文本"""

    @abstractmethod
    def supports(self, file_path: str) -> bool:
        """检查是否支持此文件类型"""
        ...

    @abstractmethod
    def parse(self, file_path: str) -> ParsedDocument:
        """解析文件，返回纯文本 + 元数据"""
        ...

class ParsedDocument:
    text: str
    source_path: str
    file_type: str       # "markdown" | "docx" | "pdf"
    metadata: dict       # 如 frontmatter, 页数, 作者等
```

### 7.2 Embedder 接口

```python
class BaseEmbedder(ABC):
    """文本 → 向量"""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化"""
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """单条查询向量化（某些模型有专门的 query 模式）"""
        ...
```

### 7.3 LLM 接口

```python
class BaseLLM(ABC):
    """大语言模型调用"""

    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """发送消息，返回文本回复"""
        ...

    @abstractmethod
    def chat_stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """流式返回（CLI 打字效果）"""
        ...
```

---

## 8. 错误处理策略

### 8.1 Ingest 阶段

| 场景 | 策略 |
|------|------|
| 不支持的文件类型 | 跳过并警告，列出跳过的文件 |
| 文件未修改 (哈希匹配) | 跳过并在报告中标注 "⏭️ 跳过 (未变更)" |
| 文件读取失败 (权限/损坏) | 跳过并警告，继续处理其余文件 |
| Embedding API 失败 | 3 次指数退避重试，仍失败则跳过该 chunk |
| ChromaDB 写入失败 | 立即中止，提示用户检查磁盘空间 |

### 8.2 Ask 阶段

| 场景 | 策略 |
|------|------|
| 知识库为空 | 提示用户先执行 `doubase ingest` |
| 检索无相关结果 | 仅使用 LLM 自身知识回答，明确标注"本地笔记中未找到相关内容" |
| LLM API 超时/失败 | 重试 3 次，仍失败则提示用户检查网络和 API Key |

### 8.3 Analyze 阶段

| 场景 | 策略 |
|------|------|
| 单文件分析失败 | 跳过该文件，记录警告，不中断整体流程 |
| LLM API 调用失败 | 指数退避重试 3 次，失败后标记为 "pending"，最终报告列出失败文件 |
| 项目过大 (>500 源码文件) | 自动截断至 top-50，输出提示 |
| 指定目录不存在 | 立即中止，显示错误 |
| 缺定价配置 | 仍可估算 token 数，但费用显示 "N/A (请在 config.yaml 配置 pricing 段)"，确认后仍可继续 |

### 8.4 最终报告格式

每个命令执行完毕后输出总结：

```
doubase ingest 结果:
  ✅ 成功导入: notes/redis.md (12 chunks)
  ✅ 成功导入: reports/设计文档.pdf (8 chunks)
  ⏭️  跳过 (未变更): notes/old.md
  ⚠️  跳过 (不支持): data/notes.txt
  ❌ 失败: corrupt.docx (解析错误: 文件损坏)

  总计: 2 成功, 1 未变更, 1 跳过, 1 失败, 20 chunks 已入库
```

---

## 9. 生成的 Markdown 总结格式

每份代码分析总结统一使用以下模板，确保元数据完整，便于后续检索：

```markdown
---
project: my-project
source_path: /Users/xxx/projects/my-project
file: src/core/engine.py
analyzed_at: 2026-06-26T16:00:00
language: python
---

# engine.py — 消息引擎

## 概述
该模块是消息系统的核心引擎，负责消息的路由、分发和持久化。

## 核心算法
### 轮询分发 (Round-Robin Dispatch)
使用环形缓冲区实现消息的均匀分发，时间复杂度 O(1)...
（详细描述算法思路和步骤）

### 消息去重
基于 Bloom Filter 实现快速去重，误判率控制在 0.1%...

## 关键数据结构
- **MessageQueue**: 优先级队列，基于二叉堆实现
- **SubscriptionMap**: Hash 表 + 双向链表，支持 O(1) 订阅/取消

## 对外接口
| 方法 | 说明 |
|------|------|
| `dispatch(msg)` | 发送消息到目标队列 |
| `subscribe(topic, handler)` | 订阅主题 |

## 依赖
- `utils/serializer.py` — 消息序列化
- `storage/db.py` — 持久化层
```

---

## 10. 依赖项

```toml
# pyproject.toml (核心依赖)
[project]
name = "doubase"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "chromadb>=0.5.0",           # 向量数据库
    "openai>=1.0.0",             # LLM/Embedding API 客户端 (DeepSeek/智谱均兼容 OpenAI 接口)
    "python-docx>=1.0.0",        # Word 解析
    "PyMuPDF>=1.23.0",           # PDF 解析
    "tiktoken>=0.5.0",           # Token 计数 (分块 + dry-run 估算)
    "pyyaml>=6.0",               # 配置文件
    "watchdog>=4.0.0",           # 文件系统监控
    "sentence-transformers>=2.0.0", # 本地 Embedding (可选)
    "rich>=13.0.0",              # 终端美化输出
]
```

---

## 11. 考虑但暂不纳入 MVP 的功能

以下功能记录在案，但不在第一版实现范围：

1. **Web UI** — 未来可能加一个简单的 Web 界面，但不是 MVP
2. **混合搜索 (Hybrid Search)** — 关键词 + 向量联合检索，提高准确率
3. **重排序 (Re-ranking)** — 对召回结果二次排序
4. **多知识库** — 将笔记和代码总结分开为不同 collection
5. **对话历史/多轮对话** — 支持连续对话而非单次问答
6. **导出功能** — 将知识库导出为某种格式的打包文件

---

## 12. 测试策略

```
tests/
├── test_parsers/           # 各解析器单元测试
│   ├── test_markdown.py
│   ├── test_docx.py
│   └── test_pdf.py
├── test_chunker.py         # 分块逻辑测试
├── test_vector_store.py    # ChromaDB 读写测试
├── test_retriever.py       # 检索精度测试
├── test_generation.py      # LLM mock 测试
├── test_analyzer/          # 代码分析测试
│   └── fixtures/           # 模拟项目用于测试
└── test_cli.py             # CLI 集成测试
```

- Parser/Chunker/VectorStore 使用真实数据做单元测试
- LLM/Embedder 层用 mock 避免调用真实 API
- Analyzer 用小型 fixtures 项目测试扫描和分析流程

---

## 13. 变更记录

| 日期 | 变更 |
|------|------|
| 日期 | 变更 |
|------|------|
| 2026-06-26 | 初始版本，完成全部设计章节 |
| 2026-06-26 | 修正: Embedding 从 DeepSeek 改为智谱 (Zhipu) API，DeepSeek 不提供 Embedding 服务 |
| 2026-06-26 | 新增: 增量更新检测 (5.1)，基于 SHA256 哈希，未变更文件自动跳过 |
| 2026-06-26 | 新增: 费用估算 + 交互确认 (5.6)，ingest/analyze 默认先展示估算 → 用户确认后再执行，`--yes` 跳过确认 |
