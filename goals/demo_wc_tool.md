---
goal: 在 tools/builtins/ 下新增一个 wc 工具（统计文件的行数、词数、字符数），
      注册进 get_builtin_tools() 返回的列表里，并保证现有的 tools_check.py 仍然通过。
check:
  - python tools_check.py
  - python -c "import sys; sys.path.insert(0, '.'); from tools.builtins import get_builtin_tools as g; names = {t.name for t in g()}; assert 'wc' in names, f'wc 没注册进工具列表：{sorted(names)}'"
budget: 8
---

## 说明

- `wc` 工具参考 `tools/builtins/read.py` 的写法：一个纯函数 + 在 `tool_def.py` 里登记。
- 参数：`path`（必填）。返回一句话，例如 `12 行 / 45 词 / 320 字符`。
- 文件不存在时抛 `FileNotFoundError`（工具失败要让 Executor 标成 is_error，不要返回错误字符串）。
- 不需要写新的测试；`tools_check.py` 与上面第二条判据就是验收标准。

## 这个任务为什么适合练手

1. 判据完全客观（`tools_check.py` 会真的报错）。
2. 规模适中：要 `ls` 看结构、`read` 抄一个现成模板、`write` 新文件、`edit` 改注册列表。
3. 有天然的失败路径 —— 第一次很容易漏掉"注册"这一步，于是第一轮判据失败，
   第二轮的重试消息会精确指出「wc 没注册进工具列表」，模型就懂了。
   **第一轮失败是好事：它证明判据真的在起作用，而不是摆设。**
