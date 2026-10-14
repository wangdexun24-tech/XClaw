"""Day 9 示例：长任务模式 —— 给一个目标，让它自己跑到"程序验证通过"。

## 图长这样（在 Day 5 的环外面再套一层环）

                    ┌──────────────────────────────────────┐
                    │                                      │
                    ▼                                      │
       ChatNode ⇄ ToolCallNode      ← 内环：怎么做（Day 5 的代码，**一行没改**）
            │
            └─"done"─▶ VerifyNode ─"retry"─▶ ChatNode      ← 外环：做完了没有
                           │
                           ├─"passed" ─┐
                           └─"give_up"─┴─▶ ReportNode ─▶ 结束

## 两个环各管一件事
    内环（ChatNode ⇄ ToolCallNode）= **怎么做**：模型和工具配合解决一个子问题
    外环（VerifyNode → ChatNode）  = **做完了没有**：程序跑判据，不通过就把证据扔回去

## 一个关键的设计发现
ChatNode 一个字都没改。同一个 ChatNode，既能跑"一问一答"，也能跑"长任务" ——
差别**只在于怎么连线**：`chat - "done" >> verify` 这一条线就是模式的开关。
**模式切换 = 换连线，不是换节点。** 这是 Day 1 "把控制流变成数据"结出的果实。

运行：
    python -m examples.goal_agent.main goals/demo_wc_tool.md
"""

from __future__ import annotations

import sys
import os
import time
from pathlib import Path
from typing import Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from core.approval import ApprovalNode, AutoApprover           # noqa: E402
from core.goal import (                                        # noqa: E402
    GoalError,
    build_retry_message,
    git_changed_files,
    load_goal,
    log_attempt,
    run_checks,
    suspicious_changes,
)
from core.memory import Memory                                 # noqa: E402
from core.node import Flow, Node, shared                       # noqa: E402
from examples.chatbot_with_tools.main import ChatNode, ToolCallNode  # noqa: E402
from tools import ToolExecutor                                 # noqa: E402

CHECK_PREVIEW = 400        # 打印判据输出时的截断长度


def build_goal_message(goal) -> str:
    """把目标写成一条 user 消息。

    为什么把目标放 user 消息而不是 system prompt？
    1. 目标本来就是"用户的指令"，语义上就是 user；
    2. 这样 ChatNode **一行都不用改** —— 我们能复用 Day 5 的节点原封不动。
    """
    checks = "\n".join(f"{index}. {item}" for index, item in enumerate(goal.checks, 1))
    return (
        "[长任务模式]\n"
        f"目标：{goal.text}\n\n"
        f"完成判据（由程序执行，你无法修改）：\n{checks}\n\n"
        "规则：\n"
        "1. 每当你不再调用工具、给出文字回答时，程序会立刻执行上面的判据。\n"
        "2. 判据全部通过（退出码 0）才算完成；否则你会收到失败输出，需要继续修，"
        f"直到全部通过或 {goal.budget} 次尝试用尽。\n"
        "3. 所以：不要用文字宣称「我完成了」，去让它**真的**通过。\n"
        "4. 禁止为了让判据通过而修改判据本身、或删改测试文件。\n\n"
        "现在开始。先看清现状再动手。"
    )


class VerifyNode(Node):
    """外环的核心：跑判据，决定"通过 / 再来一轮 / 放弃"。"""

    def exec(self, payload: Any) -> Tuple[str, Any]:
        goal = shared["goal"]
        memory: Memory = shared["memory"]

        attempt = shared.get("attempt", 0) + 1
        shared["attempt"] = attempt

        print(f"\n{'=' * 60}\n🔍 验证第 {attempt}/{goal.budget} 次尝试")
        results = run_checks(goal, cwd=goal.workdir)
        passed = all(result.ok for result in results)

        for result in results:
            mark = "✓" if result.ok else "✗"
            preview = (result.output or "(无输出)")[:CHECK_PREVIEW].replace("\n", " ")
            print(f"  [{mark}] {result.command}")
            print(f"      exit={result.exit_code}  {preview}")
        print(f"{'=' * 60}")

        # 每次尝试都落一行日志：失败时才有据可查，也顺便攒出简历要的数字
        log_attempt(shared["attempt_log"], attempt, results)

        if passed:
            shared["outcome"] = "passed"
            return "passed", {"outcome": "passed", "attempt": attempt}

        if attempt >= goal.budget:
            print(f"\n❌ 已用完 {goal.budget} 次尝试，仍然没有通过。")
            shared["outcome"] = "give_up"
            return "give_up", {"outcome": "give_up", "attempt": attempt}

        # 反作弊检查：模型有没有为了变绿去改测试？
        suspicious = suspicious_changes(git_changed_files(goal.workdir))
        if suspicious:
            print(f"  ⚠️ 可疑改动（像测试/检查的文件）：{', '.join(suspicious)}")

        # ★ 最关键的一步：把失败证据写回历史，让下一轮有的放矢
        memory.append(
            {
                "role": "user",
                "content": build_retry_message(goal, results, attempt, suspicious),
            }
        )

        # ★ 别忘了给内环重新发牌：tool_round 不清零的话，ChatNode 会认为
        #   自己已经用满了 MAX_TOOL_ROUNDS，一上来就返回 "done" ——
        #   于是 chat 和 verify 之间空转，一轮工具都跑不了。
        shared["tool_round"] = 0
        return "retry", None


