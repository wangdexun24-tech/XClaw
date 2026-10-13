"""Day 8 验收：Skill 必须能"脱离模型"独立工作，并且真的做到了按需加载。

七项检查，每项都对应一个"如果错了会怎样"：
  ① 扫描：3 份手册都被识别，name/description 正确
  ② **渐进式加载**：正文没有被提前读进上下文（用哨兵字符串证明）
  ③ 容错：坏数据只警告不崩（缺 description / 没有 frontmatter / 目录不存在）
  ④ 加载：调用 skill 工具后正文才出现
  ⑤ 幂等：第二次加载同一份，不重复返回全文
  ⑥ 工具契约：to_llm_format 合法，enum 覆盖全部手册
  ⑦ 接入：注册进 ToolExecutor 后工具数 8 → 9，且原有工具没被破坏

第 ② 项是整份验收里最有价值的地方：
  大多数测试验证的是"**做了**某件事"，而渐进式加载的核心价值是"**没做**某件事"。
  用正文里的哨兵字符串，就把一个"不存在的东西"变成了可断言的证据。

运行：python skill_check.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools import ToolExecutor                                      # noqa: E402
from tools.skills import SkillLoader, build_skill_tool, parse_skill_file  # noqa: E402

SKILLS_DIR = PROJECT_ROOT / "skills"

# 只写在 skills/code-review/SKILL.md 的**正文**里，frontmatter 里没有
SENTINEL = "SENTINEL_ONLY_IN_BODY_7f3a"


def fake_call(call_id: str, name: str, arguments: dict):
    """造一个假的 ToolCall（和 tools_check.py / mcp_check.py 用的是同一招）。"""
    return type("C", (), {"id": call_id, "name": name, "arguments": arguments})()


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def check_scan() -> SkillLoader:
    section("① 扫描手册目录")
    loader = SkillLoader(SKILLS_DIR)
    loader.scan()

    for warning in loader.warnings:
        print(f"  ⚠️ {warning}")
    assert not loader.warnings, "真实手册目录不该产生警告"
    assert len(loader.skills) == 3, f"应该识别出 3 份手册，实际 {len(loader.skills)}"

    for name, skill in loader.skills.items():
        assert skill.name == name, "索引的 key 必须等于 skill.name"
        assert skill.description.strip(), f"{name} 的 description 不能为空"
        print(f"  ✓ {name}: {skill.description[:38]}…")
    return loader


def check_progressive(loader: SkillLoader) -> None:
    section("② 渐进式加载：正文没有泄漏到索引里")

    # 把"模型在阶段①② 能看到的一切"拼起来 —— 如果哨兵出现在这里，说明正文被提前读了
    visible = json.dumps(
        {
            "names": list(loader.skills),
            "descriptions": [s.description for s in loader.skills.values()],
            "paths": [str(s.path) for s in loader.skills.values()],
        },
        ensure_ascii=False,
    )
    assert SENTINEL not in visible, "正文泄漏进索引了，渐进式加载失效"
    print("  ✓ 元数据里没有正文（哨兵不在其中）")

    tool = build_skill_tool(loader)
    spec = json.dumps(tool.to_llm_format(), ensure_ascii=False)
    assert SENTINEL not in spec, "正文泄漏进工具描述了，模型每次请求都要多付这份 token"
    print("  ✓ 工具的 parameters/description 里也没有正文")

    # 顺手算一下这份设计的收益（数字留给简历用）
    catalog_chars = sum(len(s.name) + len(s.description) for s in loader.skills.values())
    body_chars = sum(len(s.load_body()) for s in loader.skills.values())
    print(f"  · 注入成本：约 {catalog_chars} 字符")
    print(f"  · 若全量注入正文：约 {body_chars} 字符")
    print(f"  · 节省：{(1 - catalog_chars / body_chars) * 100:.0f}%")


def check_frontmatter_parser() -> None:
    section("③ frontmatter 解析 + 坏数据容错")

    # 正常情况
    meta, body = parse_skill_file("---\nname: x\ndescription: 用: 冒号也不怕\n---\n正文\n")
    assert meta == {"name": "x", "description": "用: 冒号也不怕"}, meta
    assert body == "正文", body
    print("  ✓ 正常 frontmatter 解析正确（value 里的冒号没被切断）")

    # 没有 frontmatter / 没有闭合
    assert parse_skill_file("就是一段正文") == ({}, "就是一段正文")
    assert parse_skill_file("---\nname: x\n正文没闭合")[0] == {}
    print("  ✓ 没有 frontmatter / 没闭合 → 当作纯正文，不崩")

    # 用临时目录造三份坏手册，验证 loader 只警告不崩
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "good").mkdir()
        (root / "good" / "SKILL.md").write_text(
            "---\nname: good\ndescription: 一份好手册\n---\n正文\n", encoding="utf-8"
        )
        (root / "no_desc").mkdir()
        (root / "no_desc" / "SKILL.md").write_text(
            "---\nname: no_desc\n---\n正文\n", encoding="utf-8"
        )
        (root / "bare").mkdir()
        (root / "bare" / "SKILL.md").write_text("完全裸奔，没有 frontmatter\n", encoding="utf-8")
        (root / "no_name").mkdir()
        (root / "no_name" / "SKILL.md").write_text(
            "---\ndescription: 没写 name\n---\n正文\n", encoding="utf-8"
        )

        broken = SkillLoader(root)
        broken.scan()
        assert list(broken.skills) == ["good", "no_name"], list(broken.skills)
        assert len(broken.warnings) == 2, broken.warnings
        # 没写 name 时用**目录名**兜底 —— 文件夹名字就是天然的默认值
        assert broken.skills["no_name"].name == "no_name"
        for warning in broken.warnings:
            print(f"  ✓ {warning}")

        # 目录不存在也不该崩
        missing = SkillLoader(root / "does_not_exist")
        assert missing.scan() == {} and missing.warnings
        print(f"  ✓ {missing.warnings[0]}")


def check_load_and_idempotent(loader: SkillLoader) -> None:
    section("④ 加载手册正文 / ⑤ 幂等（不重复加载）")
    tool = build_skill_tool(loader)

    body = tool.execute(name="code-review")
    assert SENTINEL in body, "加载后正文里应该出现哨兵"
    assert body.startswith("# 技能：code-review")
    print(f"  ✓ 首次加载 {len(body)} 字符，哨兵出现")

    again = tool.execute(name="code-review")
    assert SENTINEL not in again, "第二次不该再返回全文"
    assert "已经" in again
    print(f"  ✓ 第二次加载只回提示：{again}")

    # 换一份手册不受影响（说明 loaded 是按名字记的）
    other = tool.execute(name="commit-message")
    assert "提交信息规范" in other
    print("  ✓ 换一份手册仍能正常加载（loaded 是按名字记录的）")


def check_tool_contract(loader: SkillLoader) -> None:
    section("⑥ 工具契约 + 接入执行器")
    executor = ToolExecutor()
    builtin_count = len(executor.tools)

    tool = build_skill_tool(loader)
    spec = tool.to_llm_format()
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "skill"
    assert spec["function"]["parameters"]["type"] == "object"
    enum = spec["function"]["parameters"]["properties"]["name"]["enum"]
    assert set(enum) == set(loader.skills), enum
    print(f"  ✓ name 的 enum = {enum}")

    executor.register([tool])
    names = [t["function"]["name"] for t in executor.get_llm_tools()]
    assert "skill" in names and len(executor.tools) == builtin_count + 1
    print(f"  ✓ 工具总数 {builtin_count} → {len(executor.tools)}，skill 已对模型可见")

    # 通过执行器调用（走完整的 tool_calls 通路，而不是直接调 fn）
    result = executor.execute(fake_call("s1", "skill", {"name": "debug-python"}))
    assert not result.is_error and "Traceback" in result.content
    print(f"  ✓ 经执行器调用成功：{result.content[:34]}…")

    # 错误路径：不存在的名字必须变成 is_error
    bad = executor.execute(fake_call("s2", "skill", {"name": "no_such_skill"}))
    assert bad.is_error, "不存在的 skill 应该报错"
    print(f"  ✓ 错误路径：{bad.content[:56]}")

    # 原有工具没被破坏
    local = executor.execute(fake_call("s3", "bash", {"command": "echo skill-ok"}))
    assert "skill-ok" in local.content and not local.is_error
    assert {"read", "write", "edit", "bash", "ls", "grep", "find", "search"} <= set(
        executor.tool_map
    )
    print("  ✓ 8 个本地工具依然完好")


def main() -> None:
    loader = check_scan()
    check_progressive(loader)
    check_frontmatter_parser()
    check_load_and_idempotent(loader)
    check_tool_contract(loader)
    print("\n✅ Day 8 验收全部通过")
    print("\n思考题：loaded 集合不感知上下文压缩。")
    print("  如果某份手册的正文被压缩成摘要，而 loaded 仍记着它，模型会拿到什么？")


if __name__ == "__main__":
    main()
