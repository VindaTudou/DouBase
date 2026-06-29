import os
import tempfile
from doubase.config import load_config, resolve_env_vars


def test_resolve_env_vars():
    old_value = os.environ.get("TEST_VAR")
    try:
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
    finally:
        if old_value is None:
            os.environ.pop("TEST_VAR", None)
        else:
            os.environ["TEST_VAR"] = old_value


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


def test_env_var_with_default_when_missing():
    """${VAR:-default} — 变量缺失时使用默认值"""
    config = {"model": "${MISSING_VAR_999:-gpt-4o}"}
    result = resolve_env_vars(config)
    assert result["model"] == "gpt-4o"


def test_env_var_with_default_when_set():
    """${VAR:-default} — 变量存在时使用变量值"""
    old = os.environ.get("TEST_DEFAULT_VAR")
    try:
        os.environ["TEST_DEFAULT_VAR"] = "deepseek-chat"
        config = {"model": "${TEST_DEFAULT_VAR:-gpt-4o}"}
        result = resolve_env_vars(config)
        assert result["model"] == "deepseek-chat"
    finally:
        if old is None:
            os.environ.pop("TEST_DEFAULT_VAR", None)
        else:
            os.environ["TEST_DEFAULT_VAR"] = old


def test_load_config_defaults_to_project_root():
    config = load_config()
    assert "llm" in config
    assert "embedding" in config
    assert "storage" in config
