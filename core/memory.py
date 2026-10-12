"""记忆管理：对话记忆 + 长期记忆 + 上下文压缩。

两个文件的分工：
- chat_memory/session.jsonl：逐条追加的对话记录，重启后读回 → "记住刚才聊了什么"
- chat_memory/MEMORY.md：值得长期记住的事实（用户偏好、项目约定），
  每次调用模型前拼进 system prompt → "记住以后也可能有用的信息"

为什么用 jsonl 追加而不是每次重写整个文件：
1. 追加便宜，而且更容易命中模型服务商的 prefix KV cache（前缀不变 → 缓存命中 → 更快）
2. 某一行坏了只坏一行，不会整个文件解析失败
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.llm import call_llm_simple

MEMORY_DIR = Path("chat_memory")
LONG_TERM_HEADER = "# 长期记忆：用户偏好、重要事实、项目约定\n\n"

# 只有这些字段允许进入历史。
# usage 是"给程序看的元数据"，不属于对话，绝不能写进历史（有些兼容接口会报错）
MESSAGE_KEYS = {"role", "content", "tool_calls", "tool_call_id", "reasoning_content"}

MAX_CONTEXT_TOKENS = 128_000      # 模型上下文窗口（按你实际用的模型调整）
COMPRESS_THRESHOLD = 0.9          # 用到 90% 才压缩——摘要会丢细节，别压太早
KEEP_RECENT_MESSAGES = 6          # 压缩后保留最近几条原文

class Memory:
    """一份对话记录（jsonl）+ 一个长期记忆文件（md）。"""

    def __init__(self, directory: Path | str | None = None) -> None:
        self.dir = Path(directory or MEMORY_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.dir / "session.jsonl"
        self.long_term_file = self.dir / "MEMORY.md"

        # 注意：文件可能"存在但是空的"（上次被创建后没写过内容），
        # 所以不能只判断 exists()，还要判断内容是否为空
        if not self.long_term_file.exists() or not self.long_term_file.read_text(
            encoding="utf-8"
        ).strip():
            self.long_term_file.write_text(LONG_TERM_HEADER, encoding="utf-8")

        self.messages: list[dict[str, Any]] = self._load_session()

    def _load_session(self) -> list[dict[str, Any]]:
        """读回上次的对话，并把"没走完的一轮"丢掉。"""
        if not self.session_file.exists():
            return []

        messages: list[dict[str, Any]] = []
        for line in self.session_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue                      # 坏了一行不影响其他行（jsonl 的好处）

        # ---- 崩溃恢复 ----
        # 如果文件最后停在一个"有 tool_calls 但没有对应 tool 结果"的助手上，
        # 说明上次是中途退出的。这一轮必须丢掉——否则下次请求会因为
        # tool_calls 和 tool 结果配对不完整，被 API 直接拒绝。
        need_rewrite = False
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            if message.get("role") != "assistant" or not message.get("tool_calls"):
                continue

            tail = messages[index + 1:]
            if tail and not all(item.get("role") == "tool" for item in tail):
                break                          # 这一轮是完整的，不用动

            start = index - 1 if index > 0 and messages[index - 1].get("role") == "user" else index
            del messages[start:]               # 连它的 user 提问一起丢掉
            need_rewrite = True
            break

        if need_rewrite:
            self._rewrite_session(messages)

        return messages

    def _rewrite_session(self, messages: list[dict[str, Any]]) -> None:
        """整体重写（只在压缩 / 清理时用；平时都是 append）。"""
        with self.session_file.open("w", encoding="utf-8") as handle:
            for message in messages:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")

    def append(self, message: dict[str, Any]) -> dict[str, Any]:
        """加一条消息（先过滤字段，再写盘），返回清洗后的消息。"""
        cleaned = {key: value for key, value in message.items() if key in MESSAGE_KEYS}
        self.messages.append(cleaned)
        with self.session_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
        return cleaned

    def clear(self) -> None:
        """清空**对话**记忆（长期记忆不动）。"""
        self.messages = []
        self._rewrite_session([])

    def read_long_term(self) -> str:
        """读长期记忆的正文（去掉标题）。"""
        text = self.long_term_file.read_text(encoding="utf-8")
        return text.replace(LONG_TERM_HEADER, "").strip()

    def remember(self, fact: str) -> None:
        """追加一条长期记忆。"""
        fact = fact.strip()
        if fact:
            with self.long_term_file.open("a", encoding="utf-8") as handle:
                handle.write(f"- {fact}\n")

    def build_context(self, system_prompt: str) -> list[dict[str, Any]]:
        """组装发给模型的消息：system prompt（含长期记忆）+ 对话历史。"""
        long_term = self.read_long_term()
        system_content = system_prompt
        if long_term:
            system_content += f"\n\n## 长期记忆（用户之前让你记住的事）\n{long_term}"

        return [{"role": "system", "content": system_content}, *self.messages]

    def maybe_compress(self, total_tokens: int) -> bool:
        """上下文接近上限时，把早期消息压成摘要。返回是否真的压缩了。"""
        if total_tokens <= MAX_CONTEXT_TOKENS * COMPRESS_THRESHOLD:
            return False                       # 没到 90%，先不压
        if len(self.messages) <= KEEP_RECENT_MESSAGES:
            return False                       # 没什么可压的

        cut = len(self.messages) - KEEP_RECENT_MESSAGES

        # ⚠️ 边界修正：不能把 assistant(tool_calls) 和紧随的 tool 结果拆开
        # （Day 5 验证过：切开了就变成"孤立的 tool 消息"，API 会报错）
        while cut > 0 and self.messages[cut].get("role") == "tool":
            cut -= 1
        if cut <= 0:
            return False

        old_part = self.messages[:cut]
        kept = self.messages[cut:]

        summary = self._summarize(old_part)
        if not summary:
            return False                       # 摘要失败 → 这次不压（宁可不压，也不丢信息）

        old_chars = sum(len(str(item.get("content", ""))) for item in old_part)
        if len(summary) >= old_chars:
            print("[memory] 摘要没有比原文更短，跳过压缩")
            return False                       # 压缩必须有净收益

        before = len(self.messages)
        self.messages = [
            {"role": "user", "content": f"[对话历史摘要]\n{summary}"},
            *kept,
        ]
        self._rewrite_session(self.messages)
        print(f"[memory] 已压缩：{before} 条 → {len(self.messages)} 条")
        return True

    def _summarize(self, messages: list[dict[str, Any]]) -> str:
        """用模型把旧消息压成要点。失败返回空串（表示"这次不压"）。"""
        lines: list[str] = []
        for message in messages:
            role = message.get("role")
            content = str(message.get("content", "")).strip()
            if role == "tool":
                content = content.splitlines()[0] if content else ""     # 工具结果只留第一行
            if content:
                lines.append(f"[{role}] {content[:400]}")
        if not lines:
            return ""

        prompt = (
            "下面是一段较早的对话记录。请压缩成简短的中文要点，只保留：\n"
            "1) 用户的目标与偏好；2) 已经做过的关键操作；3) 得出的结论。\n"
            "不要编造记录里没出现过的事实。\n\n" + "\n".join(lines)
        )

        try:
            return call_llm_simple(prompt).strip()
        except Exception as exc:
            print(f"[memory] 摘要失败，跳过压缩：{type(exc).__name__}: {exc}")
            return ""
