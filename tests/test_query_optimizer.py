from unittest.mock import MagicMock
from doubase.query_optimizer import rewrite_query, decompose_query, should_retrieve


def test_rewrite_query_with_pronoun():
    """包含代词 → 应补全"""
    history = [
        {"role": "user", "content": "Redis 持久化是什么？"},
        {"role": "assistant", "content": "Redis 有 RDB 和 AOF 两种持久化方式。"},
    ]
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "RDB 持久化有什么优缺点？"

    result = rewrite_query("它有什么优缺点？", history, mock_llm)
    mock_llm.chat.assert_called_once()
    assert "RDB" in result


def test_rewrite_query_complete_question():
    """完整独立问题 → LLM 返回原问题"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "Redis 是什么？"

    result = rewrite_query("Redis 是什么？", [], mock_llm)
    assert "Redis" in result


def test_rewrite_no_history_skips_llm():
    """无历史 → 不调 LLM，直接返回原问题"""
    mock_llm = MagicMock()
    result = rewrite_query("它怎么样？", [], mock_llm)
    mock_llm.chat.assert_not_called()
    assert result == "它怎么样？"


def test_decompose_simple_question():
    """单问题 → 返回单元素列表"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "1. Redis 是什么？"
    result = decompose_query("Redis 是什么？", mock_llm)
    assert len(result) == 1


def test_decompose_multi_question():
    """多问题 → 拆解为子问题列表"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = (
        "1. RDB 持久化的特点\n"
        "2. AOF 持久化的特点\n"
        "3. RDB 和 AOF 的对比"
    )
    result = decompose_query("RDB 和 AOF 的区别？", mock_llm, max_count=3)
    assert len(result) == 3
    assert any("RDB" in r for r in result)
    assert any("AOF" in r for r in result)


def test_decompose_empty_response_falls_back():
    """LLM 返回空 → 回退到原问题"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = ""
    result = decompose_query("test question", mock_llm)
    assert result == ["test question"]


def test_decompose_llm_error_falls_back():
    """LLM 调用失败 → 回退到原问题"""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = Exception("API error")
    result = decompose_query("RDB 和 AOF 的区别？", mock_llm)
    assert result == ["RDB 和 AOF 的区别？"]


def test_should_retrieve_yes():
    """LLM 返回 YES → 需要检索"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "YES"
    result = should_retrieve("我的笔记里关于 Redis 的记录是什么？", mock_llm)
    assert result is True


def test_should_retrieve_no():
    """LLM 返回 NO → 不需要检索"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "NO"
    result = should_retrieve("Python 中如何反转列表？", mock_llm)
    assert result is False


def test_should_retrieve_with_history():
    """带对话历史的门控判断"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "YES"
    history = [
        {"role": "user", "content": "我的项目里用了什么数据库？"},
        {"role": "assistant", "content": "你的项目使用 Redis 作为缓存。"},
    ]
    result = should_retrieve("它的配置是什么？", mock_llm, history=history)
    mock_llm.chat.assert_called_once()
    call_args = mock_llm.chat.call_args[0][0]
    # prompt 应包含对话历史
    assert "Redis" in call_args[0]["content"]
    assert result is True


def test_should_retrieve_error_falls_back_to_true():
    """LLM 调用失败 → 默认检索（宁可多查不漏查）"""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = Exception("API timeout")
    result = should_retrieve("任意问题", mock_llm)
    assert result is True


def test_should_retrieve_empty_response_falls_back():
    """LLM 返回空字符串 → 默认检索"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = ""
    result = should_retrieve("任意问题", mock_llm)
    assert result is True


def test_should_retrieve_lowercase_yes():
    """LLM 返回小写 yes → 识别为需要检索"""
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "yes"
    result = should_retrieve("我的笔记里有什么？", mock_llm)
    assert result is True
