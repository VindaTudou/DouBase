# DouBase 多轮对话记忆 — 设计文档

> 创建日期: 2026-07-06
> 状态: 设计中 → 待评审

## 1. 目标

在 REPL 模式中增加多轮对话记忆能力，使 agent 能引用前文、支持追问和上下文补全。记忆分层为：

1. **最近 N 轮完整保留**（完整消息，直接出现在 Prompt 中）
2. **超出 N 轮的旧对话智能摘要**（LLM 压缩，注入 system prompt）
3. **持久化**（可选 `--resume` 加载历史）

CLI 模式（`doubase ask`）不增加此功能，保持无状态。

## 2. 架构

```
┌─────────────────────────────────────┐
│  REPL (doubase/repl.py)             │
│                                     │
│  memory = ConversationMemory(N=5)   │  ← 创建/加载/保存
│                                     │
│  用户提问                            │
│    → memory.get_history()           │
│    → run_ask(q, history=history)    │
│    → memory.add(question, answer)   │
│    → 可能触发 _compress()            │
└─────────────────────────────────────┘
           │
           ▼ 传入 history: list[dict]
┌─────────────────────────────────────┐
│  Pipeline (doubase/pipeline.py)     │
│                                     │
│  _build_ask_prompt(q, chunks,       │
│                    history=None)     │  ← 新增 history 参数
│                                     │
│  [system] 系统提示 + 摘要            │
│  ...历史消息...                      │
│  [user] 当前问题 + 检索结果          │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  ConversationMemory                 │
│  (doubase/memory.py) 新增           │
│                                     │
│  messages: list[dict]   最近 N 轮   │
│  summary: str           旧对话摘要   │
│  max_turns: int = 5                  │
│                                     │
│  + add(question, answer)            │
│  + get_history() -> list[dict]      │
│  + save(name) / load(name)          │
│  - _compress()                      │
└─────────────────────────────────────┘
```

## 3. ConversationMemory 详细设计

### 3.1 数据结构

```python
@dataclass
class ConversationMemory:
    max_turns: int = 5                # 保留最近 N 轮完整消息
    messages: list[dict]              # 最近 N 轮 [{role, content}, ...]
    summary: str = ""                 # 超出 N 轮后的摘要
    summary_turns: int = 0            # 摘要涵盖了多少轮
```

### 3.2 核心方法

**add(question, answer)**

```python
def add(self, question: str, answer: str):
    self.messages.append({"role": "user", "content": question})
    self.messages.append({"role": "assistant", "content": answer})
    
    # 超过 max_turns → 触发压缩
    while len(self.messages) > self.max_turns * 2:
        self._compress()  # 压缩最早的一轮
```

**_compress()（内部方法）**

将 messages 中最早的一对 Q&A 移出，合并到 summary 中。调用 LLM：

```python
def _compress(self, llm):
    # 取最早一轮 Q&A
    q = self.messages[0]["content"]
    a = self.messages[1]["content"]
    self.messages = self.messages[2:]
    
    # LLM 压缩 prompt
    prompt = f"""请将以下对话压缩为一句简短摘要。

当前摘要: {self.summary or "无"}

本轮对话:
用户: {q}
助手: {a}

请输出一句融合了已有摘要和新对话的简短摘要（中文，不超过80字）。仅输出摘要本身。"""
    
    self.summary = llm.chat([{"role": "user", "content": prompt}]).strip()
    self.summary_turns += 1
```

**get_history() -> list[dict]**

返回直接注入 Prompt 的消息列表：

```python
def get_history(self) -> list[dict]:
    result = []
    if self.summary:
        result.append({
            "role": "system",
            "content": f"[对话记忆] 之前已讨论: {self.summary}"
        })
    result.extend(self.messages)
    return result
```

### 3.3 持久化

保存到 `~/.doubase/sessions/{name}.json`：

```json
{
  "max_turns": 5,
  "messages": [...],
  "summary": "...由LLM压缩的历史摘要",
  "summary_turns": 3
}
```

