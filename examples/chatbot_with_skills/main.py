"""Day 8 示例：让 agent 拥有"按需加载的操作手册"。

和 Day 7 的 chatbot_with_mcp 相比，本文件只多了 3 行有效代码：
    扫描手册目录 → 做成一个 skill 工具 → 从 extra_tools 口子注册进去

主循环、执行器、模型调用全都没动 —— 这是第二次吃到"接口定型的回报"。

运行：
    python -m examples.chatbot_with_skills.main
可以试着问：
    帮我看看 tools/builtins/bash.py 有什么问题     → 应该先加载 code-review
    我这次改动该怎么写提交信息？                    → 应该先加载 commit-message
    帮我看看这个报错：KeyError: 'name'             → 应该先加载 debug-python
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from examples.chatbot_with_tools.main import run_chat        # noqa: E402
from tools.skills import SkillLoader, build_skill_tool       # noqa: E402


def main() -> None:
    loader = SkillLoader(PROJECT_ROOT / "skills")
    loader.scan()

    for warning in loader.warnings:
        print(f"[skill] ⚠️ {warning}")
    if not loader.skills:
        print("[skill] 没有加载到任何手册，检查 skills/ 目录")
        return

    # 注意这里只打印了名字：正文一份都没读，这就是阶段②的成本
    print(f"[skill] 已索引 {len(loader.skills)} 份手册：{list(loader.skills)}")
    print("[skill] 正文会在模型调用 skill 工具时才加载\n")

    run_chat(extra_tools=[build_skill_tool(loader)])


if __name__ == "__main__":
    main()
