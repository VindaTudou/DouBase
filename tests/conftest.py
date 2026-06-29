import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def temp_config():
    """创建包含测试配置的临时目录。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        vectors_dir = Path(tmpdir) / "vectors"
        vectors_dir.mkdir()

        config_content = f"""
llm:
  provider: deepseek
  deepseek:
    api_key: test-key
    model: deepseek-chat
    base_url: https://api.deepseek.com/v1

embedding:
  provider: zhipu
  zhipu:
    api_key: test-key
    model: embedding-2
    base_url: https://open.bigmodel.cn/api/paas/v4

storage:
  persist_dir: {vectors_dir}
  collection_name: test_notes

chunker:
  chunk_size: 100
  chunk_overlap: 20

retrieval:
  top_k: 3

pricing:
  deepseek:
    input_price: 1.0
    output_price: 2.0
  zhipu:
    embed_price: 0.5
"""
        config_path.write_text(config_content)
        yield str(config_path)
