import hashlib
from doubase.chunker.chunker import Chunker, Chunk


def test_chunker_splits_short_text_into_single_chunk():
    config = {"chunk_size": 100, "chunk_overlap": 20}
    chunker = Chunker(config)
    source_path = "/tmp/test.md"
    content_hash = hashlib.sha256(b"hello").hexdigest()
    chunks = chunker.chunk_text("hello world", source_path, content_hash)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].source_path == source_path
    assert chunks[0].chunk_index == 0
    assert chunks[0].content_hash == content_hash


def test_chunker_splits_long_text():
    config = {"chunk_size": 20, "chunk_overlap": 5}
    chunker = Chunker(config)
    text = " ".join(["word" + str(i) for i in range(80)])
    source_path = "/tmp/test.md"
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    chunks = chunker.chunk_text(text, source_path, content_hash)
    assert len(chunks) > 1
    for chunk in chunks:
        token_count = len(chunker._encode(chunk.text))
        assert token_count <= 25


def test_chunker_overlap():
    config = {"chunk_size": 50, "chunk_overlap": 10}
    chunker = Chunker(config)
    text = "unique first sentence. " * 5 + "unique last sentence. " * 5
    source_path = "/tmp/test.md"
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    chunks = chunker.chunk_text(text, source_path, content_hash)
    if len(chunks) > 1:
        tokens_0 = chunker._encode(chunks[0].text)
        tokens_1 = chunker._encode(chunks[1].text)
        overlap_found = any(t in tokens_1 for t in tokens_0[-5:])
        assert overlap_found


def test_chunker_handles_empty_text():
    config = {"chunk_size": 100, "chunk_overlap": 20}
    chunker = Chunker(config)
    chunks = chunker.chunk_text("", "/tmp/test.md", "abc123")
    assert len(chunks) == 0
