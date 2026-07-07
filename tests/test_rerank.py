"""测试关键词重排序。"""

from doubase.retrieval.retriever import _tokenize, _keyword_score, rerank


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
