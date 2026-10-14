# XClaw

> 一个跑在**终端**里的编程智能体（coding agent）——从零手写，不依赖 LangChain / LangGraph。

用 92 行实现了一套图编排框架，把「模型 → 工具 → 模型」这个循环画成**图里的一个环**；
在这张图上逐层叠加出工具系统、记忆、MCP、Skill、长任务与操作确认六种能力。

| | |
|---|---|
| **运行形态** | 命令行工具（CLI）：`pip install -e .` 后得到 `xclaw` 命令 |
| **语言 / 版本** | Python 3.11+（类型注解 + dataclass） |
| **核心代码** | 约 **3,600 行**（`core` + `tools` + `examples` + CLI） |
| **测试与验收** | 约 **2,200 行**：pytest **49 个用例**（约 2 秒）+ 8 个可独立运行的验收脚本 |
| **第三方依赖** | `openai`、`python-dotenv`、`ddgs`、`mcp`、`fastmcp` —— **只有这五个** |
| **框架** | 无。图编排、工具系统、记忆、确认机制、工作区边界全部自写 |

---

## 30 秒了解它

它是一个**终端里的 agent**：你 `cd` 到任意项目目录，敲 `xclaw`，用中文说需求，
它会自己选工具去读文件、改代码、跑命令，**危险操作会先问你**，做完把结果报给你。

```
$ cd ~/my-project && xclaw
============================================================
🤖 XClaw Agent（带工具的对话）
============================================================
[workspace] 文件工具的工作区：/Users/me/my-project
[memory] 这是新的对话
可用工具：read, write, edit, bash, ls, grep, find, search
输入 exit / quit 退出；/clear 清空对话记忆；/remember <内容> 记住一件事

👤 你：看看 core/node.py 是干什么的，用三句话总结

🤖 助手：我先读一下这个文件。
  [工具 ✓] read({'path': 'core/node.py'})
           → """轻框架核心：节点 + 编排。一句话：Node 负责"做什么"…

🤖 助手：这个文件实现了一套节点编排框架，共 92 行：
        1. Node 只负责"做什么"，返回一个 action 字符串；
        2. 去哪由连线决定（a - "action" >> b）；
        3. Flow 按 action 一步步跑，直到没有后继。
```

**它不是聊天机器人，是"能动手"的 agent**：上例中它真的调用了文件读取工具，
而不是凭记忆编内容。涉及写文件 / 改代码 / 执行命令时，它会**停下来等你确认**：

```
👤 你：demo.py 里的 add 函数有 bug，帮我修好

🤖 助手：找到了 —— add 返回的是 a - b。我改一下。

────────────────────────────────────────────────────────
[需要确认] edit
完整参数（不截断 —— 人要据此做决定）：
{
  "path": "demo.py",
  "old_text": "    return a - b",
  "new_text": "    return a + b"
}

[修改预览] - 表示删除，+ 表示新增（只预览被替换的片段）：
--- 原文
+++ 修改后
@@ -1 +1 @@
-    return a - b
+    return a + b
────────────────────────────────────────────────────────
允许执行吗？输入 y 同意，其它一律拒绝 [y/N]：
```

> 说明：以上是终端实际输出的**节选**（`[工具 ✓]` 与确认框是程序输出的原文；
> 模型回答按排版做了压缩）。工作区里只读的工具（`read` / `ls` / `grep` / `find`）
> 不会打扰你，只有"会改东西"的操作才需要确认。

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/wangdexun24-tech/XClaw.git
cd XClaw

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .                   # 安装依赖，并得到 xclaw 命令

cp .env.example .env               # 然后填入下面的配置
```

`.env`（任何 OpenAI 兼容的服务都能用：DeepSeek / Kimi / 通义 / 本地 Ollama）：

```dotenv
OPENAI_API_KEY=你的key
OPENAI_BASE_URL=https://api.deepseek.com/v1     # 注意带 /v1
OPENAI_MODEL_ID=deepseek-chat
```

> 想让 `xclaw` 在**任意目录**都能用？把命令链接到 PATH 里，配置放一份到 `~/.xclaw/.env`：
>
> ```bash
> ln -sf ~/PycharmProjects/XClaw/.venv/bin/xclaw ~/.local/bin/xclaw
> mkdir -p ~/.xclaw && cp ~/PycharmProjects/XClaw/.env ~/.xclaw/.env
> ```
> 配置是两级的：**项目里的 `.env` 优先，`~/.xclaw/.env` 兜底。**

### 2. 跑测试（不花 API 额度）

```bash
pip install -e ".[dev]"     # 含 pytest
pytest                      # 49 个用例，约 2 秒
xclaw check all             # 8 个验收脚本，输出可读报告
```

### 3. 开始用

```bash
cd 你想让 agent 干活的项目      # 工作区 = 你启动时的目录
xclaw
```

---

## 命令行接口

```
$ xclaw --help
usage: xclaw [-h] {chat,goal,check,tools} ...

  chat    交互式 agent（默认命令）
  goal    跑一个长任务（目标 + 可判定判据 + 预算）
  check   跑离线验收脚本（不花 API 额度）
  tools   列出工具及其确认策略
