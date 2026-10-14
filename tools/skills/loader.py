"""Day 8 · Skill 加载器：把"操作手册"变成模型按需取用的知识。

## 这一层在解决什么
有些能力不是"一个动作"，而是"一整套流程和领域知识"（怎么审查代码、怎么排查报错、
这个项目的提交信息怎么写）。它们写不成 `def f(a, b) -> str`，只能写成**手册**。

把手册全塞进 system prompt 的代价：50 份 × 约 2000 token = 10 万 token，
又贵又会稀释注意力，而一次对话通常只用得上其中一份。

## 解法：渐进式披露（progressive disclosure）
    阶段① 扫描  启动时只解析 YAML frontmatter（name + description），正文不进上下文
    阶段② 注入  每次请求只带一张"清单"（N × 约 25 token），塞进 skill 工具的 description
    阶段③ 加载  模型主动调用 skill(name=...) 时，才把正文读出来

## 为什么这能接进已有的 agent
最后产物仍然是一个 `Tool(name, description, parameters, fn)`，
所以对 ToolExecutor / ChatNode / ToolCallNode / call_llm 来说毫无区别 ——
和 Day 7 接 MCP 一样，靠 `executor.register()` 一个口子进来，主循环零改动。

## 已知的取舍（诚实标注）
1. `scan()` 其实仍把整个文件读进了内存（为了简单）。省的是 **token**，不是磁盘 IO。
   要做到连 IO 都省，可以只读前 4KB 去找 frontmatter 的结束位置。
2. `loaded` 集合只记"哪份手册加载过"，不感知 Day 6 的上下文压缩。
   如果正文被压缩成摘要、而 loaded 还记着它，模型就再也读不到正文了。

## Day 9 的改动：解析器下沉了
frontmatter 解析本来住在本文件里。Day 9 的任务文件（goals/*.md）需要同一套能力，
于是把它提到了 `core/frontmatter.py` —— **同一份逻辑被第二个地方需要，就该提取出来**。
`parse_skill_file` 这个名字保留成一层薄包装，免得调用方被迫改名。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.frontmatter import as_text, parse_frontmatter
from tools.builtins.tool_def import Tool

SKILL_FILE = "SKILL.md"
MAX_BODY_BYTES = 30 * 1024        # 和 read 工具保持一致：一次别喂爆上下文


@dataclass
class Skill:
    """一份手册的**元数据**。

    注意：正文**不存在这里**。这是渐进式加载的字面体现 ——
    只有 `load_body()` 被调用（阶段③）时，正文才会被读出来。
    """

    name: str
    description: str
    path: Path

    def load_body(self) -> str:
        """阶段③：真正读取正文。在扫描/注入阶段绝不会被调用。"""
        text = self.path.read_text(encoding="utf-8")
        _meta, body = parse_skill_file(text)

        raw = body.encode("utf-8")
        if len(raw) > MAX_BODY_BYTES:
            body = raw[:MAX_BODY_BYTES].decode("utf-8", errors="ignore")
            # 给出原始路径 → 模型可以用 read 自己去取剩下的部分（二级渐进式披露）
            body += f"\n\n[手册过长已截断。需要细节请用 read 打开 {self.path}]"

        return f"# 技能：{self.name}\n\n{body}"


def parse_skill_file(text: str) -> tuple[dict[str, str], str]:
    """Day 8 的老名字，保留作为兼容入口（实现已经搬到 core/frontmatter.py）。

    有意思的是：这次重构之所以敢做，正是因为 Day 8 写的 skill_check.py
    会立刻告诉你有没有改坏 —— **测试的价值不是"证明代码对"，
    而是"让你敢改代码"**。
    """
    data, body = parse_frontmatter(text)
    return {key: value for key, value in data.items() if isinstance(value, str)}, body


class SkillLoader:
    """扫描 skills/ 目录，建立"技能索引"（阶段①）。"""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.skills: dict[str, Skill] = {}
        self.warnings: list[str] = []

    def scan(self) -> dict[str, Skill]:
        """扫描目录，**只解析 frontmatter**，正文一个字节都不进上下文。"""
        self.skills, self.warnings = {}, []

        if not self.root.is_dir():
            self.warnings.append(f"技能目录不存在：{self.root}")
            return self.skills

        for path in sorted(self.root.glob(f"*/{SKILL_FILE}")):
            self._load_one(path)
        return self.skills

    def _load_one(self, path: Path) -> None:
        """读一份手册的元数据。

        坏数据只记 warning 不抛异常 —— 和 Day 4 的原则一致：
        一份坏手册不该炸掉整个启动流程。
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.warnings.append(f"读不了 {path}：{exc}")
            return

        meta, _body = parse_frontmatter(text)     # ← 下划线表示"刻意丢弃"
        # 用 as_text 而不是直接 .strip()：frontmatter 的值可能是列表，硬 strip 会崩
        name = as_text(meta.get("name")) or path.parent.name
        description = as_text(meta.get("description"))

        if not description:
            # 没有 description 就没法被路由：模型不知道**什么时候**该用它。
            # 一份没法路由的手册留在索引里只会干扰模型的判断，所以直接丢掉。
            self.warnings.append(f"{path} 缺少 description，已跳过")
            return
        if name in self.skills:
            self.warnings.append(f"技能名重复（{name}），已跳过：{path}")
            return

        self.skills[name] = Skill(name=name, description=description, path=path)


def build_skill_tool(loader: SkillLoader, loaded: set[str] | None = None) -> Tool:
    """把整个技能库做成**一个**工具（阶段② + 阶段③）。

    为什么是 1 个工具服务 N 份手册，而不是 N 个工具？
    —— 因为工具列表每次请求都要付 token。做成 N 个工具，就等于把每份手册的
       description 都常驻进 prompt，又回到了"全量注入"的老问题。

    loaded：记录哪些手册已经加载过。第二次调用只回一句提示，
    省下的是真金白银的 token（也让模型别把同一份手册读两遍）。
    """
    loaded = loaded if loaded is not None else set()

    # 阶段②：这张清单就是常驻成本，每行约 25 token
    catalog = "\n".join(
        f"- {skill.name}：{skill.description}" for skill in loader.skills.values()
    ) or "（当前没有任何手册）"

    def load_skill(name: str) -> str:
        """阶段③：模型主动调用时，才读正文。"""
        name = (name or "").strip()
        skill = loader.skills.get(name)
        if skill is None:
            # 抛异常（而不是返回错误字符串），Executor 才会标成 is_error，
            # 模型才知道"这次没成功" —— 和 Day 7 适配器同一个理由。
            available = "、".join(loader.skills) or "（空）"
            raise ValueError(f"没有这份手册：{name!r}。可用：{available}")

        if name in loaded:
            return f"[{name} 已经在上下文里了，直接参考上文，不要重复加载]"

        loaded.add(name)
        return skill.load_body()

    return Tool(
        name="skill",
        description=(
            "按需加载一份操作手册（skill）。\n"
            "当任务符合下面某份手册的适用场景时，**先调用本工具把它的正文读进来，再照着做**，"
            "不要凭记忆猜流程。手册没提到的事情照常用其他工具处理。\n\n"
            f"可用手册：\n{catalog}"
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "enum": list(loader.skills),   # 枚举让模型几乎不可能拼错名字
                    "description": "要加载的手册名",
                }
            },
            "required": ["name"],
        },
        fn=load_skill,
        # 加载手册只是读本地文件、返回文本，没有任何副作用 —— 不必打扰用户。
        # （Day 10 加的 requires_approval 默认是 True，这里显式放宽。）
        requires_approval=False,
    )
