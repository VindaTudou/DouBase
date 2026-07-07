"""DeepSeek Chat API — 兼容 OpenAI 接口，带自动重试。"""

from collections.abc import Iterator

from openai import OpenAI

from doubase.generation.base import BaseLLM
from doubase.api_retry import retry_call


class DeepSeekLLM(BaseLLM):
    """DeepSeek API 的 LLM 客户端（兼容 OpenAI 接口）。"""

    def __init__(self, api_key: str, model: str, base_url: str):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def chat(self, messages: list[dict], **kwargs) -> str:
        response = retry_call(
            self._client.chat.completions.create,
            model=self._model,
            messages=messages,
            **kwargs,
            label="DeepSeek chat",
        )
        return response.choices[0].message.content or ""

    def chat_stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        stream = retry_call(
            self._client.chat.completions.create,
            model=self._model,
            messages=messages,
            stream=True,
            **kwargs,
            label="DeepSeek chat_stream",
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
