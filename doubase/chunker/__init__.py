"""文本分块器 — 将文档拆分为可向量化的片段。"""

from doubase.chunker.chunker import Chunk, Chunker, chunk_by_headings
from doubase.chunker.heading_splitter import split_by_headings, HeadingSection
