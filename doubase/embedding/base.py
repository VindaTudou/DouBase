"""Embedding 模型抽象接口。"""

from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """文本到向量的 embedding 抽象接口。"""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化，返回向量列表。"""
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """单条查询文本向量化（某些模型有专门的 query 模式）。"""
        ...
