# 贡献指南

## 开发环境搭建

### 前置条件

- Python 3.11+
- macOS/Linux（Windows 未经测试）

### 安装

```bash
git clone https://github.com/fangtudou/DouBase.git
cd DouBase
pip install -e .

# 可选：本地 embedding 模型
pip install -e ".[local-embed]"
```

### 配置

```bash
cp .env.example .env
# 编辑 .env 填入 API Key
```

### 运行测试

```bash
# 全部测试
pytest tests/ -v

# 单个模块
pytest tests/test_query_optimizer.py -v

# 单个测试
pytest tests/test_config.py::test_resolve_env_vars -v
```

## 代码规范

### 架构原则

- **策略模式 + 工厂函数**: 所有可替换组件通过工厂函数实例化，新增 Provider 只需添加类并注册
- **依赖倒置**: 高层模块依赖抽象接口（`BaseParser`、`BaseEmbedder`、`BaseLLM`），不依赖具体实现
- **Pipeline 编排**: 业务逻辑在 `pipeline.py` 中编排，领域模块保持纯粹

### Commit 规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: 新功能
fix:  修复 bug
docs: 文档变更
test: 测试变更
refactor: 重构
chore: 构建/工具变更
```

### Pull Request 流程

1. 从 `main` 分支创建功能分支
2. 编写代码并添加测试
3. 确保全部测试通过: `pytest tests/ -v`
4. 提交 PR，描述改动内容和测试结果

## 项目结构

```
doubase/
├── parsers/        # 文档解析器（Markdown/DOCX/PDF）
├── chunker/        # 文本分块（标题切分/滑动窗口/语义合并）
├── embedding/      # 文本向量化（Zhipu/本地）
├── storage/        # ChromaDB 向量存储
├── retrieval/      # 混合检索（向量+关键词+LLM精排）
├── generation/     # LLM 客户端（DeepSeek/OpenAI兼容）
├── analyzer/       # 代码分析（扫描/分析/写入）
├── pipeline.py     # 核心流水线编排
├── repl.py         # 交互式 REPL
├── memory.py       # 多轮对话记忆
├── query_optimizer.py  # 查询优化
├── api_retry.py    # API 重试
├── config.py       # 配置加载
├── cli.py          # CLI 入口
└── watch.py        # 文件监控
```

## 添加新的 LLM Provider

1. 在 `generation/` 下新建文件，继承 `BaseLLM`
2. 实现 `chat()` 和 `chat_stream()` 方法
3. 在 `generation/__init__.py` 的 `get_llm()` 中注册

## 添加新的 Embedding Provider

1. 在 `embedding/` 下新建文件，继承 `BaseEmbedder`
2. 实现 `embed()` 和 `embed_query()` 方法
3. 在 `embedding/__init__.py` 的 `get_embedder()` 中注册

## 添加新的文档格式

1. 在 `parsers/` 下新建文件，继承 `BaseParser`
2. 实现 `supports()` 和 `parse()` 方法
3. 在 `parsers/__init__.py` 的 `get_all_parsers()` 中注册
