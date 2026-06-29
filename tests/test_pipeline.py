import tempfile
import os
from pathlib import Path
from doubase.pipeline import _hash_file, _collect_files, estimate_ingest


def test_hash_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("hello world")
        f.flush()
        result = _hash_file(f.name)
        assert len(result) == 64
        os.unlink(f.name)


def test_collect_files_expands_directories():
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "a.md").write_text("a")
        Path(tmpdir, "b.docx").write_text("b")
        Path(tmpdir, "c.txt").write_text("c")
        files = _collect_files([tmpdir])
        assert len(files) == 3
        assert any("a.md" in f for f in files)


def test_estimate_ingest_with_markdown():
    config = {
        "chunker": {"chunk_size": 512, "chunk_overlap": 64},
        "embedding": {
            "provider": "zhipu",
            "zhipu": {
                "api_key": "test",
                "model": "embedding-2",
                "base_url": "https://test.com",
            },
        },
        "pricing": {"zhipu": {"embed_price": 0.5}},
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        md_file = Path(tmpdir, "test.md")
        md_file.write_text("# Hello\n\n" + "This is a test. " * 20)
        est = estimate_ingest([str(md_file)], config)
        assert est["total_chunks"] >= 1
        assert est["total_tokens"] > 0
        assert est["total_cost"] >= 0


from doubase.pipeline import _build_ask_prompt


def test_build_ask_prompt_with_chunks():
    chunks = [
        {
            "text": "Redis 使用 RDB 快照",
            "source_path": "/notes/redis.md",
            "distance": 0.1,
        },
        {
            "text": "AOF 记录每次写操作",
            "source_path": "/notes/db.md",
            "distance": 0.2,
        },
    ]
    messages = _build_ask_prompt("Redis 如何持久化数据？", chunks)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "本地笔记" in messages[0]["content"]
    assert "/notes/redis.md" in messages[1]["content"]
    assert "/notes/db.md" in messages[1]["content"]
    assert "Redis 使用 RDB" in messages[1]["content"]


def test_build_ask_prompt_empty_chunks():
    messages = _build_ask_prompt("某个问题", [])
    assert len(messages) == 2
    assert "未找到相关内容" in messages[1]["content"]
    assert "通用知识" in messages[0]["content"]
