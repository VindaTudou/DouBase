"""检索 — 将查询 embedding 后从 ChromaDB 中搜索相关 chunks，支持关键词重排序。"""

import re
from doubase.embedding.base import BaseEmbedder
from doubase.storage.vector_store import VectorStore


def _tokenize(text: str) -> set[str]:
    """将文本分解为可匹配的 token 集合（零依赖）。

    中文: 字符二元组（"持久化" → {"持久", "久化"}），单个汉字也保留
    英文/数字: 按空格和标点分词，转小写
    """
    tokens = set()
    # 英文/数字词
    words = re.findall(r"[a-zA-Z0-9]+", text)
    tokens.update(w.lower() for w in words)
    # 中文二元组
    chinese = re.findall(r"[一-鿿]+", text)
    for segment in chinese:
        for i in range(len(segment)):
            tokens.add(segment[i])  # 单字
            if i < len(segment) - 1:
                tokens.add(segment[i:i+2])  # 二元组
    return tokens


def _keyword_score(query_tokens: set[str], chunk_text: str) -> float:
    """计算查询关键词在 chunk 中的命中率 (0.0 ~ 1.0)。"""
    if not query_tokens:
        return 0.0
    chunk_tokens = _tokenize(chunk_text)
    hits = len(query_tokens & chunk_tokens)
    return hits / len(query_tokens)


def rerank(
    query: str,
    chunks: list[dict],
    top_k: int = 5,
    vector_weight: float = 0.6,
    keyword_weight: float = 0.4,
) -> list[dict]:
    """混合重排序：向量相似度 + 关键词命中率加权融合。

    Args:
        query: 用户查询文本。
        chunks: 向量检索返回的候选列表（含 distance 字段）。
        top_k: 最终返回的 chunk 数量。
        vector_weight: 向量分数的权重（默认 0.6）。
        keyword_weight: 关键词分数的权重（默认 0.4）。

    Returns:
        重排序后的 top-K chunks。
    """
    if not chunks:
        return []

    query_tokens = _tokenize(query)

    # 向量距离 → 相似度分数（distance 越小越相似，1/(1+d) 映射到 (0,1]）
    for c in chunks:
        vector_score = 1.0 / (1.0 + c.get("distance", 0.0))
        kw_score = _keyword_score(query_tokens, c["text"])
        c["vector_score"] = vector_score
        c["keyword_score"] = kw_score
        c["fusion_score"] = vector_score * vector_weight + kw_score * keyword_weight

    chunks.sort(key=lambda c: c["fusion_score"], reverse=True)
    return chunks[:top_k]


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
