"""基于 token 计数的滑动窗口文本分块器。"""

from dataclasses import dataclass, field


@dataclass
class Chunk:
    """单个文本块及其元数据，可直接用于向量化。

    Attributes:
        text: chunk 文本内容。
        source_path: 原始文件的绝对路径。
        chunk_index: 文档内的从零开始的索引。
        content_hash: 源文件内容的 SHA256 哈希（用于去重）。
        metadata: 分块元数据（heading_path, heading_text, strategy 等）。
    """

    text: str
    source_path: str
    chunk_index: int
    content_hash: str
    metadata: dict = field(default_factory=dict)


class Chunker:
    """将文本按 token 数拆分为重叠的 chunk。

    使用 tiktoken cl100k_base 编码进行精确计数。
    如果 tiktoken 不可用，回退到近似字符级分块。
    """

    def __init__(self, config: dict):
        self.chunk_size = config.get("chunk_size", 512)
        self.chunk_overlap = config.get("chunk_overlap", 64)
        self._encoding = None
        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            pass

    def _encode(self, text: str) -> list[int]:
        """将文本编码为 token ID 列表。"""
        if self._encoding is not None:
            return self._encoding.encode(text)
        return list(range(len(text) // 4 + 1))

    def _decode(self, tokens: list[int]) -> str:
        """将 token ID 列表解码为文本字符串。"""
        if self._encoding is not None and hasattr(self._encoding, 'decode'):
            return self._encoding.decode(tokens)
        return ""

    def chunk_text(self, text: str, source_path: str, content_hash: str) -> list[Chunk]:
        """将文本拆分为重叠的 chunk，用于向量化。"""
        if not text.strip():
            return []

        tokens = self._encode(text)
        chunks = []
        step = max(1, self.chunk_size - self.chunk_overlap)

        for i in range(0, len(tokens), step):
            chunk_token_ids = tokens[i:i + self.chunk_size]
            if self._encoding is not None:
                chunk_text = self._decode(chunk_token_ids)
            else:
                char_ratio = len(text) / max(1, len(tokens))
                start_char = int(i * char_ratio)
                end_char = int((i + self.chunk_size) * char_ratio)
                chunk_text = text[start_char:end_char]

            if chunk_text.strip():
                chunks.append(Chunk(
                    text=chunk_text.strip(),
                    source_path=source_path,
                    chunk_index=len(chunks),
                    content_hash=content_hash,
                ))

        return chunks


def chunk_by_headings(
    text: str,
    source_path: str,
    content_hash: str,
    chunker: "Chunker",
) -> list[Chunk]:
    """Stage 1+2: 按 # 标题切分 -> 长段落滑动窗口兜底。

    仅对 .md 文件调用此函数。.docx/.pdf 继续使用 chunker.chunk_text()。
    """
    from doubase.chunker.heading_splitter import split_by_headings

    sections = split_by_headings(text)
    all_chunks = []

    for section in sections:
        tokens = chunker._encode(section.body_text)
        if len(tokens) <= chunker.chunk_size:
            # 短段落 -> 单个 chunk
            all_chunks.append(Chunk(
                text=section.body_text,
                source_path=source_path,
                chunk_index=0,  # 后续全局编号修正
                content_hash=content_hash,
                metadata={
                    "heading_path": section.heading_path,
                    "heading_text": section.heading_text,
                    "strategy": "heading",
                },
            ))
        else:
            # 长段落 -> 滑动窗口切分
            sub_text = section.body_text
            sub_tokens = chunker._encode(sub_text)
            step = max(1, chunker.chunk_size - chunker.chunk_overlap)

            for i in range(0, len(sub_tokens), step):
                chunk_token_ids = sub_tokens[i:i + chunker.chunk_size]
                if chunker._encoding is not None:
                    chunk_text = chunker._decode(chunk_token_ids)
                else:
                    char_ratio = len(sub_text) / max(1, len(sub_tokens))
                    start_char = int(i * char_ratio)
                    end_char = int((i + chunker.chunk_size) * char_ratio)
                    chunk_text = sub_text[start_char:end_char]

                if chunk_text.strip():
                    all_chunks.append(Chunk(
                        text=chunk_text.strip(),
                        source_path=source_path,
                        chunk_index=0,  # 后续全局编号修正
                        content_hash=content_hash,
                        metadata={
                            "heading_path": section.heading_path,
                            "heading_text": section.heading_text,
                            "strategy": "sliding_window",
                        },
                    ))

    # 全局编号
    for i, c in enumerate(all_chunks):
        c.chunk_index = i

    return all_chunks
