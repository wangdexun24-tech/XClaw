"""Day 9 验收：长任务模式必须能"脱离真实模型"独立测出全部控制逻辑。

## 难点
长任务模式的核心是"循环 + 判定"，而循环依赖模型。怎么不调 API 也能测？
**把 call_llm 换掉。** 因为 ChatNode 里写的是 `call_llm(...)`，Python 在**调用时**
才去模块的全局命名空间找这个名字 —— 所以换掉模块属性就换掉了模型。
（这个技巧叫 monkeypatch；要理解的是它的**原理**，不是写法。）

## 测什么 / 不测什么
    测：循环、预算、分支、证据传递、日志 —— 这些是**你写的代码**
    不测：模型能不能真的修好 bug —— 那是模型的能力
**测试要测自己写的逻辑。**

七项检查：
  ① 任务文件加载：正常 / 缺 check / 缺 goal / budget 非法 → 都变成 GoalError
  ② frontmatter 列表语法（Day 9 新支持）
  ③ 判据执行：通过 / 失败 / 输出截断保留尾部 / 超时
  ④ 重试消息：必须带上命令原文、退出码、输出尾部、反作弊提示
  ⑤ 判据一直失败 → 用完预算就 give_up，**不会无限循环**
  ⑥ 判据通过 → 立刻 passed，**不再多调一次模型**
  ⑦ 每次尝试都重置内环预算（tool_round），否则内外环会空转

运行：python goal_check.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import examples.chatbot_with_tools.main as chat_module        # noqa: E402
from core.frontmatter import as_list, as_text, parse_frontmatter  # noqa: E402
from core.goal import Goal, GoalError, build_retry_message, load_goal, run_checks, suspicious_changes  # noqa: E402
from examples.goal_agent import main as goal_module           # noqa: E402

MAX_TOOL_ROUNDS = chat_module.MAX_TOOL_ROUNDS


def section(title: str) -> None:
    print(f"\n--- {title} ---")


# ============================================================ 假模型


class FakeLLM:
    """假模型：记录被调用了多少次，并按剧本返回 assistant 消息。

    mode="done"  → 每次都说"我完成了"（不带 tool_calls，一轮就结束）
    mode="tool"  → 每次都要求调一次 bash（用来把内环的 tool_round 撑满）
    """

    def __init__(self, mode: str = "done") -> None:
        self.mode = mode
        self.calls = 0
        self.seen_messages: list[list[dict]] = []

    def __call__(self, messages=None, tools=None, system_prompt=None):
        self.calls += 1
        self.seen_messages.append(list(messages or []))

        if self.mode == "tool":
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call_{self.calls}",
                        "type": "function",
                        "function": {"name": "bash", "arguments": '{"command": "echo hi"}'},
                    }
                ],
            }
        return {"role": "assistant", "content": "我完成了"}


def use_fake(fake: FakeLLM) -> None:
    """把 Day 5 那个模块里的 call_llm 换成假模型。

    要换的是 **ChatNode 所在模块** 的属性 ——
    ChatNode.exec 里的 `call_llm` 是在那个模块的命名空间里查找的。
    """
    chat_module.call_llm = fake


# ============================================================ 测试用任务文件


def write_goal(directory: Path, *, check: str, budget: int = 2, goal: str = "让判据通过") -> Path:
    """在 <directory>/goals/task.md 写一个任务文件（这样默认 workdir 就是 directory）。"""
    goals_dir = directory / "goals"
    goals_dir.mkdir(parents=True, exist_ok=True)
    path = goals_dir / "task.md"
    path.write_text(
        f"---\ngoal: {goal}\ncheck:\n  - {check}\nbudget: {budget}\n---\n\n备注正文。\n",
        encoding="utf-8",
    )
    return path


ALWAYS_FAIL = 'python -c "import sys; sys.exit(1)"'
ALWAYS_PASS = 'python -c "import sys; sys.exit(0)"'
NOISY_FAIL = 'python -c "import sys; [print(chr(120)*50) for _ in range(200)]; sys.exit(1)"'


# ============================================================ ① 加载


def check_loading() -> None:
    section("① 任务文件加载与校验")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        good = write_goal(root, check="pytest -q", budget=5)
        goal = load_goal(good)
        assert goal.text == "让判据通过"
        assert goal.checks == ["pytest -q"]
        assert goal.budget == 5
        # 注意用 resolve() 比较：macOS 的 /var 是 /private/var 的符号链接，
        # 而 load_goal 会把路径 resolve 掉 —— 这是"临时目录测试"的常见坑
        assert goal.workdir == root.resolve(), goal.workdir
        print(f"  ✓ 正常加载：budget={goal.budget}，workdir 默认取到 goals/ 的父目录")

        # 缺 check：必须直接拒绝，而不是放行一个"没有判据的长任务"
        (root / "goals" / "nocheck.md").write_text(
            "---\ngoal: 随便改改\n---\n正文\n", encoding="utf-8"
        )
        try:
            load_goal(root / "goals" / "nocheck.md")
            raise AssertionError("缺 check 竟然没有被拒绝")
        except GoalError as exc:
            assert "check" in str(exc)
            print("  ✓ 缺 check → GoalError（没有判据就不该跑长任务）")

        # 缺 goal
        (root / "goals" / "nogoal.md").write_text(
            "---\ncheck:\n  - true\n---\n", encoding="utf-8"
        )
        try:
            load_goal(root / "goals" / "nogoal.md")
            raise AssertionError("缺 goal 竟然没有被拒绝")
        except GoalError as exc:
            assert "goal" in str(exc)
            print("  ✓ 缺 goal → GoalError")

        # budget 不是整数 / 不是正数
        for bad in ["abc", "0", "-3"]:
            (root / "goals" / "badbudget.md").write_text(
                f"---\ngoal: x\ncheck:\n  - true\nbudget: {bad}\n---\n", encoding="utf-8"
            )
            try:
                load_goal(root / "goals" / "badbudget.md")
                raise AssertionError(f"budget={bad} 竟然通过了")
            except GoalError:
                pass
        print("  ✓ budget 非法（abc / 0 / -3）→ GoalError")

        # 文件不存在
        try:
            load_goal(root / "goals" / "nope.md")
            raise AssertionError("不存在的文件竟然加载成功了")
        except GoalError:
            print("  ✓ 文件不存在 → GoalError")

        # 真实项目里的任务文件也要能加载
        demo = load_goal(PROJECT_ROOT / "goals" / "demo_wc_tool.md")
        assert len(demo.checks) == 2 and demo.budget == 8
        assert demo.workdir == PROJECT_ROOT
        print(f"  ✓ goals/demo_wc_tool.md：{len(demo.checks)} 条判据，budget={demo.budget}")


# ============================================================ ② frontmatter


def check_frontmatter() -> None:
    section("② frontmatter 列表语法（Day 9 新支持）")
    text = (
        "---\n"
        "goal: 一个目标\n"
        "check:\n"
        "  - pytest -q\n"
        "  - python check.py\n"
        "budget: 3\n"
        "---\n"
        "正文\n"
    )
    data, body = parse_frontmatter(text)
    assert as_list(data["check"]) == ["pytest -q", "python check.py"], data
    assert as_text(data["goal"]) == "一个目标"
    assert as_text(data["budget"]) == "3"
    assert body == "正文"
    print("  ✓ 多行列表被正确解析")

    data, _ = parse_frontmatter("---\ncheck: pytest -q\n---\n")
    assert as_list(data["check"]) == ["pytest -q"]
    print("  ✓ 单行 check 也接受（as_list 兼容字符串）")

    # 标量字段拿到列表时不能崩 —— Day 8 那种直接 .strip() 的写法会在这里炸
    data, _ = parse_frontmatter("---\nname:\n  - a\n  - b\n---\n")
    assert as_text(data["name"]) == ""
    assert as_list(data["name"]) == ["a", "b"]
    print("  ✓ as_text / as_list 分工明确，list 值不会让标量字段崩掉")


# ============================================================ ③ 判据执行


def check_run_checks() -> None:
    section("③ 判据执行与输出截断")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        goal = Goal(text="t", checks=[ALWAYS_PASS, ALWAYS_FAIL], budget=1, workdir=root)
        results = run_checks(goal)
        assert len(results) == 2
        assert results[0].ok and results[0].exit_code == 0
        assert not results[1].ok and results[1].exit_code == 1
        print("  ✓ 通过/失败都由 exit_code 判定；全部跑完，不提前退出")

        noisy = Goal(text="t", checks=[NOISY_FAIL], budget=1, workdir=root)
        output = run_checks(noisy)[0].output
        assert len(output.splitlines()) <= 32, len(output.splitlines())
        assert "只保留最后" in output
        print(f"  ✓ 200 行输出被截断到 {len(output.splitlines())} 行，且保留了尾部")

        slow = Goal(
            text="t",
            checks=['python -c "import time; time.sleep(5)"'],
            budget=1,
            workdir=root,
        )
        timed_out = run_checks(slow, timeout=1)[0]
        assert not timed_out.ok and "超时" in timed_out.output
        print("  ✓ 超时判定为失败（不会把整个长任务卡死）")


# ============================================================ ④ 重试消息


def check_retry_message() -> None:
    section("④ 重试消息必须带证据")
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        goal = Goal(text="把 wc 工具加上", checks=[ALWAYS_FAIL], budget=4, workdir=root)
        results = run_checks(goal)

        message = build_retry_message(goal, results, attempt=2, suspicious=["tools_check.py"])
        must_have = [
            "第 2/4 次尝试",                  # 还剩多少机会
            "把 wc 工具加上",                  # 目标回顾（防止压缩后丢失）
            ALWAYS_FAIL,                      # 命令原文：模型要靠它复现
            "退出码：1",                       # 比"失败了"精确
            "禁止为了让判据通过而删改测试",      # 反作弊提示
            "tools_check.py",                 # 可疑改动清单
        ]
        for item in must_have:
            assert item in message, f"重试消息里缺少：{item}"
        print("  ✓ 六项要素齐全：次数 / 目标 / 命令原文 / 退出码 / 反作弊 / 可疑改动")

        hits = suspicious_changes(
            ["README.md", "tools_check.py", "test_x.py", "a/tests/b.py", "core/node.py"]
        )
        assert hits == ["tools_check.py", "test_x.py", "a/tests/b.py"], hits
        assert suspicious_changes(["README.md", "core/goal.py"]) == []
        print("  ✓ 只挑出像测试/检查的文件，普通代码文件不误报")


# ============================================================ ⑤⑥⑦ 端到端


def run_fake_goal(*, check: str, budget: int, mode: str = "done"):
    """在临时目录里跑一遍长任务，返回 (outcome, fake, 日志行, memory 消息)。"""
    fake = FakeLLM(mode=mode)
    original = chat_module.call_llm
    use_fake(fake)
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            goal_path = write_goal(root, check=check, budget=budget)
            outcome = goal_module.run_goal(
                goal_path,
                memory_dir=root / "memory",
                log_dir=root / "logs",
            )
            log_files = sorted((root / "logs").glob("*.jsonl"))
            lines = log_files[0].read_text(encoding="utf-8").splitlines() if log_files else []
            messages = list(goal_module.shared["memory"].messages)
        return outcome, fake, lines, messages
    finally:
        chat_module.call_llm = original


def check_give_up() -> None:
    section("⑤ 判据一直失败 → 用完预算就放弃（不会无限循环）")
    outcome, fake, log_lines, messages = run_fake_goal(check=ALWAYS_FAIL, budget=3)

    assert outcome == "give_up", outcome
    assert fake.calls == 3, f"应该刚好调用模型 3 次，实际 {fake.calls}"
    assert len(log_lines) == 3, len(log_lines)
    print(f"  ✓ outcome=give_up，模型被调用 {fake.calls} 次（= budget），日志 {len(log_lines)} 行")

    retries = [
        m for m in messages
        if m.get("role") == "user" and "[目标未达成" in str(m.get("content", ""))
    ]
    assert len(retries) == 2, f"3 次尝试应该有 2 条重试消息，实际 {len(retries)}"
    assert ALWAYS_FAIL in str(retries[-1]["content"])
    print("  ✓ 3 次尝试 → 2 条重试消息，且都带着失败证据")

    record = json.loads(log_lines[-1])
    assert record["attempt"] == 3 and record["passed"] is False
    assert record["checks"][0]["exit_code"] == 1
    print("  ✓ 日志是 jsonl：每行一条尝试记录，含 exit_code")


def check_passed() -> None:
    section("⑥ 判据通过 → 立刻结束，不再多调模型")
    outcome, fake, log_lines, _ = run_fake_goal(check=ALWAYS_PASS, budget=5)
    assert outcome == "passed", outcome
    assert fake.calls == 1, f"通过之后不该再调用模型，实际 {fake.calls} 次"
    assert len(log_lines) == 1
    print(f"  ✓ outcome=passed，模型只被调用了 {fake.calls} 次，日志 {len(log_lines)} 行")


def check_inner_budget_reset() -> None:
    section("⑦ 每次重试都给内环重新发牌（tool_round 必须清零）")
    budget = 2
    outcome, fake, _log_lines, _messages = run_fake_goal(
        check=ALWAYS_FAIL, budget=budget, mode="tool"
    )

    # 假模型每次都要求调工具 → 内环必然跑满：每轮尝试 = MAX_TOOL_ROUNDS + 1 次调用
    expected = budget * (MAX_TOOL_ROUNDS + 1)
    assert outcome == "give_up", outcome
    assert fake.calls == expected, (
        f"期望 {expected} 次模型调用（= 每轮 {MAX_TOOL_ROUNDS + 1} 次 × {budget} 轮），"
        f"实际 {fake.calls} 次 —— 说明 tool_round 没有在重试时清零，内外环在空转"
    )
    print(f"  ✓ {budget} 轮 × {MAX_TOOL_ROUNDS + 1} 次 = {fake.calls} 次，tool_round 确实被重置")


def main() -> None:
    check_loading()
    check_frontmatter()
    check_run_checks()
    check_retry_message()
    check_give_up()
    check_passed()
    check_inner_budget_reset()

    print("\n✅ Day 9 验收全部通过")
    print("\n思考题：")
    print("  1. 如果判据写成 true（永远返回 0），这套系统会变成什么？怎么防住「判据写错」？")
    print(f"  2. 内环上限 {MAX_TOOL_ROUNDS} × 外环预算 8，最坏会发多少次模型请求？")
    print("  3. 为什么「让模型自己判断任务是否完成」是循环论证？")


if __name__ == "__main__":
    main()
