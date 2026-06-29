"""Embedding 层 — 将文本转换为向量。"""

from doubase.embedding.base import BaseEmbedder
from doubase.embedding.zhipu import ZhipuEmbedder

__all__ = ["BaseEmbedder", "ZhipuEmbedder", "get_embedder"]


def get_embedder(config: dict) -> BaseEmbedder:
    """工厂函数：返回配置指定的 Embedder 实例。"""
    embedding_config = config["embedding"]
    provider = embedding_config["provider"]

    if provider == "zhipu":
        cfg = embedding_config["zhipu"]
        return ZhipuEmbedder(
            api_key=cfg["api_key"],
            model=cfg["model"],
            base_url=cfg["base_url"],
        )
    elif provider == "local":
        from doubase.embedding.local import LocalEmbedder
        cfg = embedding_config["local"]
        return LocalEmbedder(model_name=cfg["model_name"])
    else:
        raise ValueError(f"未知的 embedding provider: {provider}")
