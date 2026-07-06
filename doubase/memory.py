"""对话记忆管理 — 多轮对话上下文保留与智能压缩。"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversationMemory:
    """多轮对话记忆。最近 max_turns 轮完整保留，超出部分由 LLM 压缩为摘要。

    Attributes:
        max_turns: 完整保留的最大轮数（默认 5）。
        messages: 最近 N 轮的完整消息列表 [{role, content}, ...]。
        summary: 超出 max_turns 的历史摘要。
        summary_turns: 摘要涵盖了多少轮对话。
    """

    max_turns: int = 5
    messages: list[dict] = field(default_factory=list)
    summary: str = ""
    summary_turns: int = 0

    def add(self, question: str, answer: str, llm=None):
        """记录一轮对话。超过 max_turns 时自动触发压缩。

        Args:
            question: 用户问题。
            answer: 助手回答全文。
            llm: BaseLLM 实例（压缩时需要）。为 None 时跳过压缩。
        """
        self.messages.append({"role": "user", "content": question})
        self.messages.append({"role": "assistant", "content": answer})

        while len(self.messages) > self.max_turns * 2 and llm is not None:
            self._compress(llm)

    def _compress(self, llm):
        """将最早一轮 Q&A 移出并合并到摘要中。"""
        q = self.messages[0]["content"]
        a = self.messages[1]["content"]
        self.messages = self.messages[2:]

        prompt = (
            f"请将以下对话压缩为一句简短摘要。\n\n"
            f"当前摘要: {self.summary or '无'}\n\n"
            f"本轮对话:\n用户: {q}\n助手: {a}\n\n"
            f"请输出一句融合了已有摘要和新对话的简短摘要（中文，不超过80字）。仅输出摘要本身。"
        )
        try:
            self.summary = llm.chat([{"role": "user", "content": prompt}]).strip()
        except Exception:
            self.summary = f"{self.summary or ''} {q[:40]}...".strip()
        self.summary_turns += 1

    def get_history(self) -> list[dict]:
        """返回应注入 Prompt 的历史消息列表。包含摘要（如有）+ 完整消息。"""
        result = []
        if self.summary:
            result.append({
                "role": "system",
                "content": f"[对话记忆] 之前已讨论: {self.summary}",
            })
        result.extend(self.messages)
        return result

    def clear(self):
        """清空所有记忆。"""
        self.messages = []
        self.summary = ""
        self.summary_turns = 0

    def save(self, name: str = "default"):
        """持久化到 ~/.doubase/sessions/{name}.json。"""
        path = Path("~/.doubase/sessions").expanduser()
        path.mkdir(parents=True, exist_ok=True)
        data = {
            "max_turns": self.max_turns,
            "messages": self.messages,
            "summary": self.summary,
            "summary_turns": self.summary_turns,
        }
        (path / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    @classmethod
    def load(cls, name: str = "default") -> "ConversationMemory":
        """从 ~/.doubase/sessions/{name}.json 加载记忆。不存在则返回空实例。"""
        path = Path(f"~/.doubase/sessions/{name}.json").expanduser()
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        mem = cls(max_turns=data.get("max_turns", 5))
        mem.messages = data.get("messages", [])
        mem.summary = data.get("summary", "")
        mem.summary_turns = data.get("summary_turns", 0)
        return mem