```

| 命令 | 作用 |
|---|---|
| `xclaw` | 进入交互式对话（不带子命令时的默认行为） |
| `xclaw goal goals/demo_wc_tool.md` | 给一个目标，让它自主跑到**程序验证通过**为止 |
| `xclaw check all` / `xclaw check approval` | 跑全部 / 单项离线验收 |
| `xclaw tools` | 列出 8 个工具及其确认策略 |

**交互内命令**：`exit` / `quit` 退出 · `/clear` 清空对话历史 · `/remember <内容>` 记一条长期记忆

**会话数据**存在工作区的 `.xclaw/` 下 —— **按工作区隔离**，A 项目的历史不会串到 B 项目。

---

## 它能做什么

| 你说 | 它做什么 |
|---|---|
| 当前目录下有哪些文件？ | 调 `ls`，然后归纳目录结构 |
| 看看 `core/node.py` 是干什么的，用三句话总结 | 调 `read` → 总结（`[flow]` 日志会显示循环走了几步） |
| 在 `tmp_demo/` 下建一个 `hello.py`，打印 hello，然后跑一下 | 调 `write` 创建文件（**先确认**）→ `bash` 执行（**先确认**）→ 回报输出 |
| 哪个文件定义了 `call_llm`？ | 调 `grep` → 返回 `core/llm.py:44` |
| 帮我看看 `tools/builtins/edit.py` 有什么问题 | 先加载 `code-review` **手册** → 再读文件 → 按手册规定的格式输出 |
| 我这次改动该怎么写提交信息？ | 先加载 `commit-message` 手册 → 跑 `git diff` → 按规范生成 |
| `(128*3+45)/7` 等于多少？ | 调远程 **MCP 工具** `calc`（跑在另一个进程里） |

**8 个内置工具**：

| 工具 | 作用 | 确认策略 |
|---|---|---|
| `read` | 读文件（支持 `offset`/`limit` 分页，30KB 截断并提示如何继续） | 免确认 |
| `ls` | 列目录（不递归，目录名带 `/` 后缀） | 免确认 |
| `grep` | 内容搜索，返回 `相对路径:行号:内容` | 免确认 |
| `find` | 按通配符查找文件 | 免确认 |
| `write` | 写文件（父目录自动创建，**原子写**） | 需要确认 |
| `edit` | 精确替换一处文本；要求原文**唯一匹配**，否则拒绝 | 需要确认（附 diff 预览） |
| `bash` | 执行命令，返回 stdout/stderr/退出码 | 需要确认（危险命令高亮） |
| `search` | 联网搜索（DuckDuckGo） | 需要确认 |

---

## 架构

### 分层：三层 + 单向依赖

```
                    用户（终端）
                         │
   ┌─────────────────────┴─────────────────────┐
   │  examples/   接线层：把能力连成一张图        │
   │   6 个渐进式示例（每个只引入一个新概念）      │
   └─────────────────────┬─────────────────────┘
                         │ 只向下依赖
   ┌─────────────────────┴─────────────────────┐
   │  tools/      能力层                        │
   │   builtins/  8 个工具（纯函数 + Tool 定义） │
   │   executor.py  解析 / 执行 / 规范化          │
   │   mcp/       把"别处的动作"翻译成 Tool       │
   │   skills/    把"按需的知识"翻译成 Tool       │
   └─────────────────────┬─────────────────────┘
                         │ 只向下依赖
   ┌─────────────────────┴─────────────────────┐
   │  core/       通用能力层（**不认识 tools**）  │
   │   node       图编排 · llm 模型调用            │
   │   memory     记忆 / 压缩 / 归档 / 自愈        │
   │   frontmatter 元数据解析                     │
   │   goal       目标与判据 · approval 操作确认    │
   │   workspace  工作区边界 · 原子写              │
   └───────────────────────────────────────────┘
