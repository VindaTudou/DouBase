from unittest.mock import MagicMock
from doubase.chunker.chunker import Chunk
from doubase.chunker.semantic_merger import merge_semantically


def _make_chunk(text, heading_text, strategy, chunk_idx):
    return Chunk(
        text=text,
        source_path="/tmp/test.md",
        chunk_index=chunk_idx,
        content_hash="abc",
        metadata={"heading_text": heading_text, "strategy": strategy},
    )


def test_single_chunk_per_heading_skips_llm():
    """同标题下只有 1 个 chunk -> 不调 LLM，直接返回"""
    chunks = [
        _make_chunk("段落 A", "标题1", "heading", 0),
        _make_chunk("段落 B", "标题2", "heading", 1),
    ]
    mock_llm = MagicMock()
    result = merge_semantically(chunks, mock_llm)
    mock_llm.chat.assert_not_called()
    assert len(result) == 2


def test_multiple_chunks_same_heading_calls_llm():
    """同标题下 > 1 chunk -> 调 LLM"""
    chunks = [
        _make_chunk("RDB 简介第一部分...", "RDB", "sliding_window", 0),
        _make_chunk("RDB 简介第二部分...", "RDB", "sliding_window", 1),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "MERGE"
    result = merge_semantically(chunks, mock_llm)
    mock_llm.chat.assert_called_once()
    assert len(result) == 1
    assert "RDB 简介第一部分" in result[0].text
    assert "RDB 简介第二部分" in result[0].text
    assert result[0].metadata["strategy"] == "merged"


def test_llm_says_keep_separate():
    """LLM 判断不相关 -> 保持独立"""
    chunks = [
        _make_chunk("完全不相关的内容 A", "标题", "sliding_window", 0),
        _make_chunk("完全不相关的内容 B", "标题", "sliding_window", 1),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "KEEP_SEPARATE"
    result = merge_semantically(chunks, mock_llm)
    assert len(result) == 2


def test_three_chunks_merge_chain():
    """三个 chunk: A+B 合并, B+C 不合并 -> 返回 2 个"""
    chunks = [
        _make_chunk("相关 A", "标题", "sliding_window", 0),
        _make_chunk("相关 B", "标题", "sliding_window", 1),
        _make_chunk("无关 C", "标题", "sliding_window", 2),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = ["MERGE", "KEEP_SEPARATE"]
    result = merge_semantically(chunks, mock_llm)
    assert mock_llm.chat.call_count == 2
    assert len(result) == 2
    assert "相关 A" in result[0].text and "相关 B" in result[0].text
    assert "无关 C" in result[1].text


def test_mixed_headings():
    """混合多标题: 仅同标题下的才考虑合并"""
    chunks = [
        _make_chunk("A1", "标题A", "sliding_window", 0),
        _make_chunk("A2", "标题A", "sliding_window", 1),
        _make_chunk("B1", "标题B", "heading", 2),
        _make_chunk("C1", "标题C", "sliding_window", 3),
        _make_chunk("C2", "标题C", "sliding_window", 4),
    ]
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = ["MERGE", "MERGE"]
    result = merge_semantically(chunks, mock_llm)
    # A1+A2 合并, B1 独立, C1+C2 合并 -> 3 个
    assert len(result) == 3
    # B1 保持独立
    b_chunks = [c for c in result if c.metadata["heading_text"] == "标题B"]
    assert len(b_chunks) == 1
