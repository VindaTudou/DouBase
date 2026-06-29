"""代码分析器 — 使用 LLM 分析源码文件。"""

from doubase.generation.base import BaseLLM

ANALYSIS_PROMPT_TEMPLATE = """分析以下代码文件，识别并总结:

1. 核心算法 — 描述算法思路、时间/空间复杂度
2. 关键数据结构 — 重要的类、结构体、接口及其用途
3. 设计模式 — 使用了哪些设计模式
4. 对外接口 — 公开的函数/方法及其签名和用途
5. 依赖关系 — 模块间依赖

用简洁的中文回答，使用 Markdown 格式。

文件路径: {file_path}
语言: {language}

代码:
```
{code}
```"""

SYNTHESIS_PROMPT_TEMPLATE = """以下是对项目 "{project_name}" 各文件的逐一分析:

{file_analyses}

请撰写一份项目整体综述，包含:
1. 项目架构概述 — 整体结构、分层设计
2. 核心算法一览 — 列出所有核心算法及其所在文件
3. 模块间调用关系 — 描述主要模块之间的依赖和调用关系

用简洁的中文回答，使用 Markdown 格式。"""


def build_analysis_prompt(file_path: str, code: str, language: str) -> list[dict]:
    """构建单文件分析提示词。"""
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        file_path=file_path,
        language=language,
        code=code[:8000],
    )
    return [{"role": "user", "content": prompt}]


def analyze_file(llm: BaseLLM, file_path: str, code: str, language: str) -> str:
    """分析单个文件，返回 Markdown 总结。"""
    messages = build_analysis_prompt(file_path, code, language)
    return llm.chat(messages)


def synthesize_overview(
    llm: BaseLLM,
    project_name: str,
    file_analyses: list[dict],
) -> str:
    """将各文件分析结果合成为项目综述。

    Args:
        project_name: 项目名称。
        file_analyses: {"file": str, "analysis": str} 列表。

    Returns:
        Markdown 格式的综述文本。
    """
    combined = "\n\n---\n\n".join(
        f"### {fa['file']}\n{fa['analysis']}" for fa in file_analyses
    )
    prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
        project_name=project_name,
        file_analyses=combined,
    )
    messages = [{"role": "user", "content": prompt}]
    return llm.chat(messages)
