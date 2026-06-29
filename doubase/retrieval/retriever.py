"""检索 — 将查询 embedding 后从 ChromaDB 中搜索相关 chunks。"""

from doubase.embedding.base import BaseEmbedder
from doubase.storage.vector_store import VectorStore


class Retriever:
    """将用户查询向量化，从向量库中检索 top-K 相关 chunks。"""

    def __init__(self, embedder: BaseEmbedder, vector_store: VectorStore):
        self._embedder = embedder
        self._store = vector_store

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Embed 查询文本并返回 top-K 最相关 chunks。

        Args:
            query: 用户自然语言问题。
            top_k: 检索数量。

        Returns:
            dict 列表，每个包含: text, source_path, distance。
        """
        query_vector = self._embedder.embed_query(query)
        return self._store.search(query_vector, top_k)
