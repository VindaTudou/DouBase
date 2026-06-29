"""写入器 — 从分析结果生成 Markdown 总结文件。"""

from datetime import datetime, timezone
from pathlib import Path


def write_summary(
    output_dir: str,
    project_name: str,
    project_source: str,
    file_path: str,
    language: str,
    analysis_text: str,
) -> str:
    """将单文件分析结果写入 Markdown 文件。"""
    out = Path(output_dir) / project_name
    out.mkdir(parents=True, exist_ok=True)

    rel = Path(file_path).relative_to(project_source)
    safe_name = str(rel).replace("/", "_").replace("\\", "_").replace(".", "_")
    md_file = out / f"{safe_name}.md"

    frontmatter = f"""---
project: {project_name}
source_path: {file_path}
analyzed_at: {datetime.now(timezone.utc).isoformat()}
language: {language}
---"""

    content = f"{frontmatter}\n\n{analysis_text}"
    md_file.write_text(content, encoding="utf-8")
    return str(md_file.resolve())


def write_overview(
    output_dir: str,
    project_name: str,
    project_source: str,
    overview_text: str,
) -> str:
    """将项目综述写入 overview.md。"""
    out = Path(output_dir) / project_name
    out.mkdir(parents=True, exist_ok=True)

    md_file = out / "overview.md"
    frontmatter = f"""---
project: {project_name}
source_path: {project_source}
analyzed_at: {datetime.now(timezone.utc).isoformat()}
type: overview
---"""

    content = f"{frontmatter}\n\n{overview_text}"
    md_file.write_text(content, encoding="utf-8")
    return str(md_file.resolve())
