from unittest.mock import MagicMock
from doubase.memory import ConversationMemory


def test_memory_starts_empty():
    mem = ConversationMemory()
    assert mem.messages == []
    assert mem.summary == ""
    assert mem.summary_turns == 0
    assert mem.get_history() == []


def test_add_appends_q_and_a():
    mem = ConversationMemory()
    mem.add("问题1", "答案1")
    assert len(mem.messages) == 2
    assert mem.messages[0] == {"role": "user", "content": "问题1"}
    assert mem.messages[1] == {"role": "assistant", "content": "答案1"}


def test_get_history_no_summary():
    mem = ConversationMemory()
    mem.add("Q1", "A1")
    history = mem.get_history()
    assert len(history) == 2
    assert history[0]["role"] == "user"


def test_get_history_with_summary():
    mem = ConversationMemory()
    mem.summary = "之前聊了Redis"
    mem.add("Q1", "A1")
    history = mem.get_history()
    assert len(history) == 3
    assert history[0] == {"role": "system", "content": "[对话记忆] 之前已讨论: 之前聊了Redis"}


def test_compress_triggers_when_over_max_turns():
    mem = ConversationMemory(max_turns=2)
    mock_llm = MagicMock()
    mock_llm.chat.return_value = "Redis持久化相关讨论"

    mem.add("Q1", "A1")
    mem.add("Q2", "A2")
    assert len(mem.messages) == 4

    mem.add("Q3", "A3", llm=mock_llm)
    assert len(mem.messages) == 4
    assert mem.summary != ""
    assert mem.summary_turns == 1
    mock_llm.chat.assert_called_once()


def test_clear_resets_all():
    mem = ConversationMemory()
    mem.add("Q1", "A1")
    mem.summary = "历史"
    mem.clear()
    assert mem.messages == []
    assert mem.summary == ""
    assert mem.summary_turns == 0


def test_save_and_load():
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmpdir:
        def _fake_expanduser(self):
            return Path(str(self).replace("~", tmpdir, 1))

        with patch.object(Path, "expanduser", _fake_expanduser):
            mem = ConversationMemory()
            mem.add("Q1", "A1 long answer")
            mem.summary = "old stuff"
            mem.summary_turns = 2
            mem.save("test_session")

            loaded = ConversationMemory.load("test_session")
            assert len(loaded.messages) == 2
            assert loaded.summary == "old stuff"
            assert loaded.summary_turns == 2


def test_load_nonexistent_returns_empty():
    from pathlib import Path
    from unittest.mock import patch
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        def _fake_expanduser(self):
            return Path(str(self).replace("~", tmpdir, 1))

        with patch.object(Path, "expanduser", _fake_expanduser):
            mem = ConversationMemory.load("nonexistent")
            assert mem.messages == []
            assert mem.summary == ""
