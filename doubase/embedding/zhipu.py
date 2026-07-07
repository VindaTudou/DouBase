"""智谱 AI Embedding API, 带自动重试。智谱 API 兼容 OpenAI 接口。"""

from openai import OpenAI

from doubase.embedding.base import BaseEmbedder
from doubase.api_retry import retry_call


class ZhipuEmbedder(BaseEmbedder):
    """通过智谱 (ZhipuAI) API 进行 Embedding。"""

    def __init__(self, api_key: str, model: str, base_url: str):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = retry_call(
            self._client.embeddings.create,
            model=self._model,
            input=texts,
            label=f"Zhipu embed ({len(texts)} texts)",
        )
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        result = self.embed([text])
        return result[0] if result else []
