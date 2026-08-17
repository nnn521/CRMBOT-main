<div data-theme-toc="true"> </div>

<!--
发布到 LINUX DO 或其他社区时，可按平台要求保留并确认下面这段。
如果不走开源推广流程，可以删除本注释块和下面的申明段。
-->

#### 本帖使用社区开源推广，符合推广要求。我申明并遵循社区要求的以下内容：

* **我的帖子已经打上 #开源推广 标签：** 是
* **我的开源项目完整开源，无未开源部分：** 是
* **我的开源项目已链接认可 LINUX DO 社区：** 是
* **我帖子内的项目介绍，AI 生成、润色内容部分已截图发出：** 是
* **以上选择我承诺是永久有效的，接受社区和佬友监督：** 是

*以下为项目介绍正文内容，AI 生成、润色内容已使用截图方式发出*

---

# 让 AI Agent 不再“忘规则”：我做了一个可路由的项目 Skill 架构

项目地址：[WoJiSama/skill-based-architecture](https://github.com/WoJiSama/skill-based-architecture)

这个项目不是又写了一份更长的提示词，也不是把 `AGENTS.md`、`CLAUDE.md`、`.cursor/rules/` 的内容换个地方复制一遍。

它想解决的是一个更具体的问题：

> 当项目越来越大，AI Agent 到底应该在什么时候读哪些规则、跟哪个流程、记录哪些新经验，并且在上游模板更新时不覆盖下游项目自己的个性化规则？

我把这套东西做成了一个 meta-skill：把散落的项目规则、工作流、踩坑经验，整理成一个可激活、可路由、可验证、可持续维护的项目 skill。

---

## 阅读路径

- **只想知道这个项目解决什么问题**：读第一章到第三章。
- **想在自己项目里用起来**：读第四章、第八章、第九章。
- **想理解为什么这样设计**：按顺序读完整篇。

全文核心是三句话：

1. **结构服务于内容。** 小 skill 不需要上全套架构，内容真的复杂了再拆。
2. **激活优于存储。** 规则写进文件不等于生效，Agent 正常任务路径上能读到才算生效。
3. **下游知识优先于上游模板。** 上游可以升级结构，但不能粗暴覆盖下游项目自己沉淀的规则。

---

## 一、问题不是 Agent 不读规则，而是不知道该读哪条规则

很多项目一开始只有一个入口文件：

```text
AGENTS.md
CLAUDE.md
.cursor/rules/workflow.mdc
```

刚开始很好用，因为规则少，Agent 每次读一遍也不贵。

但项目跑久之后，常见情况会变成这样：

```text
AGENTS.md                # 写了一部分规则
CLAUDE.md                # 又复制了一份，略有不同
CODEX.md                 # 再复制一份
.cursor/rules/*.mdc      # Cursor 还有一份
README.md                # 某些约定又埋在这里
docs/*.md                # 还有历史记录、流程说明、坑点
```

表面上是“规则很多”，实际问题是：

| 现象 | 后果 |
|---|---|
| 多个入口文件写了重复路由 | 改一处漏三处，规则开始漂移 |
| `SKILL.md` 越写越长 | Agent 每次任务读整本书，token 浪费且容易漏重点 |
| 坑点只放在 `references/` | 下次修同类 bug 时，Agent 根本不会自然读到 |
| description 写得太窄 | 用户说“这个接口报错了”，但 skill 只写 “fix bug”，可能不触发 |
| description 写得太宽 | 什么任务都触发，后面还要再猜真正意图 |
| 上游模板更新 | 下游项目自己慢慢写出来的规则不能被覆盖 |

所以这个项目的核心不是“让 Agent 多读点文档”，而是让 Agent **少读、读准、读对路径**。

---

## 二、先承认：单文件 skill 很多时候就是最优解

我不认为所有项目一上来都应该拆成 `rules/`、`workflows/`、`references/`。

如果一个 skill 只有几条稳定原则，单个 `SKILL.md` 就够了。参考 [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) 这类项目，核心价值不是目录复杂，而是规则写得克制、具体、可检查。

真正需要升级结构的信号是：

- 同一个 `SKILL.md` 开始超过 100-150 行。
- 内容自然分成了 3 个以上主题。
- 不同任务需要读不同规则。
- 同样的坑第二次出现，但没有地方沉淀。
- 多个工具入口文件开始复制同一张路由表。

这时候才应该从“单文件”升级到“文件夹化 skill”。

---

## 三、文件夹化之后，每类内容只做一件事

目标结构是这样：

```text
skills/<project>/
├── SKILL.md          # 入口：激活后导航，不写百科
├── routing.yaml      # 路由单一事实源
├── rules/            # 稳定约束：什么必须一直成立
├── workflows/        # 步骤流程：做一件事的顺序
├── references/       # 背景、架构、坑点、索引
└── docs/             # 可选：报告、提示词、对外材料
```

文件边界很简单：

| 内容类型 | 放哪里 |
|---|---|
| “必须 / 禁止 / 始终” | `rules/` |
| “第一步 / 第二步 / 最后检查” | `workflows/` |
| “为什么这样 / 这个坑怎么来的” | `references/` |
| “对外说明 / 报告 / 提示词” | `docs/` |

这个拆分不是为了看起来工程化，而是为了让 Agent 在不同任务里只加载最小必要上下文。

---

## 四、`routing.yaml`：路由只维护一份

我后来发现长期维护最大的风险，不是某条规则写错，而是**同一份路由在多个地方重复维护**。

所以现在模板里把路由集中到 `routing.yaml`：

```yaml
tasks:
  - id: fix-bug
    labels:
      en: Fix bug
      zh: 修复 bug / 排查异常
    required_reads:
      - rules/project-rules.md
      - rules/coding-standards.md
    workflow: workflows/fix-bug.md
    trigger_examples:
      - "这个接口报错了"
      - "测试挂了"
      - "fix this failing test"
```

然后由脚本生成或校验：

- `SKILL.md` 里的 Always Read / Common Tasks
- `AGENTS.md`、`CLAUDE.md`、`CODEX.md`、`GEMINI.md` 的薄壳入口
- `.cursor/rules/workflow.mdc`
- `.cursor/skills/<name>/SKILL.md`
- 路由引用的 workflow 文件是否存在
- description 和路由是否明显冲突

这样新增一个任务时，不再需要手动改五六个入口文件。

---

## 五、description 只负责“激活”，不负责“路由”

很多 skill 的 description 会陷入两个极端。

第一种是太窄：

```yaml
description: Fix bug
```

用户说“这个接口报错了”“页面白屏了”“测试挂了”，不一定能触发。

第二种是太宽：

```yaml
description: Helps with development
```

它可能什么任务都触发，后面路由压力反而变大。

我的处理方式是：**description 写领域边界和真实用户表达，任务级细分交给 `routing.yaml`。**

例如：

```yaml
description: >
  Use this skill when the user asks to organize project rules, clean up
  scattered agent docs, improve skill routing, increase description trigger
  accuracy, or maintain templates and thin shells.
  Activate when task routes, trigger_examples, SKILL.md, AGENTS.md,
  CLAUDE.md, Cursor rules, validation scripts, or upstream update workflows
  need drift-resistant maintenance.
```

它不需要列出每一个 workflow。它只需要回答一个问题：

> 这个用户请求，属于这个 skill 的领域吗？

激活之后，才由 `routing.yaml` 继续判断是修 bug、改模板、更新 reference、优化 description，还是从上游升级。

---

## 六、薄壳：让不同工具都能找到同一个规则系统

不同工具读取入口不同：

| 工具 / Harness | 常见入口 |
|---|---|
| Claude Code | `CLAUDE.md` |
| Codex / AGENTS.md 工具 | `AGENTS.md`、`CODEX.md` |
| Cursor | `.cursor/rules/*.mdc`、`.cursor/skills/<name>/SKILL.md` |
| Gemini | `GEMINI.md` |

如果每个入口都复制完整规则，很快就会漂移。

所以这个项目采用“薄壳”：

```md
## Quick Routing

Task routes live in `skills/<name>/routing.yaml`.

For every new task:
1. Read `skills/<name>/SKILL.md`.
2. Read `skills/<name>/routing.yaml`.
3. Match by `labels`, `trigger_examples`, and task intent.
4. Read only that route's `required_reads`, then follow its `workflow`.
5. If no route matches, use the `other` route.
```

薄壳只回答“从哪里开始、怎么路由”，规则正文仍然只放在 skill 目录里。

这样做还有一个额外好处：长会话压缩之后，结构化的 Quick Routing 比普通自然语言更容易保留下来。Agent 即使忘了前文，也还能重新找到路由入口。

---

## 七、AAR：让 skill 自己长经验

很多项目的规则文档只会增加，不会筛选。

这个项目把任务结束定义成一个闭环：

1. 主体任务完成并验证。
2. 做 30 秒 AAR 扫描。
3. 如果发现新规则、新坑、过时规则，再决定是否记录。

AAR 只问四个问题：

- 这次有没有发现新的可复用模式？
- 有没有遇到不提前知道就会浪费很多时间的坑？
- 有没有因为缺少规则走弯路？
- 有没有发现旧规则已经不准确？

但不是所有东西都记录。录入前要过门槛：

| 判断 | 说明 |
|---|---|
| 可重复 | 未来还可能再次遇到 |
| 代价高 | 不知道会明显浪费时间或造成错误 |
| 代码里看不出 | 只读代码不容易发现 |

通常至少满足 2 条才值得写进 skill。

更重要的是：写进 `references/` 还不够。高代价坑点必须出现在正常任务路径上，比如 workflow 的完成检查、SKILL.md 的 Known Gotchas，或者某条 route 的 required reads。

否则它只是“存起来了”，不是“会被激活”。

---

## 八、模板：复制骨架，不预制项目内容

以前让 Agent 临场生成脚手架，很容易漏段：

- 忘了写 Auto-Triggers。
- 忘了 Cursor 注册入口。
- 忘了 Red Flags。
- `SKILL.md` 和薄壳路由不一致。
- description 只剩模板废话。

所以这个项目把结构放进 `templates/`：

```text
templates/
├── skill/                    # 复制为 skills/<name>/
├── shells/                   # AGENTS.md / CLAUDE.md / CODEX.md / GEMINI.md
├── hooks/                    # 可选 SessionStart / PreToolUse hook
├── protocol-blocks/          # AAR、Red Flags、subagent contract 等
└── ANTI-TEMPLATES.md         # 明确哪些东西禁止预制
```

这里有一条边界：

> 结构可以预制，内容禁止预制。

比如 `routing.yaml` 的字段结构可以预制，但具体任务、规则、坑点必须来自下游项目真实情况。

判断一个东西能不能放进模板，我用这个问题：

> 一个 Go 后端服务和一个 React 动画站，都会同意这块默认内容吗？

如果不会，就不应该预制。

---

## 九、验证脚本：把容易漏的东西交给机器检查

人很难每次手动检查这些事情：

- `routing.yaml` 引用的 workflow 是否存在。
- `SKILL.md` 和 Cursor 注册入口的 description 是否一致。
- 薄壳有没有丢 routing bootstrap。
- 是否还有 `<!-- FILL: -->` 没填。
- `SKILL.md` 是否过长。
- description 是否太宽或太窄。

所以模板里带了脚本：

```bash
bash skills/<name>/scripts/smoke-test.sh <name>
bash skills/<name>/scripts/sync-routing.sh <name> --check
bash skills/<name>/scripts/check-description-routing.sh <name>
bash skills/<name>/scripts/test-trigger.sh <name>
```

脚本不能替代理解，但能抓住大量“忘了改 / 改漏了 / 多处漂移”的问题。

---

## 十、上游更新：不能覆盖下游项目自己的规则

这是我后来遇到的一个更实际的问题。

这个仓库是上游模板项目，会持续更新；但下游项目已经有自己慢慢沉淀出来的规则、流程、坑点。

如果上游升级时直接覆盖：

```text
cp -R upstream/templates/skill/. skills/<name>/
```

那就会把下游项目自己的知识冲掉。这是不靠谱的。

所以现在模板里加入了 `update-upstream` 工作流。下游用户不需要自己 diff，也不需要维护额外系统文件。他只要对 Agent 说类似这样的话：

> 上游 skill-based-architecture 更新了，帮我更新一下。

Agent 应该自己去做：

1. 拉取或克隆最新上游仓库。
2. 只从上游读取升级说明和模板变更。
3. 比较本地下游文件和上游模板结构。
4. 只补结构性变化，不盲目覆盖项目规则。
5. 对冲突区域给出人工可读的解释。
6. 运行 smoke test、routing check、description check。

核心原则是：

> 上游负责结构演进，下游保留项目知识。

---

## 十一、什么时候不该用这个项目

这套架构不是越早上越好。

下面这些情况，一个普通入口文件就够：

- 项目很短期，规则不会长期维护。
- 所有规则加起来不到 50 行。
- 只用一个 AI 工具，不需要跨 harness。
- 没有反复任务，也没有高代价踩坑经验。

这时候强行上 `rules/`、`workflows/`、`references/` 反而是过度设计。

我更推荐按复杂度逐步升级：

```text
单文件 SKILL.md
  ↓
Folder-light: SKILL.md + rules/
  ↓
Full: routing.yaml + workflows/ + references/ + thin shells + validation scripts
```

结构只在内容真的需要时增长。

---

## 十二、怎么开始用

第一步，把这个项目拉到本地，让 Agent 能读到：

```bash
# Cursor 用户级 skill
git clone https://github.com/WoJiSama/skill-based-architecture.git \
  ~/.cursor/skills/skill-based-architecture

# Cursor 项目级 skill
git clone https://github.com/WoJiSama/skill-based-architecture.git \
  .cursor/skills/skill-based-architecture

# 通用项目内安装
git clone https://github.com/WoJiSama/skill-based-architecture.git \
  skills/skill-based-architecture
```

第二步，在目标项目里触发：

```text
Use skill-based-architecture to refactor the project rules
```

或者中文也可以：

```text
整理项目规则，把它迁移成 skill-based architecture。
```

Agent 激活后，会按 `WORKFLOW.md` 的 Quick Start：

1. 审计现有规则来源。
2. 从 `templates/` 复制脚手架。
3. 填写项目自己的 `rules/`、`workflows/`、`references/`。
4. 创建各工具薄壳入口。
5. 跑脚本验证结构、路由和 description。

---

## 十三、这个项目最终提供了什么

它提供的不是某一条神奇 prompt，而是一套项目规则系统的工程结构：

| 能力 | 解决的问题 |
|---|---|
| `SKILL.md` 入口 | 激活后快速导航，不把所有内容塞进入口 |
| `routing.yaml` | 路由单一事实源，避免多入口重复维护 |
| `rules/` | 存稳定约束 |
| `workflows/` | 存可重复步骤 |
| `references/` | 存架构背景和高代价坑点 |
| 薄壳入口 | 兼容 Cursor、Claude Code、Codex、Gemini 等工具 |
| AAR / Task Closure | 任务结束时捕获新经验和过时规则 |
| templates | 复制稳定结构，不让 Agent 临场生成漏段 |
| validation scripts | 自动检查占位符、路由、description、薄壳漂移 |
| update-upstream workflow | 上游结构可升级，下游项目知识不被覆盖 |

一句话总结：

> 它把“写给 AI Agent 的散乱提示词”，升级成了一个可路由、可验证、可持续维护的项目规则系统。

---

## 项目地址

[https://github.com/WoJiSama/skill-based-architecture](https://github.com/WoJiSama/skill-based-architecture)

欢迎一起提 issue 或 PR。这个项目本身也在用自己的规则维护自己，所以后续会继续围绕 description 命中率、路由漂移、下游升级、AAR 质量继续迭代。

## Star History

<a href="https://www.star-history.com/?repos=WoJiSama%2Fskill-based-architecture&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=WoJiSama/skill-based-architecture&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=WoJiSama/skill-based-architecture&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=WoJiSama/skill-based-architecture&type=date&legend=top-left" />
 </picture>
</a>
