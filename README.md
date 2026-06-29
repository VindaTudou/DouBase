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

```bash
export DEEPSEEK_API_KEY=sk-你的-deepseek-key
export ZHIPU_API_KEY=你的-智谱-key
```

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

编辑 `config.yaml` 切换提供商、模型、分块大小等。

```yaml
llm:
  provider: deepseek  # 可改为 openai 或 openai_compat

embedding:
  provider: zhipu     # 可改为 local 使用离线 embedding

retrieval:
  top_k: 5            # 检索返回的 chunk 数量

pricing:
  deepseek:
    input_price: 1.0   # 人民币/百万 tokens
    output_price: 2.0
```

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
