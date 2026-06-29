# DouBase

本地 RAG CLI 工具，用于个人知识管理与代码分析。

## 快速开始

```bash
pip install -e .
export DEEPSEEK_API_KEY=sk-...
export ZHIPU_API_KEY=...

doubase ingest ~/Documents/notes/
doubase ask "Redis 持久化原理是什么？"
doubase analyze ../some-project/
```
