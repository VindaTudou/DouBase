# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 开发命令

```bash
# 安装（Python 3.11 必需）
/opt/homebrew/bin/python3.11 -m pip install -e .

# 运行全部测试
/opt/homebrew/bin/python3.11 -m pytest tests/ -v

# 运行单个测试文件
/opt/homebrew/bin/python3.11 -m pytest tests/test_config.py -v

# 运行单个测试函数
/opt/homebrew/bin/python3.11 -m pytest tests/test_config.py::test_resolve_env_vars -v

# 直接运行 CLI（无需安装）
/opt/homebrew/bin/python3.11 doubase/cli.py --help

# 系统 python3 是 3.9，不支持本项目。始终使用 /opt/homebrew/bin/python3.11
```

## 架构

### 三层 Pipeline 模型

项目遵循 `Parser → Chunk → Embed → Store → Retrieve → Generate` 的 Pipeline 模式。每个阶段通过抽象接口与下游解耦，所有接口和工厂函数定义在各模块的 `__init__.py` 中。

**三条 Pipeline：**

1. **Ingest**: `doubase ingest <paths>` — 解析文档 → SHA256 哈希去重 → 分块 → Embedding → ChromaDB
2. **Ask**: `doubase ask <question>` — 问题 Embedding → 检索 top-K → 混合 Prompt（本地笔记 + LLM 知识）→ 流式回答
3. **Analyze**: `doubase analyze <project>` — 扫描源码 → LLM 逐文件分析 → 生成 Markdown 总结 → 自动触发 Ingest 入库
4. **REPL**: `doubase repl` — 交互式对话模式，直接输入问题即可提问，`/` 前缀执行命令（`/ingest`、`/analyze`、`/help`、`/exit`）。闲置 30 秒自动显示命令提示。

### REPL 输出模式

`repl.py` 通过 `run_ask(render_markdown=True)` 累积 LLM 流式输出后，用 `rich.markdown.Markdown` 渲染完整回答（表格、列表、标题等）。回答前打印白色 `●` 圆点标识，使用 Rich `Table` 与内容同行对齐。

CLI 模式（`doubase ask`）保持流式逐 token 输出，不渲染 Markdown。

### 关键抽象接口

| 模块 | 接口 | 位置 |
|------|------|------|
| Parser | `BaseParser` → `supports()`, `parse() -> ParsedDocument` | `parsers/base.py` |
| Embedder | `BaseEmbedder` → `embed()`, `embed_query()` | `embedding/base.py` |
| LLM | `BaseLLM` → `chat()`, `chat_stream()` | `generation/base.py` |
| Chunker | `Chunker` → `chunk_text() -> list[Chunk]` | `chunker/chunker.py` |
| VectorStore | `VectorStore` → `add_chunks_with_embeddings()`, `search()`, `get_existing_hash()` | `storage/vector_store.py` |

### Provider 切换机制

LLM 和 Embedder 通过工厂函数实例化（`get_llm()`, `get_embedder()`），读取 `config["llm"]["provider"]` 决定具体实现。新增 Provider 只需添加类并注册到工厂函数的分支中。

### 配置加载流程

`doubase/config.py` 的 `load_config()`：
1. 加载项目根目录的 `.env` 文件到环境变量（不覆盖已存在的变量）
2. 加载 `config.yaml`
3. 递归解析 `${VAR_NAME}` 和 `${VAR:-default}` 语法
4. 展开 `~` 路径

`.env` 存敏感信息（API Key），`config.yaml` 存运行时参数。`.env` 通过 `.gitignore` 排除。

### 费用估算与确认

`ingest` 和 `analyze` 默认**三步执行**：本地预处理 → 展示费用估算表格 → 用户确认后调用付费 API。`--yes` / `-y` 跳过确认。估算仅在本地方计算 token 数，不调用任何 API。

### 增量去重

Ingest 阶段对每个文件计算 SHA256，查询 ChromaDB 中已有的 hash。相同则跳过（`source_path` 作为 key），不同则先删旧 chunks 再导入新 chunks。
