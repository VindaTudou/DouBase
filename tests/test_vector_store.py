import tempfile
from doubase.storage.vector_store import VectorStore
from doubase.chunker.chunker import Chunk


def _make_chunk(text="test content", source_path="/tmp/test.md", idx=0, hash_val="abc123"):
    return Chunk(text=text, source_path=source_path, chunk_index=idx, content_hash=hash_val)


def test_add_and_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(persist_dir=tmpdir, collection_name="test_notes")
        chunks = [
            _make_chunk("Redis 持久化使用 RDB 和 AOF", "/notes/redis.md", 0, "h1"),
            _make_chunk("Python 是一门编程语言", "/notes/python.md", 0, "h2"),
        ]
        count = store.add_chunks_with_embeddings(
            chunks,
            [[0.1] * 1536, [0.2] * 1536],
        )
        assert count == 2

        results = store.search([0.1] * 1536, top_k=2)
        assert len(results) == 2


def test_get_existing_hash():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(persist_dir=tmpdir, collection_name="test_notes")
        hash_val = "abcdef1234567890"
        store.add_chunks_with_embeddings(
            [_make_chunk("data", "/notes/file.md", 0, hash_val)],
            [[0.1] * 1536],
        )
        found = store.get_existing_hash("/notes/file.md")
        assert found == hash_val


def test_get_existing_hash_returns_none_for_new_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(persist_dir=tmpdir, collection_name="test_notes")
        found = store.get_existing_hash("/notes/nonexistent.md")
        assert found is None


def test_delete_by_source():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(persist_dir=tmpdir, collection_name="test_notes")
        store.add_chunks_with_embeddings([
            _make_chunk("chunk 1", "/notes/keep.md", 0, "h1"),
            _make_chunk("chunk 2", "/notes/remove.md", 0, "h2"),
        ], [[0.1] * 1536, [0.2] * 1536])
        deleted = store.delete_by_source("/notes/remove.md")
        assert deleted >= 1

        remaining_hash = store.get_existing_hash("/notes/remove.md")
        assert remaining_hash is None

        keep_hash = store.get_existing_hash("/notes/keep.md")
        assert keep_hash == "h1"
