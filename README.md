# DouBase 🧠

本地 RAG CLI 工具，用于个人知识管理与代码分析。

## 功能

- **RAG 问答** — 提问，结合本地笔记 + LLM 知识给出混合回答
- **文档导入** — 导入 `.md`、`.docx`、`.pdf` 文件到 ChromaDB 向量库
- **代码分析** — 分析外部项目，自动生成 Markdown 总结并入库
- **费用估算** — 在调用任何付费 API 前展示花费预估，确认后执行
- **监控模式** — 自动导入放入监控目录的新文件
- **提供商切换** — LLM 可切换 DeepSeek/OpenAI，Embedding 可切换智谱/本地

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

**运行时参数**（分块大小、检索数量等）在 `config.yaml` 中修改：

```yaml
retrieval:
  top_k: 5            # 检索返回的 chunk 数量

chunker:
  chunk_size: 512     # 分块大小（tokens）
  chunk_overlap: 64   # 重叠量（tokens）
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

> 存储目录可通过 `.env` 中的 `DOUBASE_VECTOR_DIR` 修改。

## 架构

```
Ingest 流水线:   解析器 → 哈希去重 → 分块器 → Embedder → ChromaDB
Ask 流水线:      查询 → Embed → 检索 top-K → 混合提示词 → LLM → 回答
Analyze 流水线:  扫描器 → LLM 分析 → 写入器 (.md) → Ingest 流水线
```

## 技术栈

- Python 3.11+、ChromaDB、OpenAI SDK
- python-docx（Word）、PyMuPDF（PDF）、tiktoken（token 计数）
- rich（终端美化输出）、watchdog（文件监控）

## 许可证

MIT
