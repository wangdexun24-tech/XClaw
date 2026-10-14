"""Day 6 验收：记忆模块的离线检查（不消耗 API 额度）。

用临时目录 + 假摘要函数，验证四件最容易写错的事：
  ① 字段过滤：usage 不能进历史
  ② 崩溃恢复：没走完的工具轮要被丢掉
  ③ 压缩边界：不能把 assistant(tool_calls) 和 tool 结果拆开，且必须变短
  ④ 长期记忆：写入 MEMORY.md 并拼进 system prompt
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import core.memory as memory_module
from core.memory import Memory

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="xclaw-memory-"))


def check_field_filtering() -> None:
    """① usage 这类元数据不能进历史，也不能落盘。"""
    print("\n--- ① 字段过滤 ---")
    mem = Memory(_temp_dir())
    saved = mem.append({
        "role": "assistant",
        "content": "你好",
        "usage": {"total_tokens": 123},          # 元数据，应该被过滤掉
    })
    check("usage" not in saved, "① append 没有过滤掉 usage")
    first_line = json.loads(mem.session_file.read_text(encoding="utf-8").splitlines()[0])
    check("usage" not in first_line, "① 落盘的消息里还带着 usage")
    print("  ✓ usage 在内存对象和磁盘文件里都被过滤掉了")


def check_crash_recovery() -> None:
    """② 读回时，没走完的工具轮必须整轮丢掉。"""
    print("\n--- ② 崩溃恢复 ---")
    directory = _temp_dir()
    Memory(directory).clear()                     # 先把目录和文件建出来
    (directory / "session.jsonl").write_text(
        "\n".join([
            json.dumps({"role": "user", "content": "看看 README"}, ensure_ascii=False),
            json.dumps({"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "read", "arguments": "{}"}}]}, ensure_ascii=False),
        ]) + "\n",
        encoding="utf-8",
    )
    reloaded = Memory(directory)
    check(reloaded.messages == [], f"② 未完成的一轮没有被清掉：{reloaded.messages}")
    print("  ✓ 孤立的 tool_call 被清掉了（否则下次请求会被 API 拒绝）")


def check_compression_boundary() -> None:
    """③ 压缩不能把 assistant(tool_calls) 和 tool 结果拆开，且必须真的变短。"""
    print("\n--- ③ 压缩边界 ---")
    mem = Memory(_temp_dir())
    mem.append({"role": "user", "content": "任务：读若干文件"})
    for index in range(6):
        mem.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{index}", "type": "function",
             "function": {"name": "read",
                          "arguments": json.dumps({"path": f"f{index}.py"})}}]})
        mem.append({"role": "tool", "tool_call_id": f"c{index}",
                    "content": "工具 read 执行结果：\n" + "文件内容行\n" * 40})
    mem.append({"role": "assistant", "content": "读完了，总结如下……" + "内容" * 200})

    original_max_tokens = memory_module.MAX_CONTEXT_TOKENS
    original_summarize = memory_module.call_llm_simple
    memory_module.MAX_CONTEXT_TOKENS = 10         # 把阈值调小，强制触发压缩
    memory_module.call_llm_simple = lambda prompt: "用户想读若干文件，模型逐个读取后做了总结。"

    try:
        before = len(mem.messages)
        changed = mem.maybe_compress(total_tokens=99999)
        after = mem.messages
    finally:
        # 还原全局状态：测试不能污染后面的用例
        memory_module.MAX_CONTEXT_TOKENS = original_max_tokens
        memory_module.call_llm_simple = original_summarize

    check(changed, "③ 应该触发压缩但没有")
    check(len(after) < before, f"③ 压缩后条数没有减少：{before} → {len(after)}")
    check(after[0].get("role") == "user" and "[对话历史摘要]" in str(after[0].get("content", "")),
          f"③ 摘要没有放在历史开头：{after[0]}")
    check(after[1].get("role") != "tool",
          f"③ 压缩边界把 tool 消息切到开头了（配对被拆散）：{[m.get('role') for m in after]}")
    print(f"  ✓ 压缩 {before} 条 → {len(after)} 条，且切点没有拆散 tool 配对")


def check_long_term_memory() -> None:
    """④ 长期记忆写入 MEMORY.md，并拼进 system prompt。"""
    print("\n--- ④ 长期记忆 ---")
    mem = Memory(_temp_dir())
    mem.append({"role": "user", "content": "我开始干活了"})
    mem.remember("我的项目 XClaw 用 uv 管理依赖")
    check("uv" in mem.read_long_term(), "④ 长期记忆没写进 MEMORY.md")
    context = mem.build_context("你是助手")
    check(context[0]["role"] == "system" and "uv" in context[0]["content"],
          "④ 长期记忆没有拼进 system prompt")
    check(context[1:] == mem.messages and len(context) == len(mem.messages) + 1,
          "④ build_context 没有把历史原样接在 system 之后")
    print("  ✓ 长期记忆已落盘，并拼进了 system prompt")


def main() -> None:
    check_field_filtering()
    check_crash_recovery()
    check_compression_boundary()
    check_long_term_memory()

    print("\n检查项：①字段过滤  ②崩溃恢复  ③压缩边界  ④长期记忆")
    if failures:
        print("❌ 失败：")
        for item in failures:
            print("  -", item)
        raise SystemExit(1)

    print("✅ 四项全部通过")


if __name__ == "__main__":
    main()
