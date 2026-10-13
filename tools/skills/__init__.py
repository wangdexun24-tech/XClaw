"""Day 8 · Skill：按需加载的操作手册（渐进式披露）。

和 tools/mcp/ 是同一类东西的两种形态：
    mcp/    把"跑在别处的**工具**"翻译成 Tool
    skills/ 把"按需取用的**知识**"翻译成 Tool
"""

from .loader import Skill, SkillLoader, build_skill_tool, parse_skill_file

__all__ = ["Skill", "SkillLoader", "build_skill_tool", "parse_skill_file"]
