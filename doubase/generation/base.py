"""LLM 对话模型抽象接口。"""

from abc import ABC, abstractmethod
from collections.abc import Iterator


class BaseLLM(ABC):
    """大语言模型对话抽象接口。"""

    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """发送消息，返回完整文本回复。"""
        ...

    @abstractmethod
    def chat_stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """发送消息，逐 token 流式返回文本。"""
        ...