class ReportNode(Node):
    """打印最终结论。故意不注册任何后继 —— 流程到此结束。"""

    def exec(self, payload: Any) -> Tuple[str, Any]:
        goal = shared["goal"]
        outcome = payload.get("outcome")
        attempt = payload.get("attempt")

        if outcome == "passed":
            print(f"\n✅ 目标达成（第 {attempt} 次尝试）")
        else:
            print(f"\n❌ 放弃：{goal.budget} 次尝试都没让判据全部通过")
            print("   最后一次的失败输出见上方；完整记录见尝试日志。")

        print(f"[goal] 尝试日志：{shared['attempt_log']}")
        return "end", payload


def build_flow() -> Flow:
    """连图（只做一次）。注意内环的两条边和 Day 5 完全一样。"""
    chat, approval, tool_call = ChatNode(), ApprovalNode(), ToolCallNode()
    verify, report = VerifyNode(), ReportNode()

    chat - "tool_call" >> approval
    approval - "proceed" >> tool_call
    tool_call - "chat" >> chat        # ← 内环闭合（Day 5 原样）
    chat - "done" >> verify           # ← 新增：一轮结束 → 去验证
    verify - "retry" >> chat          # ← 新增：没通过 → 再来一轮（外环闭合）
    verify - "passed" >> report
    verify - "give_up" >> report
    # report 没有后继 → Flow 自然结束，而且不会打 "没有后继" 的警告

    return Flow(chat)


def run_goal(
    goal_path: Path | str,
    *,
    memory_dir: Path | str | None = None,
    log_dir: Path | str | None = None,
) -> str:
    """跑一个长任务，返回 'passed' 或 'give_up'。

    memory_dir / log_dir 做成参数，是为了让 goal_check.py 能把状态隔离到临时目录 ——
    **可测试性是被设计出来的，不是事后补的。**
    """
    goal = load_goal(goal_path)

    print("=" * 60)
    print("🎯 XClaw 长任务模式")
    print("=" * 60)
    print(f"目标：{goal.text}")
    print(f"判据（{len(goal.checks)} 条，退出码 0 表示通过）：")
    for index, item in enumerate(goal.checks, 1):
        print(f"  {index}. {item}")
    print(f"预算：最多 {goal.budget} 次尝试    工作目录：{goal.workdir}")

    shared.clear()
    executor = ToolExecutor()
    shared["tool_executor"] = executor
    shared["tools"] = executor.get_llm_tools()
    shared["memory"] = Memory(Path(memory_dir or PROJECT_ROOT / "goal_memory"))

    # 长任务是无人值守的：没人能回答终端里的 [y/N]。
    # 如果这里用 ConsoleApprover，程序会**卡在 input() 上**，看起来像死循环。
    # 所以这里显式声明信任策略为"自动放行"。
    # —— 反过来说，这也说明长任务模式的判据必须足以兜住"模型乱改文件"的风险。
    shared["approver"] = AutoApprover()

    shared["goal"] = goal
    shared["attempt"] = 0
    shared["tool_round"] = 0
    shared["attempt_log"] = _new_log_path(log_dir, goal)

    # 目标作为一条 user 消息进入历史（见 build_goal_message 的说明）
    shared["memory"].append({"role": "user", "content": build_goal_message(goal)})

    # 让**工具**和**判据**在同一个目录里干活。
    # 为什么要动 cwd：8 个内置工具都是用相对路径 + Path.resolve() 决定位置的，
    # 也就是跟着进程的当前目录走；而判据是按 goal.workdir 跑的。
    # 两者不一致的话，会遇到"判据在 A 目录找文件、模型在 B 目录写文件"这种鬼故事。
    # 代价说清楚：chdir 是**进程级全局状态**，作为库被别的程序调用时不够礼貌；
    # 更干净的做法是给每个工具传入 cwd —— 那是后面可以做的重构。
    original_cwd = Path.cwd()
    os.chdir(goal.workdir)
    try:
        build_flow().run(None)
    except KeyboardInterrupt:
        print("\n[goal] 被中断。已完成的部分记录在尝试日志里：")
        print(f"       {shared['attempt_log']}")
        return "interrupted"
    finally:
        os.chdir(original_cwd)          # 一定要还回去，否则会污染调用方

    return shared.get("outcome", "unknown")


def _new_log_path(log_dir: Path | str | None, goal) -> Path:
    directory = Path(log_dir or PROJECT_ROOT / "goal_runs")
    directory.mkdir(parents=True, exist_ok=True)
    stem = goal.source.stem if goal.source else "goal"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return directory / f"{stem}-{stamp}.jsonl"


def main() -> int:
    if len(sys.argv) < 2:
        goal_files = sorted((PROJECT_ROOT / "goals").glob("*.md"))
        print("用法：python -m examples.goal_agent.main <任务文件>")
        print("可用的任务文件：")
        for item in goal_files:
            print(f"  {item.relative_to(PROJECT_ROOT)}")
        return 1

    try:
        outcome = run_goal(sys.argv[1])
    except GoalError as exc:
        print(f"[goal] 任务文件有问题：\n{exc}")
        return 1

    return 0 if outcome == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
