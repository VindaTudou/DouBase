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

## ⚠️ 评测原则（血泪教训，2026-08-17）

**① 分块参数评测必须用"与生产库完全一致的语料"，不能只挑一部份 md。**

- 反例：用 vault-only（77 个笔记 md）扫分块参数，得出"256/64 或 512/64 胜"；
  但真实生产库包含**代码总结、homework、README、CLAUDE.md、Excalidraw、docx** 等 214 个源，
  在生产库上结论**反转**（256/64 ≥ 512/64）。
- 正解：`evals/chunk_eval.py --corpus store`（从当前生产库读完整源文件集），
  不要用 `--corpus vault`（仅笔记子集）做参数决策。

**② 必须测"完整生产链路"（semantic_merge 分块 + LLM 精排检索），不能只测检索阶段。**

- 反例：只测检索阶段（无合并无 LLM）时 256/64 胜；加上 semantic_merge + LLM 精排后结论翻转。
- 正解：`chunk_eval.py --merge --llm`，且用 `recall_eval.py`（默认全链路）做最终确认。

**③ Recall@K 的分母取决于分块粒度，跨分块器/跨库的数字不可直接比较。**

- 分块变细 → 相关片段变多 → 分母变大 → Recall 数值降（但命中的片段数可能反而增加）。
- 比较"是否变好"以 **Hit@K（命中率）** 为主、Recall@K 为辅。

**④ 数据必须可复现**：简历/对外口径一律用当前生产库 + `recall_eval.py` 实测，
不要引用旧库/旧分块器的历史数字。

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