```python
def save(self, name: str = "default"):
    path = Path("~/.doubase/sessions").expanduser()
    path.mkdir(parents=True, exist_ok=True)
    data = {
        "max_turns": self.max_turns,
        "messages": self.messages,
        "summary": self.summary,
        "summary_turns": self.summary_turns,
    }
    (path / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))

@classmethod
def load(cls, name: str = "default") -> "ConversationMemory":
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

## 4. Pipeline 变更

### 4.1 _build_ask_prompt 签名

```python
def _build_ask_prompt(
    question: str,
    chunks: list[dict],
    history: list[dict] = None,  # 新增
) -> list[dict]:
```

### 4.2 Prompt 拼接顺序

```
1. [system] 你是一个知识助手。请综合...      ← 原有系统提示
2. [system] [对话记忆] 之前已讨论: ...       ← 仅当有 summary
3. [user] 第一轮问题                         ← 历史完整消息
4. [assistant] 第一轮回答
5. [user] 第二轮问题
...
N. [user] 当前问题 + 本地检索结果             ← 当前轮
```

```python
def _build_ask_prompt(question, chunks, history=None):
    system_prompt = """你是一个知识助手。请综合以下两个来源来回答用户问题:
1. 用户本地笔记中的相关内容 (见下文)
2. 你自己的通用知识

规则:
- 如果本地笔记有相关信息，优先引用，并注明来源文件路径
- 如果本地笔记没有覆盖的部分，用你自己的知识补充，并标注"[通用知识]"
- 不要编造本地笔记中不存在的内容
- 用中文回答"""

    messages = [{"role": "system", "content": system_prompt}]
    
    # 注入历史
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
        user_parts.append("\n(本地笔记中未找到相关内容，请使用你的通用知识回答)")
    
    messages.append({"role": "user", "content": "\n".join(user_parts)})
    return messages
```

### 4.3 run_ask 签名

```python
def run_ask(
    question: str,
    config: dict,
    llm_override: str = None,
    embedding_override: str = None,
    render_markdown: bool = False,
    on_before_stream=None,
    on_retrieval_done=None,
    history: list[dict] = None,  # 新增
):
```

内部分块不变，仅将 `history` 透传给 `_build_ask_prompt`。

## 5. REPL 变更

### 5.1 CLI 参数

```bash
doubase repl                 # 新会话
doubase repl --resume        # 加载 default 会话
doubase repl --resume 2026-07-06  # 加载指定会话
doubase repl --new           # 强制新会话（不加载历史）
```

### 5.2 REPL 主循环

```python
def start_repl(config_path=None, resume=None, new=False):
    config = load_config(config_path)
    
    # 初始化记忆
    if new:
        memory = ConversationMemory()
    elif resume:
        memory = ConversationMemory.load(resume) if resume is not True else ConversationMemory.load("default")
    else:
        memory = ConversationMemory()
    
    # 欢迎界面显示记忆状态
    if memory.messages or memory.summary:
        console.print(f"[dim]已加载 {memory.summary_turns + len(memory.messages)//2} 轮历史[/dim]")
    
    while True:
        user_input = ...
        cmd, content = _parse_command(user_input)
        
        if cmd is None and content:
            spinner = RunningIndicator("正在检索")
            spinner.start()
            try:
                history = memory.get_history()
                answer = run_ask(
                    question=content, config=config,
                    render_markdown=True,
                    history=history,
                    on_retrieval_done=spinner.stop,
                )
                # 从 run_ask 的返回值获取 answer（需修改 run_ask 返回 answer）
                memory.add(content, answer)
            except:
                spinner.stop()
        
        elif cmd == "exit":
            memory.save("default")
            ...
```

### 5.3 /clear 命令

新增命令清除当前会话记忆：

```
/clear   清空对话记忆，重新开始
```

### 5.4 自动保存

每次 `/exit` 时自动保存到 `default.json`。`Ctrl+C` 退出时也保存（signal handler）。

## 6. run_ask 返回值变更

当前 `run_ask` 流式输出，不返回 answer 文本。REPL 需要 answer 来记录记忆。

修改方式：`run_ask` 内部在流式输出时同时累积 `accumulator`，最终返回给调用方。

```python
def run_ask(...) -> str | None:  # 返回 answer 文本
    ...
    accumulator = ""
    with Live(...):
        for token in llm.chat_stream(messages):
            accumulator += token
            ...
        # 最终帧
        live.update(Markdown("● " + accumulator))
    return accumulator
```

CLI 模式（`doubase ask`）同样返回但忽略返回值。

## 7. 压缩 LLM 调用配置

摘要压缩使用配置中的主 LLM provider（DeepSeek），不增加额外配置项。

每次压缩约消耗 ~200 tokens（prompt）+ ~50 tokens（输出摘要），费用可忽略。

## 8. 测试策略

- `tests/test_memory.py` — 单元测试 add / get_history / _compress / save / load
- `tests/test_pipeline.py` 追加 — 测试 `_build_ask_prompt` with history
- REPL 集成测试无法自动化（需要交互终端），手动验证

## 9. 总结

| 维度 | 决策 |
|------|------|
| 记忆层位置 | REPL 层（pipeline 保持无状态） |
| 完整保留轮数 | N = 5 |
| 超限策略 | LLM 智能摘要（每次压缩一轮） |
| 持久化 | JSON 文件 → `~/.doubase/sessions/` |
| CLI 模式 | 不受影响（无记忆） |
| 摘要 LLM | 跟随主 LLM provider |

## 10. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-07-06 | 初始版本 |
