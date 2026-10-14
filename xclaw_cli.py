"""xclaw 命令行入口。

## 为什么要有它
在它之前，"把项目跑起来"意味着 `python -m examples.chatbot_with_tools.main` ——
那是**开发者的用法**。装成命令之后：

    pip install -e .
    cd 你的项目
    xclaw

这是"仓库"和"工具"的分界线：前者要你进到它里面，后者是它进到你里面。

## 子命令
    xclaw                    进入交互式 agent（默认）
    xclaw chat               同上，显式写法
    xclaw goal <任务文件>     跑一个长任务（目标 + 判据 + 预算）
    xclaw check [名字]        跑离线验收脚本（不花 API 额度）
    xclaw tools              列出工具及其确认策略

## 为什么 check 用子进程跑
8 个验收脚本会改模块级全局状态（阈值、假模型、工作区），
在同一个进程里连着跑会互相污染。**每个脚本一个干净进程**是最省心的隔离方式，
代价只是多几次解释器启动。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# 验收脚本的名字 → 文件（顺序按依赖从底到上，方便快速定位第一个失败点）
CHECK_SCRIPTS = {
    "graph": "day1_check.py",
    "tools": "tools_check.py",
    "memory": "memory_check.py",
    "mcp": "mcp_check.py",
    "skills": "skill_check.py",
    "goal": "goal_check.py",
    "approval": "approval_check.py",
    "hardening": "hardening_check.py",
}


def cmd_chat(args: argparse.Namespace) -> int:
    """交互式 agent。工作区和会话数据都跟着当前目录走。"""
    from examples.chatbot_with_tools.main import run_chat

    workspace = Path.cwd().resolve()
    run_chat(memory_dir=workspace / ".xclaw")
    return 0


def cmd_goal(args: argparse.Namespace) -> int:
    from core.goal import GoalError
    from examples.goal_agent.main import run_goal

    try:
        outcome = run_goal(args.goal_file)
    except GoalError as exc:
        print(f"[goal] 任务文件有问题：\n{exc}")
        return 1
    return 0 if outcome == "passed" else 1


def cmd_check(args: argparse.Namespace) -> int:
    names = list(CHECK_SCRIPTS) if args.name in (None, "all") else [args.name]
    failed: list[str] = []

    for name in names:
        script = REPO_ROOT / CHECK_SCRIPTS[name]
        print(f"\n{'=' * 64}\n▶ {name}：{script.name}\n{'=' * 64}", flush=True)
        # 每个脚本单独起进程：它们的全局状态互不隔离，同一个进程里连着跑会互相污染
        proc = subprocess.run([sys.executable, str(script)], cwd=str(REPO_ROOT))
        if proc.returncode != 0:
            failed.append(name)

    print(f"\n{'=' * 64}")
    if failed:
        print(f"❌ 失败的验收项：{', '.join(failed)}")
        return 1
    print(f"✅ 全部 {len(names)} 项验收通过")
    return 0


def cmd_tools(_args: argparse.Namespace) -> int:
    from tools.builtins import get_builtin_tools

    print(f"{'工具':<10}{'确认策略':<12}说明")
    print("-" * 72)
    for tool in get_builtin_tools():
        policy = "需要确认" if tool.requires_approval else "免确认（只读）"
        summary = tool.description.splitlines()[0][:44]
        print(f"{tool.name:<10}{policy:<12}{summary}")
    print("\n提示：工作区之外的路径会被拒绝；需要放宽时设置 XCLAW_ALLOW_OUTSIDE=1。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xclaw",
        description="从零手写的编程智能体（coding agent）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  xclaw                         在当前目录下开始对话\n"
            "  xclaw goal goals/demo_wc_tool.md\n"
            "  xclaw check approval          只跑操作确认那一项验收\n"
            "  xclaw check all               跑全部八项（不花 API 额度）\n"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("chat", help="交互式 agent（默认命令）")

    goal = sub.add_parser("goal", help="跑一个长任务（目标 + 可判定判据 + 预算）")
    goal.add_argument("goal_file", help="任务文件路径，例如 goals/demo_wc_tool.md")

    check = sub.add_parser("check", help="跑离线验收脚本（不花 API 额度）")
    check.add_argument(
        "name",
        nargs="?",
        default="all",
        choices=[*CHECK_SCRIPTS, "all"],
        help="要跑哪一项，默认全部",
    )

    sub.add_parser("tools", help="列出工具及其确认策略")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # 不带子命令时默认进交互式 agent —— 最常见的用法应该是零参数的
    command = args.command or "chat"
    handlers = {
        "chat": cmd_chat,
        "goal": cmd_goal,
        "check": cmd_check,
        "tools": cmd_tools,
    }
    return handlers[command](args)


if __name__ == "__main__":
    raise SystemExit(main())
