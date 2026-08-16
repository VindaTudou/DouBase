# 检索召回率评测

对 DouBase 的**检索链**（向量 → 关键词融合 → LLM 精排）做召回率评测。
只测检索，不经过 LLM 生成回答。

## 为什么测、测什么

RAG 里"召回率"特指检索阶段能不能把相关片段找出来。本目录用**带人工标注的测试集**
（query + 答案所在片段）计算三个指标，并对比三种检索配置：

| 配置 | 说明 |
|------|------|
| 纯向量 | 只做向量检索取 top-K，baseline |
| 混合 | 向量 + 关键词融合 `rerank` |
| 全链路 | 混合 + LLM 精排 `llm_rerank`（与 `doubase ask` 线上一致） |

指标：

- **Hit@K**：检索成功率 = 有多少比例的 query 在 top-K 中至少命中 1 个相关片段。
  个人知识库最常用的召回指标。
- **Recall@K**：片段级召回率 = 检索到的相关片段数 / 知识库中全部相关片段数（按 query 平均）。
- **MRR**：首个相关片段排名的倒数均值（衡量相关结果排得靠不靠前）。

## 使用

```bash
# 跑全部（纯向量 / 混合 / 全链路 三组对比，K=3,5,10）
/opt/homebrew/bin/python3.11 evals/recall_eval.py

# 自定义 K 值
/opt/homebrew/bin/python3.11 evals/recall_eval.py --top-k 1 5 20

# 查看向量库中的全部 source_path，用于核对标注
/opt/homebrew/bin/python3.11 evals/recall_eval.py --dump-sources
```

费用：全链路每组 query 只调一次 LLM（`llm_rerank`），30 条查询约 ¥0.01 以内；
向量 + 混合两组不调 LLM。

## 两套测试集

| 文件 | 题型 | 说明 |
|------|------|------|
| `test_set.jsonl` | **直述题**（30 条） | 问题直接用了答案里的术语，词面匹配容易，Hit@K 接近 1.0，用作"系统能跑通"的基线 |
| `test_set_hard.jsonl` | **改述题**（30 条） | 同一批知识点换成口语化/用户真实说法，抹掉答案关键词，考察真正的语义召回，指标有区分度 |

评测结果存档在 `evals/results/`（每份含日期、测试集、指标表和结论）。
`2026-08-07-llm-rerank-diagnosis.md` 是 LLM 精排对 MRR 影响的逐条诊断：直述题上 LLM 精排只下移不上移（基线完美 + LLM 判断层只有错误可犯），改述题上上移 10 条（把答案捞回来）；且 LLM 的误判集中在少数几个主题上，是系统性盲区而非随机噪声。
**核心结论**：直述题指标饱和（Hit@3≈1.0），改述题才有区分度（Hit@1≈0.5–0.8）；
LLM 精排在直述题上轻微拉低、在改述题上显著提升（Hit@3 0.867 → 0.933），应主要用改述题评估。

改述题示例（同一知识点，两种问法）：
- 直述：「栈的操作特性是什么？为什么叫先进后出？」
- 改述：「我要做一个撤销功能：后执行的操作必须先被撤销，用什么数据结构最合适？」

评测时用哪个测试集：
```bash
/opt/homebrew/bin/python3.11 evals/recall_eval.py --test-set evals/test_set.jsonl
/opt/homebrew/bin/python3.11 evals/recall_eval.py --test-set evals/test_set_hard.jsonl
```

## 测试集格式

`test_set.jsonl` / `test_set_hard.jsonl`，每行一个 JSON：

```json
{
  "query": "数据库事务的 ACID 特性是什么？",
  "relevant": [
    {"source_path": "/path/to/note.md", "text_marker": "原子性"}
  ]
}
```

- `source_path` **必须与向量库元数据完全一致**（用 `--dump-sources` 核对）。
- `text_marker` 可选：给定时为片段级匹配（该片段文本须包含此标记）；缺省为文件级匹配。

## 自己加测试集

对着你的笔记写"你会真去问的问题"，别从 chunk 原文直接抄（否则召回虚高）。
标注后用下面的命令快速校验 ground-truth 是否都能命中：

```python
from evals.recall_eval import load_test_set, build_relevant_index
# build_relevant_index 会对每条标注做校验，未命中的会打 ⚠️
```

> 注意：向量库中的 `source_path` 可能在笔记移动后与磁盘路径不一致，
> 请始终以 `--dump-sources` 输出的路径为准，而不是当前磁盘路径。
