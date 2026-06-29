from unittest.mock import patch, MagicMock
from doubase.generation.base import BaseLLM
from doubase.generation.deepseek import DeepSeekLLM
from doubase.generation import get_llm


def test_get_llm_returns_deepseek_by_default():
    config = {
        "llm": {
            "provider": "deepseek",
            "deepseek": {
                "api_key": "test-key",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
            },
        }
    }
    llm = get_llm(config)
    assert isinstance(llm, DeepSeekLLM)


def test_get_llm_override_provider():
    config = {
        "llm": {
            "provider": "deepseek",
            "deepseek": {"api_key": "sk-ds", "model": "deepseek-chat", "base_url": "https://x.com"},
            "openai": {"api_key": "sk-oai", "model": "gpt-4o", "base_url": "https://api.openai.com/v1"},
        }
    }
    from doubase.generation.openai_compat import OpenAICompatLLM
    llm = get_llm(config, override_provider="openai")
    assert isinstance(llm, OpenAICompatLLM)


@patch("doubase.generation.deepseek.OpenAI")
def test_deepseek_chat(mock_openai_class):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Redis 持久化使用 RDB 和 AOF。"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai_class.return_value = mock_client

    llm = DeepSeekLLM(api_key="test", model="deepseek-chat", base_url="https://api.test.com")
    result = llm.chat([{"role": "user", "content": "你好"}])
    assert "Redis 持久化" in result


@patch("doubase.generation.deepseek.OpenAI")
def test_deepseek_chat_stream(mock_openai_class):
    mock_client = MagicMock()
    mock_chunk1 = MagicMock()
    mock_chunk1.choices = [MagicMock(delta=MagicMock(content="你好 "))]
    mock_chunk2 = MagicMock()
    mock_chunk2.choices = [MagicMock(delta=MagicMock(content="世界"))]
    mock_chunk3 = MagicMock()
    mock_chunk3.choices = [MagicMock(delta=MagicMock(content=None))]
    mock_client.chat.completions.create.return_value = [mock_chunk1, mock_chunk2, mock_chunk3]
    mock_openai_class.return_value = mock_client

    llm = DeepSeekLLM(api_key="test", model="deepseek-chat", base_url="https://api.test.com")
    tokens = list(llm.chat_stream([{"role": "user", "content": "你好"}]))
    assert tokens == ["你好 ", "世界"]


def test_get_llm_returns_openai_compat():
    config = {
        "llm": {
            "provider": "openai_compat",
            "openai_compat": {
                "api_key": "test-key",
                "model": "custom-model",
                "base_url": "https://custom.api.com/v1",
            },
        }
    }
    from doubase.generation.openai_compat import OpenAICompatLLM
    llm = get_llm(config)
    assert isinstance(llm, OpenAICompatLLM)
