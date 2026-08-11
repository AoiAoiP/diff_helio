# PaperCraft — 论文创作全流程工作台使用指南

> 版本: 1.0 | 日期: 2026-08-11 | 适用于: Claude Code

---

## 目录

1. [概览](#概览)
2. [模块一：文献管理](#模块一文献管理)
3. [模块二：论文架构整理](#模块二论文架构整理)
4. [模块三：论文写作](#模块三论文写作)
5. [模块四：实验优化](#模块四实验优化)
6. [推荐全流程](#推荐全流程)
7. [命令速查表](#命令速查表)
8. [工具清单与安装](#工具清单与安装)

---

## 概览

PaperCraft 将论文写作拆解为四个模块，每个模块由独立的 Claude Code Skill 执行：

```
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│  1. 文献管理  │ → │ 2. 论文架构   │ → │   3. 论文写作      │ ← │ 4. 实验优化  │
│  ref/        │    │  ARS: plan   │    │  RPW + ARS: full  │    │ autoresearch │
│  ARS: lit    │    │  ARS: outline│    │  ARS: reviewer    │    │              │
└──────────────┘    └──────────────┘    └──────────────────┘    └──────────────┘
```

### 触发方式

在 Claude Code 会话中说出以下任意关键词即可激活：

> **触发词**: 写论文、论文工作流、papercraft、paper writing、论文写作、文献检索、打磨大纲

或直接运行对应命令（参见[命令速查表](#命令速查表)）。

---

## 模块一：文献管理

**目标**: 建立检索策略 → 真检索 → Zotero 管理 → 本地链接 → 引用验证

### 工作流

```
Step 1          Step 2              Step 3            Step 4
Claude 生成     用户用               PDF 存入          ARS 链接
检索策略    →   Undermind.ai 等  →   Zotero +     →   本地文献库
                AI 工具真检索       建立 Collection    写入论文
```

### 操作指南

#### Step 1: 生成检索策略

```
/ars-lit-review "你的研究主题"
```

或直接告诉 Claude：
> 帮我为"重力作用下定日镜面型的可微优化"生成系统的文献检索策略，包含关键词、数据库和筛选标准

Claude 将产出：
- 检索关键词（主关键词 + 同义词 + MeSH terms）
- 推荐数据库（Scopus / Web of Science / Semantic Scholar）
- 筛选标准（时间范围、文献类型、排除条件）
- PRISMA 流程图框架

策略文件保存到 `ref/search_strategies/`。

#### Step 2: 执行真检索

**工具推荐**:
- [Undermind.ai](https://undermind.ai) — AI 学术搜索引擎，适合系统性综述
- [Semantic Scholar](https://www.semanticscholar.org) — 免费 API，ARS 内置验证
- [Google Scholar](https://scholar.google.com) — 覆盖面广
- Web of Science / Scopus — 机构订阅

> **注意**: 不要用 Claude 直接搜文献（会产生幻觉引用）。检索必须由用户用真实学术搜索工具执行。

#### Step 3: Zotero 管理

1. 将命中的 PDF 导入 Zotero
2. 建立 Collection（按主题/方法分类）
3. 确保每篇文献有完整元数据（作者 / 年份 / Title / DOI / Abstract）

#### Step 4: 导出到 ref/

**方式 A — Zotero 手动导出**:
1. Zotero → 右键 Collection → Export Collection
2. 格式选择 **CSL JSON** 或 **Better BibLaTeX**
3. 保存到 `ref/corpus/`

**方式 B — ARS Zotero 适配器**（需 Zotero 本地 API 运行）:
```bash
python academic-research-skills/scripts/adapters/zotero.py \
  --output ref/corpus/literature_corpus.json
```

**验证导出**:
```bash
python academic-research-skills/scripts/check_literature_corpus_schema.py ref/corpus/
```

#### 链接到写作

```
"加载 ref/corpus/ 中的文献库，帮我撰写 Related Work 部分"
```

ARS 的 `literature_corpus[]` Schema 会自动：
- 读取所有文献条目的元数据
- 通过 CrossRef / Semantic Scholar / OpenAlex / arXiv 四索引交叉验证引用存在性
- 在写作时自动标注引用锚点（`<!--ref:slug-->` + `<!--anchor:page:...-->`）
- 在 Stage 4.5 终审闸门校验主张-引用-致性

### ref/ 目录结构

```
ref/
├── README.md                  # 模块说明
├── search_strategies/         # 检索策略记录
├── corpus/                    # 文献条目（CSL-JSON / BibTeX）
├── notes/                     # 论文阅读笔记
└── adapters/                  # Zotero 适配脚本
```

---

## 模块二：论文架构整理

**目标**: 打磨 idea、规划章节、精炼贡献陈述

### 三个核心命令

| 命令 | 功能 | 何时用 |
|------|------|--------|
| `/ars-plan` | 苏格拉底式章节规划 | idea 尚模糊，需要对话引导 |
| `/ars-outline` | 详细大纲生成 | 结构已明确，需要逐节细化 |
| `/ars-3w` | What/Why/Why Now 精炼 | 投稿前打磨故事线 |

### 典型流程

```
/ars-plan
  → 苏格拉底对话（3-5 轮）
  → 澄清研究问题（RQ Brief）
  → 确定贡献维度
  → 产出章节蓝图

/ars-outline
  → 逐节填写：
      §1 Introduction（动机 + 贡献）
      §2 Related Work（五条脉络定位）
      §3 System Model（物理系统 + 目标）
      §4 Method（框架 + 工具链）
      §5 Theoretical Analysis（"为什么有效"）
      §6 Experiments（实验设计 + 结果）
      §7 Discussion / Conclusion
  → 实验方案与所需图表清单

/ars-3w
  → What: 本文做了什么
  → Why: 为什么之前没人做
  → Why Now: 为什么现在时机成熟
  → 精炼为 3 句 elevator pitch
```

### 使用示例

```
# 对话式规划
/ars-plan

# 直接描述论文 idea
"我正在写一篇关于重力作用下定日镜面型可微优化的论文，目标期刊 AEI。
核心贡献是发现了重力→法线耦合修复后，35 螺栓支撑布局存在结构性
重力地板，并通过 margin 优化将 300m 四面镜 S95 降低 26.7%。
帮我规划论文架构。"

# 精炼贡献陈述
/ars-3w
```

---

## 模块三：论文写作

**目标**: 逐段撰写 → 风格校准 → 自审 → 同行评审 → 修订 → 终稿

### 工具分工

| 工具 | 角色 |
|------|------|
| **research-paper-writing** (RPW) | 逐段写作指导 + 段落清晰度检查 + 对抗性自审 |
| **academic-paper** (ARS) | 全流程调度 + 引用锚点 + 主张-证据对齐 |
| **academic-paper-reviewer** (ARS) | 5 位审稿人 + 魔鬼代言人 + 编辑决定信 |

### 方式 A — 全流程一键执行

```
/ars-full
```

自动执行 10 阶段 pipeline：

```
Stage 1:  deep-research（文献背景扫描）
Stage 2:  outline + draft（大纲 + 初稿，调用 RPW 风格指南）
    ├─ 12 个写作 Agent 并行：引言/相关工作/方法/实验/结论
    ├─ 风格校准（从历史写作中学习个人风格）
    ├─ 写作质量检查（识别机器生成模式）
    └─ 每段标注引用锚点（<!--ref:slug--> + <!--anchor:-->）
Stage 2.5: 学术诚信闸门 🔴
    ├─ 7 类 AI 研究失败模式检查（Lu 2026, Nature）
    ├─ 引用存在性四索引验证（SS / OpenAlex / Crossref / arXiv）
    ├─ 主张-证据对齐检查
    └─ VLM 图表忠实度验证
Stage 3:  论文评审（5 位审稿人 + 魔鬼代言人）
Stage 4:  按审稿意见修订
Stage 4.5: 终审闸门 🔴
Stage 5:  格式转换（LaTeX / DOCX）
Stage 6:  AI Self-Reflection Report
```

### 方式 B — 分步精细控制

#### B1: 逐段写作（使用 RPW）

```
# 写 Abstract
"用 research-paper-writing skill 写 Abstract，控制在 200 词以内"

# 写 Introduction（最重要的部分）
"用 RPW 写 Introduction：
- 第 1 段：CSP 领域背景 + 可微优化在定日镜中的现状
- 第 2 段：现有方法的局限（理想曲面无工程参考价值、重力光学隐身）
- 第 3 段：本文贡献（重力→法线耦合修复 + 结构性地板 + margin 优化 −26.7%）
- 每段第一句必须是该段的核心信息"

# 写 Related Work
"加载 ref/corpus/ 中所有文献，用 RPW 写 Related Work，
按五条脉络组织：可微渲染 / 代理模型 / 重力补偿 / 结构优化 / 太阳场光学"

# 写 Method
"用 RPW 写 Method 部分，包含：
- TPS 代理模型公式
- 重力三平面耦合机制
- 可微光线追踪管线
- 损失函数与正则化体系
确保所有公式和变量定义清晰"

# 写 Experiments
"用 RPW 写 Experiments 部分，包含：
- 实验设置（12.84×9.45m, 35 螺栓 7×5, 300m NEWS）
- 基线对比（B_naive vs B_comp vs 端到端最优 vs B*）
- 消融实验（9 组：参数化 × 锚定 × 行程 × 弯曲能 × init）
- Phase 5 margin 优化（m*≈0.05, 红利 −26.7%）
- FEA 验证（Proxy vs ANSYS, R²>0.95）"
```

#### B2: 风格检查（RPW 逆向大纲）

```
# 检查段落流畅度
"用 RPW 检查 Introduction 每一段的清晰度：
- 每段是否只有一个核心信息？
- 首句是否陈述了该段要做什么？
- 句间是否有明确的因果/对比/递进关系？"

# 逆向大纲检查
"对 §1 Introduction 做逆向大纲：
1. 写出该节的中心论点
2. 写出每段的主题句
3. 检查主题句→中心论点、证据→主题句的映射
4. 标记无法干净映射的段落，建议修改或删除"
```

#### B3: 同行评审

```
# 完整评审
/ars-reviewer

# 方法论专项评审
/ars-reviewer --mode methodology-focus
```

评审产出：
- 5 位审稿人的详细意见（含评分 0-100）
- 魔鬼代言人的对抗性审查
- 编辑决定信（Accept / Minor Revision / Major Revision / Reject）
- 修订路线图（Revision Roadmap）

#### B4: 修订与终审

```
# 按审稿意见修订
/ars-revision

# 审阅 Rebuttal
/ars-rebuttal-audit

# 引用完整性终检
/ars-citation-check

# 格式转换
/ars-format-convert --format latex
```

### RPW 逐 Section 参考指南

RPW 内置以下 section-specific 写作指南（位于 `.claude/skills/research-paper-writing/references/`）：

| 文件 | 适用 Section |
|------|-------------|
| `abstract.md` | 摘要：四句结构（背景/问题/方法/结果） |
| `introduction.md` | 引言：倒三角结构 + 贡献列表 |
| `related-work.md` | 相关工作：五条脉络 + 本文定位 |
| `method.md` | 方法：技术细节完整性 + 可复现性 |
| `experiments.md` | 实验：设置/基线/消融/可视化 |
| `conclusion.md` | 结论：贡献回顾 + 局限性 + 未来工作 |
| `paper-review.md` | 自审清单：5 维度 rejection risk 检测 |

---

## 模块四：实验优化

**目标**: 端到端指标驱动的自主实验——修改参数 → 跑实验 → 验证 → 保留/丢弃 → 循环

### 三种模式

| 模式 | 用途 | 示例 |
|------|------|------|
| **Loop** | 指标驱动自主优化 | `/autoresearch 将 North 300m S95 降低到 50 m² 以下` |
| **Debug** | 假设驱动 Bug 调查 | `/autoresearch 调试 λ_energy=0 时能量溢出问题` |
| **Fix** | 错误计数归零 | `/autoresearch 修复所有编译警告` |

### Loop 模式详解

```
/autoresearch <目标>

→ Claude 扫描项目结构
→ 交互向导（1-3 轮）确认:
    - 作用范围（哪些配置/参数文件？）
    - 指标（S95 值 / 用何命令提取？）
    - 验证命令（./bezier_opt.exe configs/...）
    - 守护命令（回归测试？）
    - 迭代上限
→ 用户说 "go"
→ 自主循环:
    Read → Ideate → Modify → Commit → Verify → Guard → Decide → Log → Repeat
    每轮: 一次聚焦修改 → 机械验证 → 保留/丢弃 → 记录到 results.tsv
→ 卡住时自动升级:
    3 次丢弃 → 精炼策略
    5 次未保留 → 转换方法
    2 次转换无改善 → 网络搜索
    3 次转换无改善 → 停止并报告
```

### 适合本项目（定日镜优化）的用法

```
# 单镜优化
/autoresearch 优化 North 300m 的螺栓行程配置，在不触发能量惩罚的前提下
将年均 S95 降到最低，使用 configs/_fw_tanh_a0.json 作为基线

# 超参扫描
/autoresearch 扫描 λ_anchor 在 [0, 1e-5, 1e-4, 1e-3, 1e-2] 下 300m NEWS
四镜的 S95 变化，给出最优 λ 推荐

# 布局优化
/autoresearch 在 m=0.05 margin 下扫描 5×3 / 7×5 / 9×7 / 11×9 四种密度
的 300m NEWS 四镜 S95，确定密度甜点
```

### 结果追踪

```
autoresearch-results/
├── results.tsv       # 每次迭代的日志
├── state.json        # 当前运行状态
└── lessons.md        # 跨运行学习笔记
```

### 状态管理

```bash
# 从 claude-autoresearch/scripts/ 目录运行
PYTHONPATH=claude-autoresearch/scripts python3 claude-autoresearch/scripts/autoresearch_state.py check    # 检查活跃运行
PYTHONPATH=claude-autoresearch/scripts python3 claude-autoresearch/scripts/autoresearch_state.py summary  # 运行摘要
PYTHONPATH=claude-autoresearch/scripts python3 claude-autoresearch/scripts/autoresearch_state.py pause    # 暂停
PYTHONPATH=claude-autoresearch/scripts python3 claude-autoresearch/scripts/autoresearch_state.py resume   # 恢复
PYTHONPATH=claude-autoresearch/scripts python3 claude-autoresearch/scripts/autoresearch_state.py complete  # 完成
```

---

## 推荐全流程

### 启动阶段（1–2 天）

```
Day 1
  1. /ars-plan                              # 规划论文架构（1-2h）
  2. /ars-lit-review "your topic"           # 生成检索策略（30min）
  3. [手动] Undermind.ai 检索               # 真检索（2-3h）

Day 2
  4. [手动] PDF → Zotero → 整理 Collection   # 文献管理（1h）
  5. Zotero → Export → ref/corpus/           # 导出到本地（10min）
  6. "加载 ref/corpus/，做文献综述"           # Claude 读取 + 验证引用（30min）
```

### 写作阶段（3–5 天）

```
Day 3
  7. /ars-outline                            # 详细大纲 + 实验方案（1h）
  8. 用 RPW 写 §1 Introduction               # 最重要的部分（2-3h）
  9. 用 RPW 写 §3 System Model              # 已有公式基础（1-2h）

Day 4
  10. 加载 ref/corpus/，用 RPW 写 §2 Related Work  # 五条脉络（2h）
  11. 用 RPW 写 §4 Method                    # 管线说明（2h）
  12. /autoresearch 补跑缺失实验              # 边写边补（后台）

Day 5
  13. 用 RPW 写 §5-7（Analysis / Experiments / Conclusion）
  14. /ars-reviewer                          # 首次同行评审
  15. /ars-revision                          # 按意见修订
```

### 终审阶段（1–2 天）

```
Day 6
  16. /ars-3w                                # 精炼贡献陈述
  17. RPW paper-review self-audit            # 对抗性自审
  18. /ars-citation-check                    # 引用完整性终检

Day 7
  19. /ars-reviewer                          # 最终同行评审
  20. /ars-revision                          # 最后修订
  21. /ars-format-convert --format latex     # 输出投稿格式
  22. /ars-disclosure                        # AI 使用声明
```

---

## 命令速查表

### ARS (Academic Research Skills) — 16 个命令

| 命令 | 模块 | 功能 | Token 估算 |
|------|:---:|------|:---:|
| `/ars-plan` | 架构 | 苏格拉底式章节规划 | ~70 |
| `/ars-outline` | 架构 | 详细大纲生成 | ~70 |
| `/ars-3w` | 架构 | What/Why/Why Now 精炼 | ~110 |
| `/ars-full` | 写作 | 全流程一键执行 | ~12.5k |
| `/ars-lit-review` | 文献 | 文献综述 + 检索策略 | ~110 |
| `/ars-abstract` | 写作 | 单独打磨摘要 | ~90 |
| `/ars-reviewer` | 写作 | 多视角同行评审（5 审稿人） | ~120 |
| `/ars-revision` | 写作 | 按审稿意见修订 | ~70 |
| `/ars-revision-coach` | 写作 | 修订指导 | ~220 |
| `/ars-rebuttal-audit` | 写作 | Rebuttal 审阅 | ~160 |
| `/ars-citation-check` | 写作 | 引用完整性验证 | ~80 |
| `/ars-format-convert` | 写作 | LaTeX/DOCX 格式转换 | ~80 |
| `/ars-disclosure` | 写作 | AI 使用声明 | ~200 |
| `/ars-mark-read` | 文献 | 标记文献已读 | ~500 |
| `/ars-cache-invalidate` | 文献 | 清除验证缓存 | ~440 |
| `/ars-unmark-read` | 文献 | 取消已读标记 | ~290 |

### RPW (Research Paper Writing) — 按 section 触发

| 触发提示 | 功能 |
|---------|------|
| "用 RPW 写/改 Abstract" | 四句结构摘要 |
| "用 RPW 写/改 Introduction" | 倒三角 + 贡献列表 |
| "用 RPW 写/改 Related Work" | 五条脉络定位 |
| "用 RPW 写/改 Method" | 技术细节 + 可复现性 |
| "用 RPW 写/改 Experiments" | 设置/基线/消融/可视化 |
| "用 RPW 写/改 Conclusion" | 贡献回顾 + 局限性 |
| "用 RPW 做逆向大纲检查 [section]" | 段落→论点映射 |
| "用 RPW 做 paper review" | 5 维度 rejection 自审 |
| "check flow of this paragraph" | 段落清晰度测试 |

### Autoresearch — 1 个命令

| 命令 | 功能 |
|------|------|
| `/autoresearch <目标>` | 指标驱动自主实验循环 |

---

## 工具清单与安装

### 已安装

| 工具 | 版本 | 位置 | 大小 |
|------|------|------|------|
| **academic-research-skills** | v3.19.0 | Plugin (user scope) | 20 skills + 16 commands + 3 agents |
| **research-paper-writing** | - | `.claude/skills/research-paper-writing/` | 1 skill + 8 references |
| **claude-autoresearch** | v0.1.0 | Plugin (user scope) | 1 command + 1 skill |
| **PaperCraft** | 1.0 | `.claude/skills/papercraft/SKILL.md` | 总调度 |
| **ref/** | - | `ref/` | 文献管理模块 |

### 安装命令回顾

```bash
# 1. ARS（一键安装）
/plugin marketplace add Imbad0202/academic-research-skills
/plugin install academic-research-skills

# 2. Research Paper Writing（手动安装）
git clone git@github.com:Master-cai/Research-Paper-Writing-Skills.git
mkdir -p .claude/skills
cp -R Research-Paper-Writing-Skills/research-paper-writing .claude/skills/

# 3. Autoresearch（本地 marketplace 安装）
git clone git@github.com:yin52133/claude-autoresearch.git
# 创建 .claude-plugin/marketplace.json → claude plugin marketplace add → install

# 4. PaperCraft（已内置）
# .claude/skills/papercraft/SKILL.md — 项目内自动加载
```

### Token 预算

| 组件 | Always-on | On-invoke |
|------|:---:|:---:|
| ARS (全部) | ~1,385 tok | — |
| ARS academic-paper | — | ~11.5k |
| ARS academic-paper-reviewer | — | ~8.6k |
| ARS academic-pipeline | — | ~12.5k |
| ARS deep-research | — | ~9k |
| RPW | < 100 | ~3k |
| Autoresearch | ~80 | ~2.8k |
| PaperCraft | < 50 | — |
| **总计（always-on）** | **~1,500 tok** | — |

> 一篇 15k 字的完整论文跑完 pipeline 估算约 $4–6（ARS 官方数据，基于 Opus 定价）。

---

## 与现有项目集成

### 启动新版论文

```
# 在 bezier_opt 项目根目录启动 Claude Code，然后：
/ars-plan
```

### 从现有 draft.md 继续

```
"加载 docs/draft.md，这已经是一份中文初稿（§1-§7 完整草稿）。
用 RPW 逐节审查和重写，重点打磨：
1. §1 Introduction 的贡献陈述
2. §2 Related Work 的五条脉络定位
3. §5 理论分析部分的重力补偿论证
完成后运行 /ars-reviewer 做同行评审"
```

### 实验结果自动更新到论文

```
# 1. 跑实验
/autoresearch 扫描 margin 0.02-0.08 下 300m NEWS 四镜 S95，找出最优 margin

# 2. 实验完成后告诉 Claude
"把 autoresearch 的最新结果更新到 docs/draft.md 的 §6 Experiments 部分"
```

---

## 参考文献

- Lu et al. (2026). The AI Scientist. *Nature* 651:914-919.
- Zhao et al. (2026). Hallucinated citations in LLM-generated academic papers. arXiv:2605.07723.
- Ren et al. (2026). Self-Improvements in Modern Agentic Systems: A Survey. arXiv:2607.13104.
- Song et al. (2026). PaperOrchestra. arXiv:2604.05018.
- Kong et al. (2026). AI for Auto-Research: Roadmap & User Guide. arXiv:2605.18661.
