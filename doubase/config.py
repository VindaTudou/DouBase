"""配置管理：从 .env 文件和 YAML 加载配置。"""

import os
import re
from pathlib import Path

import yaml


def _load_dotenv():
    """加载项目根目录的 .env 文件到环境变量（不会覆盖已存在的变量）。"""
    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"

    if not env_file.exists():
        return

    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue
            # 解析 KEY=VALUE 或 KEY="VALUE" 或 KEY='VALUE'
            m = re.match(r'^(\w+)\s*=\s*(.+)$', line)
            if not m:
                continue
            key = m.group(1)
            value = m.group(2).strip()
            # 去除引号
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            # 不覆盖已在环境中设置的变量
            if key not in os.environ:
                os.environ[key] = value


def resolve_env_vars(config: dict) -> dict:
    """递归解析字符串值中的 ${VAR_NAME} 和 ${VAR_NAME:-default} 以及 ~ 路径。"""
    if isinstance(config, dict):
        return {k: resolve_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [resolve_env_vars(item) for item in config]
    elif isinstance(config, str):
        # 解析 ${VAR_NAME} 和 ${VAR_NAME:-默认值}
        def replacer(match):
            var_name = match.group(1)
            default = match.group(2)
            if default is not None:
                # ${VAR:-default} — 有默认值
                return os.environ.get(var_name, default)
            else:
                # ${VAR} — 无默认值
                return os.environ.get(var_name, "")

        result = re.sub(r"\$\{(\w+)(?::-([^}]*))?\}", replacer, config)
        # 展开 ~ 为用户主目录
        if result.startswith("~"):
            result = os.path.expanduser(result)
        return result
    else:
        return config


def load_config(path: str = None) -> dict:
    """加载配置：先加载 .env，再加载 YAML 并解析环境变量引用。

    Args:
        path: config.yaml 路径。为 None 时查找项目根目录下的 config.yaml。

    Returns:
        解析并处理后的配置字典。
    """
    # 1. 加载 .env 文件
    _load_dotenv()

    # 2. 加载 YAML
    if path is None:
        project_root = Path(__file__).resolve().parent.parent
        path = project_root / "config.yaml"
    else:
        path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"配置文件未找到: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)

    # 3. 解析 ${VAR_NAME} 引用
    return resolve_env_vars(raw_config)
