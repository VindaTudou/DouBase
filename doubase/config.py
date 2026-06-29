"""配置管理：YAML 加载与环境变量插值。"""

import os
import re
from pathlib import Path

import yaml


def resolve_env_vars(config: dict) -> dict:
    """递归解析字符串值中的 ${VAR_NAME} 和 ~ 路径。"""
    if isinstance(config, dict):
        return {k: resolve_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [resolve_env_vars(item) for item in config]
    elif isinstance(config, str):
        def replacer(match):
            var_name = match.group(1)
            return os.environ.get(var_name, "")

        result = re.sub(r"\$\{(\w+)\}", replacer, config)
        if result.startswith("~"):
            result = os.path.expanduser(result)
        return result
    else:
        return config


def load_config(path: str = None) -> dict:
    """从 YAML 文件加载配置。

    Args:
        path: config.yaml 路径。为 None 时查找项目根目录下的 config.yaml。

    Returns:
        解析并处理后的配置字典。
    """
    if path is None:
        project_root = Path(__file__).resolve().parent.parent
        path = project_root / "config.yaml"
    else:
        path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"配置文件未找到: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    return resolve_env_vars(raw_config)
