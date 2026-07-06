# 多轮对话记忆 — 实现计划

> **目标：** REPL 中增加多轮对话记忆（最近 5 轮完整 + 超限 LLM 摘要 + 持久化到 `~/.doubase/sessions/`）。Pipeline 保持无状态，新增 `history` 参数。

**架构：** 新增 `doubase/memory.py`（ConversationMemory），`pipeline.py` 中 `_build_ask_prompt` 和 `run_ask` 增加 `history` 参数，`run_ask` 返回 answer 文本。REPL 层管理记忆生命周期。

**技术栈：** Python >=3.11, rich, json

## 全局约束

- Python >=3.11（`/opt/homebrew/bin/python3.11`）
- 现有 67 个测试不能破坏
- CLI 模式（`doubase ask`）不受影响
- 摘要压缩跟随主 LLM provider
- max_turns = 5（最近 5 轮完整保留）
- 持久化路径：`~/.doubase/sessions/{name}.json`

---

### 任务 1: ConversationMemory 核心类

**文件:**
- 创建: `doubase/memory.py`
- 创建: `tests/test_memory.py`

**接口:**
- 消耗: 无（纯 Python + json）
- 产出: `ConversationMemory(max_turns=5)` 数据类，方法 `add(question, answer)`, `get_history() -> list[dict]`, `clear()`, `save(name)`, `load(name)` 类方法

- [ ] **步骤 1: 编写测试**

创建 `tests/test_memory.py`:

```python
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

    # 填满 2 轮（4条消息）
    mem.add("Q1", "A1")
    mem.add("Q2", "A2")
    assert len(mem.messages) == 4  # 刚好满了，不触发

    # 第 3 轮触发压缩
    mem.add("Q3", "A3")
    # 压缩后：最早一轮被压缩成摘要，剩余 2 轮（4条）
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
    import tempfile, os
    from pathlib import Path
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(Path, "expanduser", return_value=Path(tmpdir)):
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
        with patch.object(Path, "expanduser", return_value=Path(tmpdir)):
            mem = ConversationMemory.load("nonexistent")
            assert mem.messages == []
            assert mem.summary == ""
```

- [ ] **步骤 2: 运行测试确认失败**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/test_memory.py -v`
预期: FAIL — 模块未找到

- [ ] **步骤 3: 编写实现**

创建 `doubase/memory.py`:

```python
"""对话记忆管理 — 多轮对话上下文保留与智能压缩。"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversationMemory:
    """多轮对话记忆。最近 max_turns 轮完整保留，超出部分由 LLM 压缩为摘要。

    Attributes:
        max_turns: 完整保留的最大轮数（默认 5）。
        messages: 最近 N 轮的完整消息列表 [{role, content}, ...]。
        summary: 超出 max_turns 的历史摘要。
        summary_turns: 摘要涵盖了多少轮对话。
    """

    max_turns: int = 5
    messages: list[dict] = field(default_factory=list)
    summary: str = ""
    summary_turns: int = 0

    def add(self, question: str, answer: str, llm=None):
        """记录一轮对话。超过 max_turns 时自动触发压缩。

        Args:
            question: 用户问题。
            answer: 助手回答全文。
            llm: BaseLLM 实例（压缩时需要）。为 None 时跳过压缩。
        """
        self.messages.append({"role": "user", "content": question})
        self.messages.append({"role": "assistant", "content": answer})

        # 超过 max_turns → 压缩最早的一轮
        while len(self.messages) > self.max_turns * 2 and llm is not None:
            self._compress(llm)

    def _compress(self, llm):
        """将最早一轮 Q&A 移出并合并到摘要中。"""
        q = self.messages[0]["content"]
        a = self.messages[1]["content"]
        self.messages = self.messages[2:]

        prompt = (
            f"请将以下对话压缩为一句简短摘要。\n\n"
            f"当前摘要: {self.summary or '无'}\n\n"
            f"本轮对话:\n用户: {q}\n助手: {a}\n\n"
            f"请输出一句融合了已有摘要和新对话的简短摘要（中文，不超过80字）。仅输出摘要本身。"
        )
        try:
            self.summary = llm.chat([{"role": "user", "content": prompt}]).strip()
        except Exception:
            # 压缩失败 → 保留原文片段防止信息丢失
            self.summary = f"{self.summary or ''} {q[:40]}...".strip()
        self.summary_turns += 1

    def get_history(self) -> list[dict]:
        """返回应注入 Prompt 的历史消息列表。包含摘要（如有）+ 完整消息。"""
        result = []
        if self.summary:
            result.append({
                "role": "system",
                "content": f"[对话记忆] 之前已讨论: {self.summary}",
            })
        result.extend(self.messages)
        return result

    def clear(self):
        """清空所有记忆。"""
        self.messages = []
        self.summary = ""
        self.summary_turns = 0

    def save(self, name: str = "default"):
        """持久化到 ~/.doubase/sessions/{name}.json。"""
        path = Path("~/.doubase/sessions").expanduser()
        path.mkdir(parents=True, exist_ok=True)
        data = {
            "max_turns": self.max_turns,
            "messages": self.messages,
            "summary": self.summary,
            "summary_turns": self.summary_turns,
        }
        (path / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    @classmethod
    def load(cls, name: str = "default") -> "ConversationMemory":
        """从 ~/.doubase/sessions/{name}.json 加载记忆。不存在则返回空实例。"""
        path = Path(f"~/.doubase/sessions/{name}.json").expanduser()
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        mem = cls(max_turns=data.get("max_turns", 5))
        mem.messages = data.get("messages", [])
        mem.summary = data.get("summary", "")
        mem.summary_turns = data.get("summary_turns", 0)
        return mem
```

- [ ] **步骤 4: 运行测试确认通过**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/test_memory.py -v`
预期: 8 PASS

- [ ] **步骤 5: 提交**

```bash
git add doubase/memory.py tests/test_memory.py
git commit -m "feat: add ConversationMemory with N-turn retention, LLM compression, and persistence"
```

---

### 任务 2: Pipeline 增加 history 参数 + run_ask 返回 answer

**文件:**
- 修改: `doubase/pipeline.py` — `_build_ask_prompt`（第 301 行）、`run_ask`（第 330 行）

**接口:**
- 消耗: 现有 pipeline 逻辑
- 产出: `_build_ask_prompt(q, chunks, history=None) -> list[dict]`；`run_ask(...) -> str` 返回 answer 文本

- [ ] **步骤 1: 修改 _build_ask_prompt**

读取 `doubase/pipeline.py`，找到 `_build_ask_prompt`（约第 301 行），将整个函数替换为：

```python
def _build_ask_prompt(
    question: str,
    chunks: list[dict],
    history: list[dict] = None,
) -> list[dict]:
    """构建混合 RAG 提示词：本地知识 + LLM 知识 + 对话历史。"""
    system_prompt = """你是一个知识助手。请综合以下两个来源来回答用户问题:
