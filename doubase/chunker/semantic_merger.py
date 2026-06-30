"""LLM 语义合并 — 合并同标题下语义相关的相邻 chunk。"""

from doubase.chunker.chunker import Chunk
from doubase.generation.base import BaseLLM

MERGE_PROMPT = """以下两段文本来自同一篇文档的相邻段落。判断它们是否应该合并为一个语义单元。

合并标准：两段文本讨论同一主题的连续内容，合并后阅读流畅、逻辑连贯。
不合并标准：两段文本讨论不同方面、不同案例，各自独立存在更有意义。

文本 1:
{text1}

文本 2:
{text2}

请仅回复一个词：MERGE 或 KEEP_SEPARATE。"""


def merge_semantically(chunks: list[Chunk], llm: BaseLLM) -> list[Chunk]:
    """LLM 保守合并：仅合并同标题下语义相关的相邻 chunk。

    Args:
        chunks: Stage 1+2 产出的全部 chunk（已按 chunk_index 排序）。
        llm: LLM 实例（用于判断语义相关性）。

    Returns:
        合并后的 chunk 列表。
    """
    if not chunks:
        return []

    # 按 heading_text 分组（保持组内原有顺序）
    groups: dict[str, list[int]] = {}
    for i, c in enumerate(chunks):
        heading = c.metadata.get("heading_text", "")
        if heading not in groups:
            groups[heading] = []
        groups[heading].append(i)

    # 标记哪些 index 需要移除（被合并到前一个）
    to_remove: set[int] = set()

    for heading, indices in groups.items():
        if len(indices) <= 1:
            continue  # 同标题下只有 1 个 chunk -> 无需合并

        # 逐个判断相邻 pair，用 current_idx 跟踪已合并的累积 chunk
        current_idx = indices[0]

        for j in range(1, len(indices)):
            next_idx = indices[j]

            # 调 LLM 判断 current（可能已合并多个）与 next
            prompt = MERGE_PROMPT.format(
                text1=chunks[current_idx].text,
                text2=chunks[next_idx].text,
            )
            try:
                reply = llm.chat([{"role": "user", "content": prompt}]).strip().upper()
            except Exception:
                # LLM 调用失败 -> 保守行为：不合并，current 移到 next
                current_idx = next_idx
                continue

            if "MERGE" in reply:
                # 合并: next 的内容追加到 current, 标记 next 待移除
                chunks[current_idx].text = chunks[current_idx].text + "\n\n" + chunks[next_idx].text
                chunks[current_idx].metadata["strategy"] = "merged"
                to_remove.add(next_idx)
                # current_idx 不变，继续与下一个比较
            else:
                # 不合并：current 移到 next，开启新的一段
                current_idx = next_idx

    # 移除被合并的 chunk
    result = [c for i, c in enumerate(chunks) if i not in to_remove]

    # 重新编号
    for i, c in enumerate(result):
        c.chunk_index = i

    return result
