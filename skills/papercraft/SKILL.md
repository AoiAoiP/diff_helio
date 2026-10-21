---
name: papercraft
description: >
  论文创作全流程工作台——集成文献管理/论文架构/写作/实验四大模块。
  文献管理：生成检索策略、链接 Zotero 本地库 (ref/)；
  论文架构：通过 academic-research-skills 规划章节、打磨观点；
  论文写作：research-paper-writing 逐段撰写 + 自审 + 终审；
  实验优化：autoresearch 端到端指标驱动实验。
  触发词：写论文、论文工作流、papercraft、paper、paper writing、论文写作、文献检索、打磨大纲。
---

# PaperCraft — 论文创作全流程工作台

将论文写作拆解为**文献管理 → 论文架构 → 论文写作 ↔ 实验优化**四个模块，每个模块由独立的 Skill 执行，PaperCraft 负责调度和衔接。

## 模块总览

```
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│  1. 文献管理  │ → │ 2. 论文架构   │ → │   3. 论文写作      │ ← │ 4. 实验优化  │
│  ref/        │    │  ARS: plan   │    │  RPW + ARS: full  │    │ autoresearch │
│  ARS: lit    │    │  ARS: outline│    │  ARS: reviewer    │    │              │
└──────────────┘    └──────────────┘    └──────────────────┘    └──────────────┘
```

## 模块一：文献管理

**目标**：建立 Zotero 本地文献库 → ref/ 的链接，生成检索策略，为写作提供引用基础。

### 能力

| 动作 | 使用的工具 | 说明 |
|------|-----------|------|
| 生成检索策略 | Claude（通用）+ `/ars-lit-review` | 关键词/数据库/筛选标准 |
| 执行检索 | **用户手动**（Undermind.ai 等） | AI 工具真检索 |
| PDF 管理 | **用户手动**（Zotero） | 存入 Zotero，建立 Collection |
| 导出到本地 | Zotero Export / ARS adapter | CSL-JSON 存入 `ref/corpus/` |
| 文献库验证 | ARS `check_literature_corpus_schema.py` | Schema 合规检查 |
| 引用验证 | ARS citation verification gate | 确定性引用存在性验证 |

### 使用示例

```
# 1. 生成检索策略
/ars-lit-review "differentiable optimization of heliostat mirror surface under gravity"

# 2. 用户用 Undermind.ai 搜索 → 下载 PDF → 导入 Zotero → 建立 "Heliostat_Opt" Collection

# 3. 从 Zotero 导出
# Zotero → Export Collection → CSL JSON → 保存到 ref/corpus/zotero_export.json

# 4. Claude 加载并验证
"加载 ref/corpus/ 中的所有文献，验证引用完整性，然后帮我写 Related Work"
```

### ref/ 目录结构

```
ref/
├── README.md                  # 模块说明
├── search_strategies/         # 检索策略记录
├── corpus/                    # 文献条目（CSL-JSON / BibTeX）
├── notes/                     # 论文阅读笔记
└── adapters/                  # Zotero 适配脚本
```

详见 `ref/README.md`。

---

## 模块二：论文架构整理

**目标**：打磨文章 idea、规划章节结构、精炼贡献陈述。

### 能力（via academic-research-skills）

| 命令 | 功能 | 适用场景 |
|------|------|---------|
| `/ars-plan` | 苏格拉底式章节规划 | 新论文启动，idea 尚模糊 |
| `/ars-outline` | 详细大纲生成 | 章节结构已明确，需细化 |
| `/ars-3w` | What/Why/Why Now 精炼 | 投稿前打磨故事线 |

### 典型工作流

```
/ars-plan → 苏格拉底对话 (3-5 轮) → 产出 RQ Brief + 章节蓝图
    → /ars-outline → 细化每节论点 + 实验方案
        → /ars-3w → 精炼贡献陈述 → 进入模块三
```

### 使用示例

```
# 启动论文规划
/ars-plan

# 直接告诉 Claude 你的 idea
"我正在写一篇关于重力作用下定日镜面型可微优化的论文，
目标期刊 AEI。帮我规划论文架构和章节大纲。"

# 精炼故事线
/ars-3w
```

---

## 模块三：论文写作

**目标**：逐段撰写 → 自审 → 同行评审 → 修订 → 终稿。

### 能力

| 工具 | 角色 | 触发方式 |
|------|------|---------|
| **research-paper-writing** (RPW) | 逐段写作 + 风格校准 + 逆向大纲检查 | 直接请求或 `/ars-full` 内部调用 |
| **academic-paper-reviewer** (ARS) | 多视角同行评审（5 审稿人 + 魔鬼代言人） | `/ars-reviewer` |
| **academic-paper** (ARS) | 全流程调度（含引用验证 + 学术诚信闸门） | `/ars-full` |

### 典型全流程

```
/ars-full
  → 自动执行:
      Stage 1: deep-research（文献背景）
      Stage 2: outline + draft（逐段写作，调用 RPW 风格指导）
      Stage 2.5: 学术诚信闸门（引用存在性 + 主张-证据对齐）
      Stage 3: academic-paper-reviewer（5 位评审 + 魔鬼代言人）
      Stage 4: revision（修订）
      Stage 4.5: 终审闸门
      Stage 5: format-convert（LaTeX / DOCX 输出）
      Stage 6: AI Self-Reflection Report
```

