"""ChromaDB 向量存储 — 将 ChromaDB collection 封装为我们的 chunk 模型。"""

from pathlib import Path
from typing import Optional

from doubase.chunker.chunker import Chunk


class VectorStore:
    """基于 ChromaDB 的文档 chunk 向量存储。

    每个 chunk 存储时附带元数据: source_path, content_hash, chunk_index。
    去重逻辑在 ingest 层处理（embedding 前比对哈希），
    但 store 也暴露 get_existing_hash() 方法以支持该检查。
    """

    def __init__(self, persist_dir: str, collection_name: str):
        import chromadb
        persist_path = Path(persist_dir).expanduser().resolve()
        persist_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(persist_path))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks_with_embeddings(
        self, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> int:
        """添加带预计算 embedding 的 chunks。返回添加数量。"""
        if not chunks:
            return 0

        ids = []
        documents = []
        metadatas = []

        for chunk in chunks:
            chunk_id = f"{chunk.source_path}__{chunk.chunk_index}"
            ids.append(chunk_id)
            documents.append(chunk.text)
            metadatas.append({
                "source_path": chunk.source_path,
                "content_hash": chunk.content_hash,
                "chunk_index": chunk.chunk_index,
            })

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        return len(chunks)

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """搜索与 query embedding 最相似的 chunks。

        返回 dict 列表，每个 dict 包含: text, source_path, distance。
        """
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

        items = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                items.append({
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "source_path": results["metadatas"][0][i].get("source_path", "")
                        if results["metadatas"] else "",
                    "distance": results["distances"][0][i]
                        if results["distances"] else 0.0,
                })

        return items

    def delete_by_source(self, source_path: str) -> int:
        """删除指定源文件的所有 chunks。返回删除数量。"""
        existing = self._collection.get(
            where={"source_path": source_path},
        )
        if existing["ids"]:
            self._collection.delete(ids=existing["ids"])
            return len(existing["ids"])
        return 0

    def get_existing_hash(self, source_path: str) -> Optional[str]:
        """查询已索引文件的 content_hash，未找到则返回 None。"""
        existing = self._collection.get(
            where={"source_path": source_path},
            limit=1,
        )
        if existing["metadatas"]:
            return existing["metadatas"][0].get("content_hash")
        return None

    def count(self) -> int:
        """返回 collection 中的 chunk 总数。"""
        return self._collection.count()
