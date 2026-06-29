from unittest.mock import MagicMock
from doubase.retrieval.retriever import Retriever


def test_retriever_embeds_and_searches():
    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1, 0.2, 0.3]
    mock_store = MagicMock()
    mock_store.search.return_value = [
        {"text": "Redis 使用 RDB 持久化", "source_path": "/notes/redis.md", "distance": 0.12},
        {"text": "AOF 记录每次写操作", "source_path": "/notes/redis.md", "distance": 0.18},
    ]

    retriever = Retriever(embedder=mock_embedder, vector_store=mock_store)
    results = retriever.retrieve("Redis 如何持久化数据？", top_k=5)

    mock_embedder.embed_query.assert_called_once_with("Redis 如何持久化数据？")
    mock_store.search.assert_called_once_with([0.1, 0.2, 0.3], 5)
    assert len(results) == 2
    assert results[0]["source_path"] == "/notes/redis.md"


def test_retriever_uses_default_top_k():
    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1, 0.2]
    mock_store = MagicMock()
    mock_store.search.return_value = []

    retriever = Retriever(embedder=mock_embedder, vector_store=mock_store)
    retriever.retrieve("test query")

    mock_store.search.assert_called_once_with([0.1, 0.2], 5)