```

**依赖单向**是硬约束：`core` 不认识 `tools`。这个约束直接决定了文件该放哪 ——
比如 frontmatter 解析器同时被 `tools/skills/` 和 `core/goal.py` 需要，
它就只能放在 `core/`。

### agent 主循环 = 图里的一个环

```
   ChatNode ──"tool_call"──▶ ApprovalNode ──"proceed"──▶ ToolCallNode
        ▲                                                      │
        └──────────────────────"chat"──────────────────────────┘
```

- `ChatNode` 调模型：返回了 `tool_calls` 就往下走，没有就结束
- `ApprovalNode` 决定每个调用是否放行（加它时**只需把节点插进图里**）
- `ToolCallNode` 执行工具、写回结果，然后**回到模型** —— 环在这里闭合

### 一次工具调用的消息序列（协议要求，最容易犯错的地方）

```
1. user        {role: "user", content: "看看 core/node.py"}
2. assistant   {role: "assistant", tool_calls: [{id: "call_1", name: "read", ...}]}
3. tool        {role: "tool", tool_call_id: "call_1", content: "…文件内容…"}
4. assistant   {role: "assistant", content: "这个文件实现了一个节点编排框架…"}
```

**规则**：第 2 条必须先于第 3 条；第 3 条的数量与 `tool_call_id` 必须和第 2 条一一对应。
违反任何一条，API 都会直接拒绝请求。这条约束在压缩切点、崩溃恢复、拒绝分支**三个地方**
分别逼出了一个设计。

---

## 四个技术亮点

### ① 把 agent 循环写成图，而不是 `while`

**问题**：控制流写在代码里，加一个分支就要改主循环。

**做法**：自研 92 行图编排框架，`Node.exec()` 返回 `(action, payload)` ——
节点不关心下一步去哪，**分支与循环因此从代码变成数据**：

```python
chat - "tool_call" >> approval      # 有工具要执行 → 先确认
approval - "proceed" >> tool_call
tool_call - "chat" >> chat          # 执行完 → 回到模型（环闭合）
```

**效果**：后续接入 MCP、Skill、长任务、操作确认时，**核心 `ChatNode` 一行没改**
（从记忆接入定型后到项目完成，五天未改动）。

**取舍**：多一层抽象要维护。换来的是流程可画、可改、可单独测试。

### ② 统一 `Tool` 契约：不同来源的能力，同一个接入点

**问题**：工具可能跑在本进程（`read`）、别的进程（MCP 服务器），
或者根本不是"动作"而是"知识"（操作手册）。

**做法**：把一切统一翻译成同一个契约，接入点收敛为一个 `register()`：

```
tools/mcp/    远程的**动作**  →  MCPClient + to_local_tools()    →  executor.register()
tools/skills/ 本地的**知识**  →  SkillLoader + build_skill_tool() →  executor.register()
                       两者都没让 主循环 / 执行器 / llm 改动一行
```

契约本身在项目里被**扩展过两次，但从未被破坏**（都给了 fail-safe 默认值）：

| 新增属性 | 默认值 | 效果 |
|---|---|---|
| `requires_approval: bool` | `True` | 新接入的工具**不改一行**就被纳入确认保护 |
| `preview: Callable \| None` | `None` | 只有 `edit` 提供 diff，其它工具不受影响 |

### ③ 长任务模式：把"结束"的决定权从模型手里拿走

**问题**：之前"活干完了"是**模型自己宣布的**。它说"我修好了"，而测试还是红的 ——
拿模型的判断去验证模型的行为，是循环论证。

**做法**：任务文件声明**程序可判定的完成判据**与预算，每轮结束自动验证：

```markdown
---
goal: 在 tools/builtins/ 下新增一个 wc 工具，注册进 get_builtin_tools()，并保证 tools_check.py 通过。
check:
  - python tools_check.py
  - python -c "from tools.builtins import get_builtin_tools as g; assert 'wc' in {t.name for t in g()}"
budget: 8
---
```

```
   ChatNode ⇄ ToolCallNode        ← 内环：怎么做（主循环代码一行没改）
        │
        └─"done"─▶ VerifyNode ─"retry"─▶ ChatNode     ← 外环：做完了没有
                       │
                       ├─"passed" ─▶ 结束（成功）
                       └─"give_up"─▶ 结束（失败，报告原因）
