"""Day 9 · 长任务模式的"目标和判据"这一层。

## 要解决什么问题
Day 5 的 agent 里，"活干完了"是**模型自己宣布的**（ChatNode 返回 "done"）。
它宣布得对不对，程序完全不知道 —— 模型经常说"我修好了"，而测试还是红的。
更根本地说，"模型觉得做完了"拿模型的判断去验证模型的行为，是**循环论证**。

## 做法：把"结束"的条件从「模型说完了」改成「程序验证通过」
    执行一轮 → 跑判据 → 没过就带着失败证据再来一轮 → 直到通过或预算耗尽

## 自主性三要素（缺一个就失控）
    循环   少了它：停在第一次失败，需要人盯着
    判据   少了它：无限打转，永远不知道自己好了没有
    预算   少了它：烧光 API 额度

## 这个文件管什么 / 不管什么
    管：  目标（Goal）、判据怎么跑（run_checks）、失败怎么转述成人话（build_retry_message）
    不管：图怎么连、什么时候重试 —— 那是 examples/goal_agent/main.py 的事

## 最重要的一条设计原则
判据必须由**外部**给出（任务文件里写死），**不能让模型自己定**。
让模型自己定完成判据，等于让运动员自己当裁判 ——
它会定一个自己稳过的判据（比如"文件被创建了"，而不是"内容正确"）。
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from core.frontmatter import as_list, as_text, parse_frontmatter

DEFAULT_BUDGET = 8                # 默认最多尝试几轮（每一轮 = 一次判据验证）
CHECK_TIMEOUT = 300               # 单条判据的超时秒数：判据挂住 = 整个长任务死掉
MAX_OUTPUT_LINES = 30             # 判据输出只留**最后** N 行
MAX_OUTPUT_BYTES = 8 * 1024

TEST_LIKE_NAMES = ("conftest.py", "test.py", "tests", "test")


class GoalError(ValueError):
    """任务文件写错了。刻意用一个专门的异常类型，方便调用方区分"配置错"和"运行错"。"""


@dataclass
class Goal:
    """一个长任务：目标 + 判据 + 预算。"""

    text: str                                   # 目标原话，要**原样**给模型看（转述会丢约束）
    checks: list[str]                           # 判据：每条是一个 shell 命令，退出码 0 表示通过
    budget: int = DEFAULT_BUDGET                # 最多尝试几轮
    workdir: Path = field(default_factory=Path.cwd)   # 判据在哪个目录跑
    notes: str = ""                             # 正文（补充说明）
    source: Path | None = None                  # 任务文件路径（报错时指给人看）


@dataclass
class CheckResult:
    """一条判据的执行结果。"""

    command: str
    exit_code: int
    output: str                                 # 已截断（保留尾部）
    duration: float

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


# ---------------------------------------------------------------- 加载任务


def load_goal(path: Path | str) -> Goal:
    """读一个任务文件（frontmatter + 正文），返回 Goal。

    格式见 goals/ 目录下的示例。这里刻意把"写错了"都变成 GoalError，
    而不是让程序带着一个残缺的 Goal 往下跑 —— **早失败，比跑偏 12 轮再失败便宜得多**。
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise GoalError(f"找不到任务文件：{path}")

    data, body = parse_frontmatter(path.read_text(encoding="utf-8"))

    text = as_text(data.get("goal"))
    if not text and body:
        # 兜底：允许把目标直接写成正文第一行（这样报错信息会更贴切）
        text = body.splitlines()[0].strip()
    if not text:
        raise GoalError(f"{path} 里没有 goal：请在 frontmatter 里写一行 'goal: ...'")

    checks = as_list(data.get("check"))
    if not checks:
        # 没有判据的长任务模式，等于退回"模型自己说做完了" —— 那还不如不做。
        # 所以这里**拒绝运行**，而不是给一个空列表放行。
        raise GoalError(
            f"{path} 里没有 check。没有判据就不该跑长任务模式：\n"
            "  check:\n    - pytest -q"
        )

    budget = _parse_budget(path, as_text(data.get("budget")))

    workdir_raw = as_text(data.get("workdir"))
    # 默认工作目录 = 任务文件所在目录的**父目录**（goals/x.md → 项目根目录）。
    # 默认值要来自已经存在的信息，而不是瞎猜一个。
    workdir = (path.parent / workdir_raw).resolve() if workdir_raw else path.parent.parent.resolve()
    if not workdir.is_dir():
        raise GoalError(f"{path} 指定的 workdir 不存在：{workdir}")

    return Goal(
        text=text,
        checks=checks,
        budget=budget,
        workdir=workdir,
        notes=body,
        source=path,
    )


def _parse_budget(path: Path, raw: str) -> int:
    if not raw:
        return DEFAULT_BUDGET
    try:
        budget = int(raw)
    except ValueError:
        raise GoalError(f"{path} 的 budget 必须是整数，收到 {raw!r}") from None
    if budget <= 0:
        raise GoalError(f"{path} 的 budget 必须大于 0，收到 {budget}")
    return budget


# ---------------------------------------------------------------- 跑判据


