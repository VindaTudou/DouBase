import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "ask" in result.stdout
    assert "ingest" in result.stdout
    assert "analyze" in result.stdout


def test_cli_ask_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli", "ask", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_ingest_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli", "ingest", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_analyze_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli", "analyze", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_no_command_shows_help():
    result = subprocess.run(
        [sys.executable, "-m", "doubase.cli"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
