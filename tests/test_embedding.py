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
def test_zhipu_embed_splits_over_64_into_batches(mock_openai_class):
    """超过智谱单次 64 条上限时应分批，且返回顺序与输入一致。"""
    mock_client = MagicMock()

    def fake_create(**kwargs):
        resp = MagicMock()
        # 每条输入按 "text-N" 中的 N 生成以序号为特征的 embedding
        resp.data = []
        for t in kwargs["input"]:
            n = int(t.split("-")[1])
            resp.data.append(MagicMock(embedding=[float(n), float(n)]))
        return resp

    mock_client.embeddings.create.side_effect = fake_create
    mock_openai_class.return_value = mock_client

    embedder = ZhipuEmbedder(
        api_key="test-key",
        model="embedding-2",
        base_url="https://api.test.com",
    )
    texts = [f"text-{i}" for i in range(70)]  # 70 条 → 2 批（64 + 6）
    result = embedder.embed(texts)

    assert len(result) == 70
    assert mock_client.embeddings.create.call_count == 2
    batch_sizes = [len(c[1]["input"]) for c in mock_client.embeddings.create.call_args_list]
    assert batch_sizes == [64, 6]
    # 顺序保持：第一批首条是 text-0，第二批首条是 text-64
    assert mock_client.embeddings.create.call_args_list[0][1]["input"][0] == "text-0"
    assert mock_client.embeddings.create.call_args_list[1][1]["input"][0] == "text-64"
    # 返回值顺序与输入一致
    assert result[0] == [0.0, 0.0]
    assert result[69] == [69.0, 69.0]


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