def run_checks(
    goal: Goal,
    cwd: Path | str | None = None,
    timeout: int = CHECK_TIMEOUT,
) -> list[CheckResult]:
    """跑**全部**判据，返回每一条的结果。

    四个刻意的决定：
    1. **不走 ToolExecutor**。Executor 是"模型调用的工具"的通道；
       判据是"程序自己跑的检查"。混在一起，模型就有机会看到并干预判据。
    2. **全部跑完，不提前退出**。目标常常是多条件的（功能 + 测试 + 不留脏文件），
       一次把问题都告诉模型，比挤牙膏式地一次报一个高效得多。
    3. **输出截断且保留尾部**。报错信息在尾部 ——
       这和 Day 4 写 bash 工具时的 MAX_LINES 是同一个判断，不是巧合。
    4. **超时算失败**。判据里如果写了 pytest 而它挂住，整个长任务就死了。
    """
    directory = Path(cwd or goal.workdir)
    results: list[CheckResult] = []

    for command in goal.checks:
        started = time.monotonic()
        try:
            # shell=True 和 bash 工具是同样的取舍：换来管道/重定向的便利，
            # 代价是判据命令本身必须是可信的（它来自任务文件，不是模型给的）
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(directory),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            exit_code = proc.returncode
            combined = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        except subprocess.TimeoutExpired:
            exit_code, combined = -1, f"判据超时（{timeout} 秒）：{command}"
        except OSError as exc:
            exit_code, combined = -1, f"判据执行失败：{type(exc).__name__}: {exc}"

        results.append(
            CheckResult(
                command=command,
                exit_code=exit_code,
                output=_truncate(combined),
                duration=time.monotonic() - started,
            )
        )

    return results


def _truncate(text: str) -> str:
    """只留最后 N 行 / 最后 8KB —— 报错在尾部。"""
    lines = text.splitlines()
    if len(lines) > MAX_OUTPUT_LINES:
        text = f"[只保留最后 {MAX_OUTPUT_LINES} 行]\n" + "\n".join(lines[-MAX_OUTPUT_LINES:])

    raw = text.encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        text = "[只保留最后 8KB]\n" + raw[-MAX_OUTPUT_BYTES:].decode("utf-8", errors="ignore")
    return text.strip()


# ---------------------------------------------------------------- 转述与记录


def build_retry_message(
    goal: Goal,
    results: Sequence[CheckResult],
    attempt: int,
    suspicious: Sequence[str] = (),
) -> str:
    """把失败结果转述成一条给模型看的 user 消息。

    **这是整个长任务模式的灵魂。** 只说"检查没通过，请继续"，模型就会把同一个
    错误再犯一遍；必须给出**可定位的证据**：命令原文、退出码、输出尾部。

    五个要素各有理由：
        第几次/共几次  → 模型知道还剩多少机会，会调整策略
        命令原文       → 模型知道跑的到底是什么，才能复现
        退出码         → 比"失败了"精确得多
        输出尾部       → 报错在尾部
        禁止改检查     → 提示词层面的反奖励作弊（挡不住故意的，但能挡住"顺手"）
    """
    failed = [result for result in results if not result.ok]
    parts: list[str] = [
        f"[目标未达成 · 第 {attempt}/{goal.budget} 次尝试]",
        f"目标（回顾）：{goal.text}",
        "",
        "下面这些判据没有通过。请根据输出**定位并修复**，然后继续：",
    ]

    for index, result in enumerate(failed, start=1):
        parts.append(
            f"\n--- 判据 {index}：{result.command} ---\n"
            f"退出码：{result.exit_code}（耗时 {result.duration:.1f}s）\n"
            f"输出（已截断，保留尾部）：\n{result.output or '(没有输出)'}"
        )

    parts.append(
        "\n注意：\n"
        "1. 判据由程序执行，你无法修改它。\n"
        "2. **禁止为了让判据通过而删改测试文件或检查脚本** —— 那不算完成。\n"
        "3. 如果某条判据你判断是环境问题而不是代码问题，请在回复里明确指出，"
        "不要假装它通过了。"
    )

    if suspicious:
        parts.append(
            "\n⚠️ 检测到工作区里这些「看起来像测试/检查」的文件被改动了：\n"
            + "\n".join(f"  - {item}" for item in suspicious)
            + "\n如果是为了让判据通过而改的，请改回来 —— 应该修的是被测的代码，不是测试。"
        )

    return "\n".join(parts)


def log_attempt(log_path: Path | str, attempt: int, results: Sequence[CheckResult]) -> None:
    """把这次尝试追加写一行 jsonl。

    用途有三个：调试（它为什么 12 轮都没过）、放弃时有据可查、
    以及给简历攒数据（平均尝试轮数 / 成功率）。
    jsonl 而不是重写整个文件 —— 和 Day 6 的记忆是同一个理由：追加便宜、坏一行只坏一行。
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "attempt": attempt,
        "passed": all(result.ok for result in results),
        "checks": [
            {
                "command": result.command,
                "exit_code": result.exit_code,
                "duration": round(result.duration, 2),
                "output": result.output[:2000],      # 日志里也不存全量
            }
            for result in results
        ],
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def git_changed_files(cwd: Path | str) -> list[str]:
    """列出工作区里被改动的文件。git 不可用 / 不是仓库时返回空列表。"""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []

    files: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) > 3:
            files.append(line[3:].strip().strip('"'))
    return files


def suspicious_changes(changed: Sequence[str]) -> list[str]:
    """从改动列表里挑出"像测试/检查"的文件。

    这是**反奖励作弊（reward hacking）**的第三道防线。
    真实 agent 系统里，模型为了让判据变绿去改测试是家常便饭。
    这里只做"指出可疑项"，不做强制 —— 因为改测试有时候是合理的（比如测试本身写错了），
    最终判断权还是留给人。**程序负责提供证据，人负责定夺。**
    """
    hits: list[str] = []
    for item in changed:
        name = Path(item).name.lower()
        lowered = item.lower().replace("\\", "/")
        looks_like_test = (
            name.startswith("test_")
            or name.endswith("_test.py")
            or name in TEST_LIKE_NAMES
            or name.endswith("_check.py")
            or name.startswith("check_")
            or "/tests/" in lowered
        )
        if looks_like_test:
            hits.append(item)
    return hits
