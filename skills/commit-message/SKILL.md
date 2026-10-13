---
name: commit-message
description: 为本次改动生成提交信息（commit message）。当用户要求写 commit、提交信息、提交说明，或要把改动提交到 git 时使用。
---

# 提交信息规范

## 格式

```
<type>(<scope>): <一句话说明>

<可选：为什么这么改，而不是改了什么>
```

## type 取值

| type | 用在什么时候 |
|---|---|
| `feat` | 新增功能 |
| `fix` | 修 bug |
| `refactor` | 不改行为的重构 |
| `docs` | 只改文档 |
| `test` | 只改测试 |
| `chore` | 依赖、配置、构建 |

## scope

用模块名，取自项目的顶层目录：`core` / `tools` / `examples` / `skills` / `mcp`。

## 写法要点

1. **标题用中文，不加句号，不超过 50 字**
2. 说**为什么**，不要复述 diff（`git log` 已经能看到改了什么）
3. 一次提交只做一件事；如果发现混了两件事，提醒用户拆开

## 生成步骤

1. 先用 `bash` 跑 `git status --short` 看有哪些文件动了
2. 再用 `bash` 跑 `git diff --stat` 看改动规模
3. 需要细节时用 `git diff <文件>` 看具体内容
4. 按上面的格式给出**一条**提交信息，不要给三个选项让用户挑

## 示例

```
feat(skills): 按需加载的操作手册（渐进式披露 + 防重复加载）

手册正文不再常驻 prompt，改为模型主动调用 skill 工具时加载，
避免手册数量增长后 prompt 开销线性上升。
```
