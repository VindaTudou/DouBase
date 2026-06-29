from pathlib import Path
from doubase.analyzer.scanner import scan_project, _score_name

FIXTURES = Path(__file__).parent / "fixtures"


def test_score_name_core():
    assert _score_name("src/core/engine.py") >= 0.9


def test_score_name_utils():
    assert _score_name("/path/to/utils.py") == 0.3


def test_score_name_default():
    assert _score_name("unknown_file.py") == 0.5


def test_scan_project_finds_files():
    project = str(FIXTURES / "mini_project")
    results = scan_project(project)
    assert len(results) >= 2
    paths = [r["path"] for r in results]
    assert any("engine.py" in p for p in paths)
    assert any("helper.py" in p for p in paths)


def test_scan_project_sorts_by_score():
    project = str(FIXTURES / "mini_project")
    results = scan_project(project)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_scan_project_with_focus():
    project = str(FIXTURES / "mini_project")
    results = scan_project(project, focus="core")
    assert len(results) >= 2
    if len(results) >= 2:
        top_paths = [r["path"] for r in results[:2]]
        assert any("core" in p for p in top_paths)