```

**自主性三要素**（缺一个就失控）：**循环**（失败自动重来）、
**判据**（程序可判定）、**预算**（防止烧光额度）。

**四条关键设计**：

1. **判据必须由外部给出** —— 让模型自己定判据，等于让运动员当裁判。
   任务文件缺 `check` 时**直接拒绝运行**。
2. **重试必须带证据** —— 命令原文 + 退出码 + 输出尾部。
   只说"没过，请继续"，模型会把同一个错误再犯一遍。
3. **判据不走 `ToolExecutor`** —— Executor 是"模型调用的工具"的通道，
   判据是"程序自己跑的检查"，混在一起模型就有机会干预。
4. **反作弊** —— 跑判据前用 `git status` 挑出"看起来像测试"的改动并提示给人
   （只提供证据，不强制拦截）。

### ④ 安全默认值：会出错的默认值，必须往安全一边靠

| 位置 | 默认值 | 忘了声明的后果 |
|---|---|---|
| `Tool.requires_approval` | `True` | 多问一句 |
| 没配置确认器 | **拒绝** | 立刻发现，而不是静默危险 |
| 未知工具要不要确认 | **要** | "不知道"时往安全一边靠 |
| 上下文压缩前归档失败 | **不压缩** | 多占上下文，不丢原始记录 |
| 任务文件缺判据 | **拒绝运行** | 不会静默退化成"模型说完了就算完" |

配套还有两条：

- **工作区路径边界**：文件工具只能碰工作区内的路径，用 `resolve()` + `parents` 判断，
  `../` 和**符号链接穿透**都拦得住（只做字符串前缀比较两者都挡不住）
- **危险命令只提示、不做决定**：正则永远会漏（`find -delete`）也永远会误报，
  它只能提高人的注意力，不能变成权限系统

---

## 工程化与可验证性

### 测试 = 49 个 pytest 用例 + 8 个可独立运行的验收脚本

```
$ pytest
49 passed in 2.35s