1. 用户本地笔记中的相关内容 (见下文)
2. 你自己的通用知识

规则:
- 如果本地笔记有相关信息，优先引用，并注明来源文件路径
- 如果本地笔记没有覆盖的部分，用你自己的知识补充，并标注"[通用知识]"
- 不要编造本地笔记中不存在的内容
- 用中文回答"""

    messages = [{"role": "system", "content": system_prompt}]

    # 注入对话历史
    if history:
        messages.extend(history)

    # 当前问题 + 检索结果
    user_parts = [question]
    if chunks:
        user_parts.append("\n---\n本地检索结果:")
        for i, chunk in enumerate(chunks, 1):
            source = chunk.get("source_path", "unknown")
            user_parts.append(f"\n[来源 {i}: {source}]\n{chunk['text']}")
    else:
        user_parts.append(
            "\n(本地笔记中未找到相关内容，请使用你的通用知识回答)"
        )

    messages.append({"role": "user", "content": "\n".join(user_parts)})
    return messages
```

- [ ] **步骤 2: 修改 run_ask 签名 + 返回值**

找到 `run_ask` 函数签名（约第 330-337 行），替换参数列表为：

```python
def run_ask(
    question: str,
    config: dict,
    llm_override: str = None,
    embedding_override: str = None,
    render_markdown: bool = False,
    on_before_stream=None,
    on_retrieval_done=None,
    history: list[dict] = None,
) -> str:
```

找到 `messages = _build_ask_prompt(question, chunks)` 这一行，改为：

```python
    messages = _build_ask_prompt(question, chunks, history=history)
```

找到 render_markdown 分支中 `accumulator = ""` 这行后面，确认 `return accumulator` 在 render_markdown 块**末尾**（Live with 结束后）。如果不是，在该 block 最后一行（`live.update(Markdown(...))` 之后）加 `return accumulator`。

找到 else 分支（非 render_markdown / CLI 模式），在流式输出完成后，加 `return accumulator`（需要新增 accumulator 变量）。CLI 模式的改造：

```python
    else:
        # CLI 模式：流式逐 token 输出
        accumulator = ""
        try:
            for token in llm.chat_stream(messages):
                accumulator += token
                console.print(token, end="", highlight=False)
            console.print()
        except Exception as e:
            console.print(f"\n[red]❌ LLM 调用失败: {e}[/red]")
            console.print("[dim]请检查网络连接和 API Key 配置。[/dim]")
        return accumulator
```

- [ ] **步骤 3: 运行全量测试**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/ -q`
预期: 75 passed（67 + 8 新）

- [ ] **步骤 4: 提交**

```bash
git add doubase/pipeline.py
git commit -m "feat: add history param to _build_ask_prompt, run_ask returns answer text"
```

---

### 任务 3: REPL 集成记忆

**文件:**
- 修改: `doubase/repl.py` — `start_repl`, `_handle_command`

**接口:**
- 消耗: `ConversationMemory`, `run_ask`（现在返回 str）
- 产出: REPL 支持 `--resume` / `--new` / `/clear` / 自动保存

- [ ] **步骤 1: 更新 start_repl 签名**

读取 `doubase/repl.py`，替换函数签名和初始化部分：

```python
def start_repl(config_path: str = None, resume: str = None, new: bool = False):
    """启动 DouBase 交互式 REPL。

    Args:
        config_path: 配置文件路径。
        resume: 加载指定会话名（"default"、日期等）。True 时加载 "default"。
        new: True 时强制新会话，不加载历史。
    """
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]❌ 配置错误: {e}[/red]")
        sys.exit(1)

    from doubase.memory import ConversationMemory

    # 初始化记忆
    if new:
        memory = ConversationMemory()
    elif resume:
        name = resume if resume is not True else "default"
        memory = ConversationMemory.load(name)
    else:
        memory = ConversationMemory()

    # 欢迎界面 + 记忆状态
    total_turns = memory.summary_turns + len(memory.messages) // 2
    if total_turns > 0:
        console.print(f"[dim]📝 已加载 {total_turns} 轮历史对话[/dim]")
```

- [ ] **步骤 2: 更新 REPL 主循环中的 ask 分支**

找到 `if cmd is None and content:` 后的 spinner + run_ask 调用，替换为：

```python
            spinner = RunningIndicator("正在检索")
            spinner.start()
            try:
                history = memory.get_history()
                llm = None
                if config.get("llm"):
                    from doubase.generation import get_llm
                    llm = get_llm(config)
                answer = run_ask(
                    question=content, config=config, render_markdown=True,
                    history=history,
                    on_retrieval_done=spinner.stop,
                )
                if answer:
                    memory.add(content, answer, llm=llm)
            except ValueError as e:
                spinner.stop()
                console.print(f"[red]❌ {e}[/red]")
            except Exception as e:
                spinner.stop()
                console.print(f"[red]❌ 出错了: {e}[/red]")
```

- [ ] **步骤 3: 添加 /clear 命令**

在 `_handle_command` 中添加 `clear` 分支（需要传入 memory 参数）。将 `_handle_command` 签名改为：

```python
def _handle_command(cmd: str, args: str, config: dict, memory=None) -> bool:
```

在 `elif cmd == "help":` 之后插入：

```python
    elif cmd == "clear":
        if memory:
            memory.clear()
            console.print("[dim]🗑️  对话记忆已清空[/dim]")
        else:
            console.print("[dim]当前无记忆[/dim]")
```

- [ ] **步骤 4: 更新 HELP_TEXT**

在 HELP_TEXT 的 `exit` 行上方加一行：

```python
  [cyan]/clear[/cyan]             清空对话记忆
```

更新 HINT_TEXT 加入 `/clear`。

- [ ] **步骤 5: /exit 时自动保存**

在 `_handle_command` 中 exit 分支改为：

```python
    if cmd == "exit" or cmd == "quit":
        if memory:
            memory.save("default")
        console.print("[dim]再见！[/dim]")
        return False
```

在 `start_repl` 的 EOF/KeyboardInterrupt 异常处理中也加保存：

```python
        except (EOFError, KeyboardInterrupt):
            memory.save("default")
            console.print("\n[dim]再见！[/dim]")
            break
```

- [ ] **步骤 6: 更新所有调用点**

`start_repl` 中调用 `_handle_command` 的地方传入 `memory`：

```python
                keep_running = _handle_command(cmd, content, config, memory=memory)
```

- [ ] **步骤 7: 更新 CLI 以支持 --resume / --new**

在 `doubase/cli.py` 中找到 repl_parser，添加参数：

```python
    repl_parser.add_argument("--resume", "-r", nargs="?", const=True,
                             help="加载历史会话（默认 default，可指定会话名）")
    repl_parser.add_argument("--new", "-n", action="store_true",
                             help="强制新会话")
```

在路由处更新 repl 调用：

```python
        elif args.command == "repl":
            from doubase.repl import start_repl
            resume_val = args.resume if hasattr(args, 'resume') else None
            new_val = args.new if hasattr(args, 'new') else False
            start_repl(resume=resume_val, new=new_val)
```

- [ ] **步骤 8: 运行全量测试**

执行: `/opt/homebrew/bin/python3.11 -m pytest tests/ -q`
预期: 75 passed（无回归）

- [ ] **步骤 9: 提交**

```bash
git add doubase/repl.py doubase/cli.py
git commit -m "feat: integrate ConversationMemory into REPL with --resume, /clear, auto-save"
```

---

## 实现注意事项

1. **任务顺序**: 1 → 2 → 3，严格按依赖顺序。memory.py 必须先于 pipeline 修改
2. **TDD**: 任务 1 先写测试，后实现
3. **python 版本**: 始终使用 `/opt/homebrew/bin/python3.11`
4. **CLI 向后兼容**: `doubase ask` 不受影响（history=None 时行为不变）
5. **现有 67 测试**: 不能破坏
