# Changelog

All notable changes to DouBase will be documented in this file.

## [0.1.0] - 2026-07-07

### Added
- **RAG 门控判断**: LLM 在检索前判断问题是否需要查本地知识库，通用常识问题跳过 RAG 流程，节省 Embedding API 调用和检索时间
- **API 重试机制**: 所有 LLM 和 Embedding API 调用自动指数退避重试（1s→2s→4s），处理 429 限流、5xx 服务端错误、网络超时
- **LLM 精排序**: 混合检索后通过 LLM 对 top-10 候选打分（1-5 分），进一步提升返回精度
- **混合检索**: 向量相似度 + 关键词命中率加权融合（vector×0.6 + keyword×0.4），中文 bigram 分词零外部依赖
- **查询优化**: 上下文补全（代词消解）+ 子问题拆解，独立判断不耦合
- **多轮对话记忆**: 5 轮完整保留 + LLM 摘要压缩，JSON 持久化到 `~/.doubase/sessions/`
- **3 级分块策略**: Markdown `#` 标题语义切分 → 滑动窗口兜底 → LLM 保守合并（仅同标题相邻对）
- **交互式 REPL**: Rich Live 流式输出 + Markdown 渲染，闲置 30 秒提示，`/ingest`、`/analyze` 等命令
- **本地 Embedding**: 支持 sentence-transformers 本地模型（BGE 系列），免费离线使用
- **OpenAI 兼容接口**: 支持任何 OpenAI-compatible API（Ollama、vLLM 等）
- **核心功能**: RAG 问答、文档导入（.md/.docx/.pdf）、代码分析（analyze）、费用估算、文件监控

### Infrastructure
- 106 个单元测试（pytest）
- Conventional Commits 规范
- MIT License
