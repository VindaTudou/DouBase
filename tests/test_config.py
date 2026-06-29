import os
import tempfile
from doubase.config import load_config, resolve_env_vars


def test_resolve_env_vars():
    os.environ["TEST_VAR"] = "my-secret"
    config = {
        "llm": {
            "api_key": "${TEST_VAR}",
            "model": "deepseek-chat",
            "count": 42,
        }
    }
    result = resolve_env_vars(config)
    assert result["llm"]["api_key"] == "my-secret"
    assert result["llm"]["model"] == "deepseek-chat"
    assert result["llm"]["count"] == 42


def test_resolve_tilde():
    config = {"storage": {"persist_dir": "~/test"}}
    result = resolve_env_vars(config)
    assert result["storage"]["persist_dir"].startswith("/")
    assert "~" not in result["storage"]["persist_dir"]


def test_missing_env_var_returns_empty():
    config = {"api_key": "${MISSING_VAR_12345}"}
    result = resolve_env_vars(config)
    assert result["api_key"] == ""


def test_load_config_from_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("llm:\n  provider: deepseek\n  deepseek:\n    api_key: test-key\n")
        f.flush()
        config = load_config(f.name)
        assert config["llm"]["provider"] == "deepseek"
        assert config["llm"]["deepseek"]["api_key"] == "test-key"
        os.unlink(f.name)


def test_load_config_defaults_to_project_root():
    config = load_config()
    assert "llm" in config
    assert "embedding" in config
    assert "storage" in config
