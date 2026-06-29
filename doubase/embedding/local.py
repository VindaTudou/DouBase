"""本地 embedding 模型 — 通过 sentence-transformers 实现（可选依赖）。"""

from doubase.embedding.base import BaseEmbedder


class LocalEmbedder(BaseEmbedder):
    """本地 embedding 模型（BGE 等），通过 sentence-transformers 运行。

    延迟加载模型，避免导入时即占用内存。
    """

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            except ImportError:
                raise ImportError(
                    "本地 embedding 需要 sentence-transformers。"
                    "请执行: pip install doubase[local-embed]"
                )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model()
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        self._ensure_model()
        embedding = self._model.encode([text], normalize_embeddings=True)
        return embedding[0].tolist()
