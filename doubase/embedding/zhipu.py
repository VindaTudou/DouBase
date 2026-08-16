"""智谱 AI Embedding API, 带自动重试。智谱 API 兼容 OpenAI 接口。"""

from openai import OpenAI

from doubase.embedding.base import BaseEmbedder
from doubase.api_retry import retry_call

# 智谱 embedding API 单次请求最多 64 条输入，超出需分批发送
BATCH_SIZE = 64


class ZhipuEmbedder(BaseEmbedder):
    """通过智谱 (ZhipuAI) API 进行 Embedding。"""

    def __init__(self, api_key: str, model: str, base_url: str):
        # timeout=60: 默认 600s 会让挂起的请求卡 10 分钟才重试，压缩到 1 分钟内触发退避重试
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            response = retry_call(
                self._client.embeddings.create,
                model=self._model,
                input=batch,
                label=f"Zhipu embed ({len(batch)} texts)",
            )
            # 分批返回结果需按原顺序拼接，保持与输入一致
            results.extend(item.embedding for item in response.data)
        return results

    def embed_query(self, text: str) -> list[float]:
        result = self.embed([text])
        return result[0] if result else []