### 快捷命令

| 命令 | 用途 |
|------|------|
| `/ars-full` | 全流程一键执行 |
| `/ars-abstract` | 单独打磨摘要 |
| `/ars-reviewer` | 单独运行同行评审 |
| `/ars-revision` | 按审稿意见修订 |
| `/ars-rebuttal-audit` | 审阅 Rebuttal |
| `/ars-citation-check` | 引用完整性检查 |

### RPW 风格指南（按 section 调用）

当只需要写某个具体 section 时，直接使用 research-paper-writing skill：

```
# 写 Introduction
"使用 research-paper-writing skill，帮我重写 Introduction，
重点打磨贡献陈述和 motivation 段落"

# 写 Method
"用 research-paper-writing skill 写 Method 部分，
确保技术细节完整、可复现"

# 自审
"用 RPW 的 paper-review checklist 做一次完整的 adversarial self-review"
```

RPW section 指南位于 `references/`：`introduction.md`, `abstract.md`, `related-work.md`, `method.md`, `experiments.md`, `conclusion.md`, `paper-review.md`。

---

## 模块四：实验优化

**目标**：端到端指标驱动实验，自主调参、验证、保留/丢弃。

### 能力（via autoresearch）

| 模式 | 用途 | 触发 |
|------|------|------|
| **Loop** | 指标驱动自主优化 | `/autoresearch 将 S95 降低到 50 m²` |
| **Debug** | 假设驱动 Bug 调查 | `/autoresearch 调试能量溢出问题` |
| **Fix** | 错误计数归零 | `/autoresearch 修复所有编译错误` |

### 典型工作流

```
提出假设 → /autoresearch (loop) → 自主跑实验 → 保留最优结果
    → 回到模块三 → 将实验结果写入 Experiments section
```

---

## 推荐论文创作全流程

### 启动阶段（1-2 天）

```
1. /ars-plan                              # 规划论文架构
2. /ars-lit-review "你的研究主题"          # 生成检索策略
3. [手动] Undermind.ai 检索 → Zotero 整理  # 收集文献
4. "加载 ref/corpus/，帮我做文献综述"       # 链接文献库
```

### 写作阶段（3-5 天）

```
5. /ars-full                              # 全流程写作（含自审 + 引用验证）
   或分步:
   /ars-outline  →  逐段用 RPW 写作  →  /ars-reviewer  →  /ars-revision
```

### 实验补充（穿插进行）

```
6. /autoresearch "<实验目标>"             # 边写边补实验
7. "把最新实验结果写入 Experiments section"
```

### 终审阶段（1-2 天）

```
8. /ars-reviewer                          # 最终同行评审
9. /ars-revision                          # 按审稿意见修改
10. /ars-citation-check                   # 引用完整性终检
11. /ars-format-convert --format latex    # 输出投稿格式
```

---

## 可用命令速查

### ARS（论文架构 + 写作 + 评审）

| 命令 | 功能 |
|------|------|
| `/ars-plan` | 章节规划（苏格拉底对话） |
| `/ars-outline` | 详细大纲 |
| `/ars-3w` | 贡献陈述精炼 |
| `/ars-full` | 全流程（研究→写作→评审→修订→终稿） |
| `/ars-lit-review` | 文献综述 / 检索策略 |
| `/ars-abstract` | 摘要打磨 |
| `/ars-reviewer` | 多视角同行评审 |
| `/ars-revision` | 按审稿意见修订 |
| `/ars-revision-coach` | 修订指导 |
| `/ars-rebuttal-audit` | Rebuttal 审阅 |
| `/ars-citation-check` | 引用完整性验证 |
| `/ars-format-convert` | 格式转换（LaTeX/DOCX） |
| `/ars-disclosure` | AI 使用声明 |
| `/ars-mark-read` | 标记文献已读 |
| `/ars-cache-invalidate` | 清除验证缓存 |

### RPW（论文写作风格）

| 触发方式 | 功能 |
|---------|------|
| "用 research-paper-writing skill 写/改 [section]" | 逐段写作 + 风格校准 |
| "paper review this draft" | 对抗性自审 |
| "check flow of this paragraph" | 段落清晰度检查 |

### Autoresearch（实验优化）

| 命令 | 功能 |
|------|------|
| `/autoresearch <goal>` | 指标驱动自主实验 |

---

## 工具清单

| 工具 | 安装状态 | 位置 |
|------|:---:|------|
| **academic-research-skills** v3.19.0 | ✅ 已安装 | Plugin (user scope) |
| **research-paper-writing** (RPW) | ✅ 已安装 | `.claude/skills/research-paper-writing/` |
| **claude-autoresearch** v0.1.0 | ✅ 已安装 | Plugin (user scope) |
| **PaperCraft** (本 Skill) | ✅ 已安装 | `.claude/skills/papercraft/SKILL.md` |
| **ref/** 文献管理模块 | ✅ 已就绪 | `ref/README.md` |
