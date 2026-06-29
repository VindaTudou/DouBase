from unittest.mock import patch, MagicMock
from doubase.embedding.base import BaseEmbedder
from doubase.embedding.zhipu import ZhipuEmbedder
from doubase.embedding import get_embedder


def test_get_embedder_returns_zhipu_by_default():
    config = {
        "embedding": {
            "provider": "zhipu",
            "zhipu": {
                "api_key": "test-key",
                "model": "embedding-2",
                "base_url": "https://test.com/api",
            },
        }
    }
    embedder = get_embedder(config)
    assert isinstance(embedder, ZhipuEmbedder)


def test_zhipu_embedder_interface():
    embedder = ZhipuEmbedder(
        api_key="test-key",
        model="embedding-2",
        base_url="https://api.test.com",
    )
    assert isinstance(embedder, BaseEmbedder)


@patch("doubase.embedding.zhipu.OpenAI")
def test_zhipu_embed_batches(mock_openai_class):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1, 0.2, 0.3]),
        MagicMock(embedding=[0.4, 0.5, 0.6]),
    ]
    mock_client.embeddings.create.return_value = mock_response
    mock_openai_class.return_value = mock_client

    embedder = ZhipuEmbedder(
        api_key="test-key",
        model="embedding-2",
        base_url="https://api.test.com",
    )
    result = embedder.embed(["hello", "world"])
    assert len(result) == 2
    assert result[0] == [0.1, 0.2, 0.3]
    assert result[1] == [0.4, 0.5, 0.6]
    mock_client.embeddings.create.assert_called_once_with(
        model="embedding-2",
        input=["hello", "world"],
    )


@patch("doubase.embedding.zhipu.OpenAI")
def test_zhipu_embed_query(mock_openai_class):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.7, 0.8, 0.9])]
    mock_client.embeddings.create.return_value = mock_response
    mock_openai_class.return_value = mock_client

    embedder = ZhipuEmbedder(
        api_key="test-key",
        model="embedding-2",
        base_url="https://api.test.com",
    )
    result = embedder.embed_query("single query")
    assert result == [0.7, 0.8, 0.9]


def test_get_embedder_returns_local_when_configured():
    config = {
        "embedding": {
            "provider": "local",
            "local": {
                "model_name": "BAAI/bge-small-zh-v1.5",
            },
        }
    }
    from doubase.embedding.local import LocalEmbedder
    embedder = get_embedder(config)
    assert isinstance(embedder, LocalEmbedder)
    assert embedder._model_name == "BAAI/bge-small-zh-v1.5"


def test_get_embedder_raises_for_unknown_provider():
    config = {
        "embedding": {
            "provider": "unknown",
        }
    }
    try:
        get_embedder(config)
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "unknown" in str(e).lower()
