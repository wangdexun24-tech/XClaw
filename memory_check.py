"""Day 6 验收：记忆模块的离线检查（不消耗 API 额度）。

用临时目录 + 假摘要函数，验证四件最容易写错的事：
  ① 字段过滤：usage 不能进历史
  ② 崩溃恢复：没走完的工具轮要被丢掉
  ③ 压缩边界：不能把 assistant(tool_calls) 和 tool 结果拆开，且必须变短
  ④ 长期记忆：写入 MEMORY.md 并拼进 system prompt
"""

import json
import tempfile
from pathlib import Path

import core.memory as memory_module
from core.memory import Memory

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


# ---------- ① 字段过滤：usage 不能进历史 ----------
tmp = Path(tempfile.mkdtemp(prefix="xclaw-memory-"))
mem = Memory(tmp)
saved = mem.append({
    "role": "assistant",
    "content": "你好",
    "usage": {"total_tokens": 123},          # 元数据，应该被过滤掉
})
check("usage" not in saved, "① append 没有过滤掉 usage")
first_line = json.loads(mem.session_file.read_text(encoding="utf-8").splitlines()[0])
check("usage" not in first_line, "① 落盘的消息里还带着 usage")

# ---------- ② 崩溃恢复：未完成的工具轮要被丢掉 ----------
tmp2 = Path(tempfile.mkdtemp(prefix="xclaw-memory-"))
Memory(tmp2).clear()                          # 先把目录和文件建出来
(tmp2 / "session.jsonl").write_text(
    "\n".join([
        json.dumps({"role": "user", "content": "看看 README"}, ensure_ascii=False),
        json.dumps({"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "read", "arguments": "{}"}}]}, ensure_ascii=False),
    ]) + "\n",
    encoding="utf-8",
)
reloaded = Memory(tmp2)
check(reloaded.messages == [], f"② 未完成的一轮没有被清掉：{reloaded.messages}")

# ---------- ③ 压缩：不拆散 tool 配对，且必须变短 ----------
tmp3 = Path(tempfile.mkdtemp(prefix="xclaw-memory-"))
mem3 = Memory(tmp3)
mem3.append({"role": "user", "content": "任务：读若干文件"})
for index in range(6):
    mem3.append({"role": "assistant", "content": "", "tool_calls": [
        {"id": f"c{index}", "type": "function",
         "function": {"name": "read",
                      "arguments": json.dumps({"path": f"f{index}.py"})}}]})
    mem3.append({"role": "tool", "tool_call_id": f"c{index}",
                 "content": "工具 read 执行结果：\n" + "文件内容行\n" * 40})
mem3.append({"role": "assistant", "content": "读完了，总结如下……" + "内容" * 200})

memory_module.MAX_CONTEXT_TOKENS = 10         # 把阈值调小，强制触发压缩
memory_module.call_llm_simple = lambda prompt: "用户想读若干文件，模型逐个读取后做了总结。"

before = len(mem3.messages)
changed = mem3.maybe_compress(total_tokens=99999)
after = mem3.messages

check(changed, "③ 应该触发压缩但没有")
check(len(after) < before, f"③ 压缩后条数没有减少：{before} → {len(after)}")
check(after[0].get("role") == "user" and "[对话历史摘要]" in str(after[0].get("content", "")),
      f"③ 摘要没有放在历史开头：{after[0]}")
check(after[1].get("role") != "tool",
      f"③ 压缩边界把 tool 消息切到开头了（配对被拆散）：{[m.get('role') for m in after]}")

# ---------- ④ 长期记忆 ----------
mem3.remember("我的项目 XClaw 用 uv 管理依赖")
check("uv" in mem3.read_long_term(), "④ 长期记忆没写进 MEMORY.md")
context = mem3.build_context("你是助手")
check(context[0]["role"] == "system" and "uv" in context[0]["content"],
      "④ 长期记忆没有拼进 system prompt")
check(context[1] is mem3.messages[0], "④ build_context 没有把历史接在 system 之后")

print("检查项：①字段过滤  ②崩溃恢复  ③压缩边界  ④长期记忆")
if failures:
    print("❌ 失败：")
    for item in failures:
        print("  -", item)
    raise SystemExit(1)

print("✅ 四项全部通过")
