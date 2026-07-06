"""查询优化 — 上下文补全 + 子问题拆解。"""

import re

# 匹配 surrogate 字符（U+D800-U+DFFF）
_SURROGATE_RE = re.compile(r'[\ud800-\udfff]')


def _sanitize(text: str) -> str:
    return _SURROGATE_RE.sub('', text)


from doubase.generation.base import BaseLLM

REWRITE_PROMPT = """你是一个查询优化器。根据对话历史判断用户当前问题是否需要上下文补全。

补全条件（满足其一即补全）:
1. 问题包含代词（它、他、她、这个、那个、这些、那些）
2. 问题 < 15 字且依赖前文内容
3. 问题是简短的确认/追问（"为什么？""怎么做？""比如？"）

不需要补全: 问题是完整独立的疑问。

对话历史:
{history}

用户当前问题: {question}

请输出最终问题文本（补全后或原问题），不要任何解释或额外文字。"""

DECOMPOSE_PROMPT = """判断以下问题是否包含多个独立子问题。如果包含，请拆分为独立子问题；否则返回原问题。

拆分标准:
- "A 和 B 的区别" → 拆成 "A 的特点"、"B 的特点"、"A 和 B 的对比"
- "X 是什么？怎么用？" → 拆成 "X 的定义"、"X 的使用方法"
- "为什么 Y？有什么影响？" → 拆成 "Y 的原因"、"Y 的影响"
- 单一问题 → 直接返回原问题

输出格式: 每个子问题一行，用数字编号。最多 {max_count} 个。
不需要任何解释。

问题: {question}"""


def rewrite_query(question: str, history: list[dict], llm: BaseLLM) -> str:
    """LLM 利用对话历史补全问题上下文。

    Args:
        question: 用户原始问题。
        history: 对话历史 [{role, content}, ...]。
        llm: LLM 实例。

    Returns:
        补全后的问题。无历史时返回原问题。
    """
    if not history:
        return question

    history_text = "\n".join(
        f"[{h['role']}]: {h['content'][:200]}" for h in history
    )
    prompt = REWRITE_PROMPT.format(
        question=question,
        history=history_text,
    )
    try:
        rewritten = _sanitize(llm.chat([{"role": "user", "content": prompt}])).strip()
        return rewritten if rewritten else question
    except Exception:
        return question


def decompose_query(question: str, llm: BaseLLM, max_count: int = 3) -> list[str]:
    """LLM 拆解复杂问题为独立子问题。

    Args:
        question: 用户问题（可能已经过上下文补全）。
        llm: LLM 实例。
        max_count: 最多拆几个子问题。

    Returns:
        子问题列表，至少 1 个元素。
    """
    prompt = DECOMPOSE_PROMPT.format(
        question=question,
        max_count=max_count,
    )
    try:
        reply = _sanitize(llm.chat([{"role": "user", "content": prompt}])).strip()
        if not reply:
            return [question]

        lines = reply.split("\n")
        sub_questions = []
        for line in lines:
            m = re.match(r"\d+[\.\)、]\s*(.+)", line.strip())
            if m:
                sub_questions.append(m.group(1).strip())
        return sub_questions if sub_questions else [question]
    except Exception:
        return [question]
