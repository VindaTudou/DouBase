# DouBase 🧠

本地 RAG CLI 工具，用于个人知识管理与代码分析。

## 功能

- **RAG 问答** — 提问，结合本地笔记 + LLM 知识给出混合回答
- **交互式 REPL** — 进入对话模式，直接输入问题，支持 `/` 命令操作
- **多轮对话记忆** — 自动记忆对话上下文，支持追问，超限自动摘要压缩
- **查询优化** — LLM 上下文补全（代词消解）+ 复杂问题子问题拆解 + RAG 门控判断（避免无意义检索）
- **混合检索** — 向量相似度 + 关键词命中率加权融合 → LLM 精排序，三层漏斗提升召回质量
- **智能分块** — 三级策略：Markdown `#` 标题语义切分 → 滑动窗口兜底 → LLM 保守合并
- **API 重试** — 指数退避自动重试（429/5xx/超时），确保 API 临时故障不中断
- **文档导入** — 导入 `.md`、`.docx`、`.pdf` 文件到 ChromaDB 向量库，SHA256 增量去重
- **代码分析** — 分析外部项目，自动生成 Markdown 总结并入库
- **费用估算** — 调用 API 前展示预估，确认后执行
- **监控模式** — 自动导入放入监控目录的新文件
- **提供商切换** — LLM（DeepSeek/OpenAI/兼容）和 Embedding（ZhipuAI/本地）可配置切换

## 快速开始

### 1. 安装

```bash
cd DouBase
pip install -e .

# 可选：本地 embedding 模型
pip install -e ".[local-embed]"
```

### 2. 设置 API Key

复制模板文件并填入你的 Key：

```bash
cp .env.example .env
```

然后编辑 `.env` 文件：

```env
# 选择 LLM 和 Embedding 提供商
DOUBASE_LLM_PROVIDER=deepseek          # deepseek / openai / openai_compat
DOUBASE_EMBEDDING_PROVIDER=zhipu       # zhipu / local

# DeepSeek（LLM）
DOUBASE_DEEPSEEK_API_KEY=sk-你的-key
DOUBASE_DEEPSEEK_MODEL=deepseek-chat

# 智谱（Embedding）
DOUBASE_ZHIPU_API_KEY=你的-key
DOUBASE_ZHIPU_MODEL=embedding-2
```

> `.env` 文件已在 `.gitignore` 中排除，不会被提交到仓库。

### 3. 导入你的笔记

```bash
# 导入整个目录
doubase ingest ~/Documents/Obsidian/

# 导入特定文件
doubase ingest notes.md report.docx paper.pdf

# 跳过确认
doubase ingest ~/notes/ --yes

# 监控目录，自动导入新文件
doubase ingest --watch ~/Documents/inbox/
```

### 4. 提问

```bash
doubase ask "Redis 持久化原理是什么？"
doubase ask "什么是梯度下降？"
doubase ask "解释 Transformer 注意力机制" --llm openai
```

### 5. 分析代码项目

```bash
doubase analyze ~/projects/some-repo/
doubase analyze ~/projects/some-repo/ --focus src/core/
doubase analyze ~/projects/some-repo/ --yes
```

### 6. 交互式对话（推荐）

```bash
doubase repl                 # 新会话
doubase repl --resume        # 加载上次会话（继续之前的对话）
doubase repl --new           # 强制新会话
```

进入对话模式后：
- 直接输入问题即可提问，回答流式输出 + Markdown 渲染
- 多轮对话自动记忆，支持追问（"它有什么优缺点？"→ 自动补全上下文）
- `/ingest <路径>`   导入文档到知识库
- `/analyze <项目>`  分析代码项目
- `/clear`           清空对话记忆
- `/help`            查看可用命令
- `/exit`            退出（自动保存记忆）

闲置 30 秒自动显示命令提示。

## 配置

**API Key、模型选择、Provider 切换**全部在 `.env` 文件中管理：

```env
# 切换 LLM 提供商
DOUBASE_LLM_PROVIDER=openai

# 切换模型
DOUBASE_DEEPSEEK_MODEL=deepseek-chat
DOUBASE_OPENAI_MODEL=gpt-4o

# 切换本地 Embedding（免费，离线）
DOUBASE_EMBEDDING_PROVIDER=local
DOUBASE_LOCAL_MODEL_NAME=BAAI/bge-small-zh-v1.5
```

**运行时参数**（分块大小、检索数量、查询优化等）在 `config.yaml` 中修改：

```yaml
retrieval:
  top_k: 15                  # 检索返回的 chunk 数量
  hybrid_search: true        # 混合检索（向量 + 关键词重排序）
  vector_weight: 0.6         # 向量分数权重
  keyword_weight: 0.4        # 关键词分数权重

chunker:
  chunk_size: 512            # 分块大小（tokens）
  chunk_overlap: 64          # 重叠量（tokens）
  heading_split: true        # 按 # 标题切分
  semantic_merge: true       # LLM 语义合并

query_optimization:
  context_rewrite: true      # 上下文补全（代词消解）
  decompose: true            # 子问题拆解
  decompose_max: 3           # 最多拆几个子问题
  rag_gating: true           # RAG 门控：LLM 判断是否需要检索
```

所有可用环境变量见 `.env.example`。

## 数据存储

向量化后的数据存储在 `~/.doubase/vectors/`：

```
~/.doubase/vectors/
├── chroma.sqlite3      # 主数据库
└── <uuid>/             # HNSW 索引文件
    ├── data_level0.bin
    ├── header.bin
    ├── length.bin
    └── link_lists.bin
```

分析代码项目时生成的 `.md` 总结文件存放在被分析项目的同级目录 `doubase_summaries/` 中。

REPL 会话记忆保存在 `~/.doubase/sessions/`（JSON 格式）。

> 存储目录可通过 `.env` 中的 `DOUBASE_VECTOR_DIR` 修改。

## 架构

```
CLI 命令:
  doubase ask <question>         单次 RAG 问答
  doubase repl                   交互式对话（多轮记忆，自动补全，混合检索）
  doubase ingest <paths>         导入文档
  doubase analyze <project>      分析代码项目

Ingest 流水线:   解析 → 哈希去重 → 三级分块 → Embedding → ChromaDB
Ask 流水线:      查询优化(补全+拆解+门控) → 混合检索(向量+关键词+LLM精排) → Prompt → LLM 流式回答
Analyze 流水线:  扫描器 → LLM 文件分析 → 写入器(.md) → 自动入库

模块: config / parsers / chunker / embedding / storage / retrieval / generation /
      analyzer / pipeline / repl / memory / query_optimizer / watch
```

## 测试

```bash
pip install -e .
pytest tests/ -v
```

**106 个单元测试**，覆盖解析器、分块器、向量存储、检索器、LLM 接口、查询优化、对话记忆、API 重试等全部模块。

## 技术栈

- Python 3.11+、ChromaDB、OpenAI SDK
- python-docx（Word）、PyMuPDF（PDF）、tiktoken（token 计数）
- rich（终端美化输出）、watchdog（文件监控）

## 许可证

MIT
