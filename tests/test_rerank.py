"""测试关键词重排序 + LLM 重排序。"""

from unittest.mock import MagicMock
from doubase.retrieval.retriever import _tokenize, _keyword_score, rerank, llm_rerank


def test_tokenize_chinese_bigrams():
    tokens = _tokenize("Redis持久化")
    assert "Redis" in tokens or "redis" in tokens
    assert "持久" in tokens
    assert "久化" in tokens


def test_tokenize_english_words():
    tokens = _tokenize("What is Redis persistence")
    assert "what" in tokens
    assert "redis" in tokens
    assert "persistence" in tokens


def test_keyword_score_full_match():
    query_tokens = _tokenize("Redis 持久化")
    score = _keyword_score(query_tokens, "Redis 持久化有 RDB 和 AOF 两种方式")
    assert score >= 0.5  # 大部分 query token 命中


def test_keyword_score_no_match():
    query_tokens = _tokenize("Redis 持久化")
    score = _keyword_score(query_tokens, "MySQL binlog redo log 事务恢复")
    assert score < 0.3  # 几乎没有命中


def test_rerank_moves_keyword_match_up():
    """关键词高度匹配的 chunk 在重排序中应被提升。"""
    query = "Redis 持久化方式"
    # 模拟真实场景：向量分数都很接近（都在 0.1-0.2 范围），关键词决定最终排名
    chunks = [
        {"text": "今天天气很好适合出门散步", "source_path": "noise.md", "distance": 0.11},
        {"text": "MySQL 通过 binlog 和 redo log 实现事务持久化", "source_path": "b.md", "distance": 0.13},
        {"text": "小猫咪在沙发上睡觉", "source_path": "noise2.md", "distance": 0.15},
        {"text": "Redis 持久化使用 RDB 和 AOF 快照日志", "source_path": "a.md", "distance": 0.18},
    ]
    result = rerank(query, chunks, top_k=4)
    # Redis 那条应该被提升到前 2（关键词命中率高）
    top_texts = [c["text"] for c in result[:2]]
    assert any("Redis" in t for t in top_texts), f"Redis should be top-2, got {top_texts}"


def test_rerank_empty():
    assert rerank("test", [], top_k=5) == []


def test_rerank_respects_top_k():
    chunks = [
        {"text": f"document {i}", "source_path": "x.md", "distance": 0.1 + i * 0.01}
        for i in range(20)
    ]
    result = rerank("document", chunks, top_k=5)
    assert len(result) == 5


def test_llm_rerank_parses_scores():
    """LLM 返回打分 → 解析后按分数重排"""
    query = "Redis 持久化"
    chunks = [
        {"text": "无关内容", "source_path": "a.md"},
        {"text": "Redis RDB 快照持久化", "source_path": "b.md"},
        {"text": "Redis AOF 日志持久化", "source_path": "c.md"},
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "1. 1\n2. 5\n3. 4"

    result = llm_rerank(query, chunks, mock_llm, top_k=2)
    assert len(result) == 2
    assert result[0]["llm_score"] == 5  # b.md 应该在第一个
    assert "RDB" in result[0]["text"]


def test_llm_rerank_fallback_on_error():
    """LLM 调用失败 → 返回原顺序"""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = Exception("API error")
    chunks = [
        {"text": f"chunk {i}", "source_path": "x.md"}
        for i in range(5)
    ]
    result = llm_rerank("test", chunks, mock_llm, top_k=3)
    assert len(result) == 3


def test_llm_rerank_truncates_to_10():
    """超过 10 个 chunk → 只评前 10 个"""
    chunks = [{"text": f"chunk {i}", "source_path": "x.md"} for i in range(15)]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "\n".join(f"{i+1}. 3" for i in range(10))
    result = llm_rerank("test", chunks, mock_llm, top_k=5)
    assert len(result) == 5
