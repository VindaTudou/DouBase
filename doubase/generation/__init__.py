"""LLM 生成层 — 模型无关的对话接口。"""

from doubase.generation.base import BaseLLM
from doubase.generation.deepseek import DeepSeekLLM

__all__ = ["BaseLLM", "DeepSeekLLM", "get_llm"]


def get_llm(config: dict, override_provider: str = None) -> BaseLLM:
    """工厂函数：返回配置指定的 LLM 实例。

    Args:
        config: 完整配置字典。
        override_provider: 不为 None 时，使用此 provider 而非配置中的默认值。
    """
    llm_config = config["llm"]
    provider = override_provider or llm_config["provider"]

    if provider == "deepseek":
        cfg = llm_config["deepseek"]
        if not cfg.get("api_key", "").strip():
            raise ValueError(
                "DeepSeek API Key 未设置。"
                "请设置环境变量 DEEPSEEK_API_KEY，或在 config.yaml 中填写 api_key。"
            )
        return DeepSeekLLM(
            api_key=cfg["api_key"],
            model=cfg["model"],
            base_url=cfg["base_url"],
        )
    elif provider in ("openai", "openai_compat"):
        from doubase.generation.openai_compat import OpenAICompatLLM
        cfg = llm_config[provider]
        if not cfg.get("api_key", "").strip():
            env_var = "OPENAI_API_KEY" if provider == "openai" else "CUSTOM_API_KEY"
            raise ValueError(
                f"LLM provider '{provider}' 的 API Key 未设置。"
                f"请设置环境变量 {env_var}，或在 config.yaml 中填写 api_key。"
            )
        return OpenAICompatLLM(
            api_key=cfg["api_key"],
            model=cfg["model"],
            base_url=cfg.get("base_url", "https://api.openai.com/v1"),
        )
    else:
        raise ValueError(f"未知的 LLM provider: {provider}")
