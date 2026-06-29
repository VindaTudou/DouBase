"""项目扫描器 — 发现源码文件并按重要性排序。"""

import os
from pathlib import Path

EXCLUDE_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", "vendor",
    ".venv", "venv", "env", ".tox", ".eggs",
    "__MACOSX", ".DS_Store",
}

SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
    ".java", ".c", ".cpp", ".h", ".hpp", ".cc", ".cs",
    ".rb", ".php", ".swift", ".kt", ".scala", ".clj",
    ".ex", ".exs", ".erl", ".hrl",
}

NAME_KEYWORDS = {
    "algorithm": 1.0, "algo": 1.0,
    "core": 0.9, "engine": 0.9,
    "main": 0.8,
    "init": 0.5,
    "utils": 0.3, "helper": 0.3, "helpers": 0.3,
}

PATH_KEYWORDS = {
    "src": 0.8, "lib": 0.8, "core": 0.85,
    "include": 0.7,
    "tests": 0.2, "test": 0.2, "spec": 0.2,
    "vendor": 0.1, "node_modules": 0.0,
}

DEFAULT_NAME_SCORE = 0.5
DEFAULT_PATH_SCORE = 0.5
MAX_FILES = 50
LARGE_PROJECT_THRESHOLD = 500


def _score_name(file_path: str) -> float:
    stem = Path(file_path).stem.lower()
    for keyword, score in NAME_KEYWORDS.items():
        if keyword in stem:
            return score
    return DEFAULT_NAME_SCORE


def _score_path(file_path: str, project_root: str, focus_dir: str = None) -> float:
    rel = Path(file_path).relative_to(project_root)
    parts = rel.parts[:-1]

    if focus_dir:
        focus_parts = Path(focus_dir).parts
        if all(p in parts for p in focus_parts):
            return 1.0

    if not parts:
        return 0.6

    scores = [PATH_KEYWORDS.get(p.lower(), DEFAULT_PATH_SCORE) for p in parts]
    return sum(scores) / len(scores) if scores else DEFAULT_PATH_SCORE


def _detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    lang_map = {
        ".py": "python",
        ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx",
        ".go": "go", ".rs": "rust", ".java": "java",
        ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
        ".cs": "csharp", ".rb": "ruby", ".php": "php",
        ".swift": "swift", ".kt": "kotlin",
    }
    return lang_map.get(ext, "unknown")


def scan_project(project_dir: str, focus: str = None) -> list[dict]:
    """扫描项目目录，返回按重要性排序的重要源文件列表。

    Args:
        project_dir: 项目根目录路径。
        focus: 可选的优先子目录。

    Returns:
        包含 path, content, language, score 的 dict 列表，按 score 降序排列。
    """
    root = Path(project_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"项目目录未找到: {project_dir}")

    if focus:
        focus_path = (root / focus).resolve()
        if not focus_path.exists():
            raise FileNotFoundError(f"Focus 目录未找到: {focus_path}")

    file_entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in SOURCE_EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, fname)
            file_entries.append(full_path)

    raw_entries = []
    max_len = 0
    for fpath in file_entries:
        try:
            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
            raw_entries.append((fpath, content))
            max_len = max(max_len, len(content))
        except Exception:
            continue

    scored_files = []
    for fpath, content in raw_entries:
        length_score = len(content) / max(1, max_len)
        name_score = _score_name(fpath)
        path_score = _score_path(fpath, str(root), focus)
        total = 0.3 * length_score + 0.4 * name_score + 0.3 * path_score

        scored_files.append({
            "path": fpath,
            "content": content,
            "language": _detect_language(fpath),
            "score": round(total, 4),
        })

    scored_files.sort(key=lambda x: x["score"], reverse=True)

    if len(scored_files) > MAX_FILES and len(file_entries) > LARGE_PROJECT_THRESHOLD:
        scored_files = scored_files[:MAX_FILES]

    return scored_files