$ xclaw check all
▶ graph：day1_check.py
▶ tools：tools_check.py
▶ memory：memory_check.py
...
✅ 全部 8 项验收通过
```

**两者共用同一份验证逻辑，只是入口不同**：直接跑脚本能看到每一步在确认什么（可读报告）；
跑 pytest 适合接 CI（看结果）。脚本会改全局状态，所以 `xclaw check` 让**每个脚本单独起进程**，
避免互相污染。

**全部不调用真实模型**，所以可以随时回归、不花钱。关键手法：

- **假模型**（`ScriptedLLM` / `FakeLLM`）：按剧本返回固定的 `tool_calls`，
  于是循环、预算、分支都能被断言
- **哨兵字符串**：证明"正文**没有**被提前加载"（渐进式加载的核心价值是"没做的事"）
- **调用计数**：证明重试时内环状态被正确重置（次数不对就说明有 bug）
- **符号链接 / 前缀陷阱**：证明工作区边界不是靠字符串比较糊弄的

> 这类"**证明否定命题**"的测试比"证明正向行为"更难写，也更能说明问题。

### 打包成真正的命令行工具

```toml
[project.scripts]
xclaw = "xclaw_cli:main"
```

`pip install -e .` 之后，`xclaw` 可以在**任意目录**运行，工作区就是当前目录。
退出码反映成败（`xclaw check all && git commit` 这种串联才有意义）。

---

## 实现顺序（12 天）

项目的价值不只在功能，也在**它的实现顺序**：每一步都建立在前一步的契约上。

| Day | 做了 | 关键决策 |
|---|---|---|
| 1 | 图编排框架 | 控制流变成数据（`Node.exec` 返回 `(action, payload)`） |
| 2 | 模型接入 | 返回**原始 message 字典**，为"零转换回填"埋伏笔 |
| 3 | 多轮对话 | 共享对话历史，消息序列必须合法 |
| 4 | 工具系统 | **三层拆分**：纯函数 / `Tool` 定义 / Executor |
| 5 | agent 主循环 | 循环是**图里的一个环**，不是 `while` |
| 6 | 记忆 | jsonl 落盘 + 长期记忆 + 按 token 触发压缩（含崩溃恢复） |
| 7 | MCP | 把"别处的动作"翻译成 `Tool`，**主循环零改动** |
| 8 | Skill | 渐进式披露：**常驻上下文降低 90%**（2393 → 243 字符） |
| 9 | 长任务 | "结束"由程序判定；顺带把解析器下沉到 `core/`（一次真实重构） |
| 10 | 操作确认 | 插一个图节点；`requires_approval` 默认 `True` |
| 11 | 工程化加固 | 工作区边界 / 原子写 / 压缩前归档 / 中断恢复 / 差异预览 |
| 12 | 收尾 | pytest（49 用例）+ 打包成 `xclaw` 命令 |

**三个阶段**：1–5 立骨架 → 6–9 加能力 → 10–12 加边界和退路。

---

## 项目结构

```
XClaw/
├── core/                    # 通用能力（不认识 tools）
│   ├── node.py              # 图编排：Node / Flow（92 行）
│   ├── llm.py               # 模型接入（两级配置：项目 .env 优先，~/.xclaw/.env 兜底）
│   ├── memory.py            # 记忆：落盘 / 长期记忆 / 压缩 / 归档 / 自愈
│   ├── frontmatter.py       # 元数据解析（Skill 与 Goal 共用）
│   ├── goal.py              # 长任务：目标 / 判据执行 / 重试证据
│   ├── approval.py          # 操作确认：ApprovalNode / 确认器 / 危险模式
│   └── workspace.py         # 工作区边界 + 原子写
├── tools/                   # 能力层
│   ├── executor.py          # ToolCall / ToolResult / ToolExecutor
│   ├── builtins/            # 8 个工具（在 tool_def.py 里登记）
│   ├── mcp/                 # server / client / adapter（远端工具 → 本地 Tool）
│   └── skills/              # loader（扫描 / 注入 / 按需加载）
├── examples/                # 6 个渐进式示例（每个只引入一个新概念）
├── skills/                  # 操作手册（frontmatter + 正文）
├── goals/                   # 长任务文件（目标 + 判据 + 预算）
├── tests/                   # pytest 用例（49 个）
├── pyproject.toml           # 打包 + [project.scripts] xclaw
├── xclaw_cli.py             # 命令行入口
└── *_check.py               # 8 个可独立运行的验收脚本
```

---

## 技术栈

- **语言**：Python 3.11+（类型注解 + dataclass）
- **模型接入**：OpenAI 兼容协议（`openai` SDK），支持任意兼容服务
- **工具协议**：手写 JSON Schema 声明参数，`to_llm_format()` 统一转换为模型协议
- **编排**：自研 `Node` / `Flow`（无第三方 agent 框架）
- **外部工具**：MCP（`mcp` 官方客户端 + `fastmcp` 服务端）
- **知识注入**：自研 Skill 加载器（YAML frontmatter + 渐进式披露）
- **测试**：pytest + 自研离线验收脚本
- **依赖**：`openai`、`python-dotenv`、`ddgs`、`mcp`、`fastmcp`

---

## 已知限制（诚实标注）

- **`bash` 不是沙箱**：`shell=True` 带来管道/重定向的便利，也意味着模型能执行任意命令。
  操作确认是**人为拦截**，不是隔离；用户点了 y 之后命令就是在你本机真实执行的。
- **危险命令靠字符串匹配**：认不出 `find -delete`、`python -c "shutil.rmtree(...)"`，
  也分不清"命令里的 rm"和"文本里的 rm"。它只用来提醒人，**不能当安全边界**。
- **工作区边界是"防手滑"，不是"防恶意"**：模型有 `bash`，`cat /etc/passwd` 照样能读。
- **长任务判据挡不住"奖励作弊"**：模型可以去改测试让判据变绿。
  目前只做到"用 `git status` 指出可疑改动并提示给人"，没有强制拦截。
- **测试以离线为主**：验证的是**控制逻辑**，不是"模型答得好不好"。
  提示词质量、工具选择准确率这类东西，离线测试证明不了。
- **包名是顶层通用名**（`core` / `tools` / `examples`），装进环境会占这三个名字。
  正式发布前应改成 `src/xclaw/` 布局。
- `shared` 是模块级全局字典，是刻意的教学简化；生产里应该用依赖注入。
- 8 个验收脚本与 pytest 共用同一份逻辑：一处维护，代价是测试文件的信息密度看起来不如手写用例高。

---

## 参考

- 项目结构与"渐进式示例"的组织方式，参考了 [Learn-OpenClaw](https://github.com/lasywolf/Learn-OpenClaw) 的教学思路
- 工具集的选择（read / write / edit / bash 为核心）参考了 pi-mono 关于最小 coding agent 的讨论
- 操作确认、压缩前归档等工程化做法，对比参考了 [ZipClaw](https://github.com/ZIPNO996/ZipClaw)
