"""通用 frontmatter 解析：把"元数据"和"正文"切开。

## 这个文件是从哪来的
Day 8 写 Skill 加载器时，这个解析器住在 `tools/skills/loader.py` 里。
Day 9 的任务文件（`goals/*.md`）需要同一套能力 ——
**"同一份逻辑被第二个地方需要"就是该把它提取出来的时候。**

## 为什么放到 core/
项目有一条铁律：`core/` 不知道 `tools/` 的存在。
而 frontmatter 解析既不依赖工具、也不依赖图编排，是纯粹的通用能力，
所以它属于 core —— 这样 `tools/skills/` 和 `core/goal.py` 都能用它，
依赖方向仍然是单向的（tools → core）。

## 支持的语法（刻意的子集）
    key: value                单行键值
    key:                      空值 + 紧跟若干列表项
      - item one
      - item two

不支持嵌套字典、多行文本、锚点引用等 YAML 高级特性 —— 我们的元数据用不上。
真需要时换 PyYAML，但**必须是** `yaml.safe_load`：
`yaml.load` 能构造任意 Python 对象，是已知的安全漏洞。
"""

from __future__ import annotations


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """把文件切成 (frontmatter 字典, 正文)。

    三条返回路径（都要能说清楚为什么）：
        1. 不以 --- 开头      → 没有 frontmatter，整个文件都是正文
        2. 有 --- 但没闭合    → 当作没有 frontmatter，返回原文
        3. 正常切分

    路径 1 和 2 故意返回**原文**而不是空串：这样这份文件不会凭空消失，
    它会带着原文走到调用方，在那里因为"缺 description / 缺 check"被拦下，
    错误信息比"解析失败"好懂得多。**错误要在最懂它的地方报。**
    """
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":     # .strip() 容忍行尾空格和 Windows 换行
            end = index
            break
    if end is None:
        return {}, text

    data: dict[str, object] = {}
    current_list: list[str] | None = None

    for raw_line in lines[1:end]:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # --- 列表项：归属到上一个"值为空的 key" ---
        if stripped == "-" or stripped.startswith("- "):
            if current_list is not None:
                current_list.append(_unquote(stripped[1:].strip()))
            continue                              # 没有归属的列表项：跳过

        # partition 只按**第一个**冒号切，value 里再有冒号也不会被切断
        key, sep, value = raw_line.partition(":")
        if not sep or not key.strip():
            continue

        key = key.strip()
        value = _unquote(value)
        if value:
            data[key] = value
            current_list = None
        else:
            # 空值：先放一个空列表占位，后面若有 "- xxx" 会往里追加
            empty: list[str] = []
            data[key] = empty
            current_list = empty

    return data, "\n".join(lines[end + 1:]).strip()


def as_text(value: object) -> str:
    """把 frontmatter 的值当**标量**读。不是字符串就返回空串。

    为什么需要它：解析器可能给出 str、list 或 None，
    而 `name` / `description` / `goal` 这类字段只应该是标量。
    直接 `.strip()` 会在值意外是 list 时崩掉。
    """
    return value.strip() if isinstance(value, str) else ""


def as_list(value: object) -> list[str]:
    """把 frontmatter 的值当**列表**读。单行写法（字符串）也接受。

    于是任务文件里既能写：
        check:
          - pytest -q
          - python check.py
    也能写：
        check: pytest -q
    """
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _unquote(value: str) -> str:
    """去掉值两端成对的引号（只去一层，不动中间的引号）。"""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip()
    return value
