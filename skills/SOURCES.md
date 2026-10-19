# skills/ — 外部研究 skill 的来源与版本

本目录存放从外部下载/克隆的研究类 skill 与自制 skill。**运行时并不直接读取这里**，DSH 读取的是 `.dsh/skills/`（本机配置，被 `.gitignore` 排除）。

## 1. 已集成的 skill（DSH 侧）

`.dsh/skills/` 下有 7 个可用 skill，均以**副本**形式安装，不是软链接：

| DSH skill | 来源 | 说明 |
|---|---|---|
| `academic-paper` | `skills/academic-research-skills/skills/academic-paper` | 论文写作 12-agent 流水线 |
| `academic-paper-reviewer` | `skills/academic-research-skills/skills/academic-paper-reviewer` | 多视角审稿模拟 |
| `academic-pipeline` | `skills/academic-research-skills/skills/academic-pipeline` | 全流程编排 |
| `deep-research` | `skills/academic-research-skills/skills/deep-research` | 深度调研 |
| `autoresearch` | `skills/claude-autoresearch/skills/autoresearch` | 目标驱动实验循环 |
| `research-paper-writing` | `skills/Research-Paper-Writing-Skills/research-paper-writing` | 论文写作方法 |
| `papercraft` | `skills/papercraft/SKILL.md`（自制） | 四模块工作台，调度上面几个 skill |

结论：**已经集成**。根目录的三个上游仓库只是来源，删掉或归档不影响 DSH 运行；但删除后升级需要重新 clone。

## 2. 上游来源

| 目录 | 远端 | 提交 | 版本 | 体量 |
|---|---|---|---|---|
| `skills/academic-research-skills/` | `git@github.com:Imbad0202/academic-research-skills.git` | `cb6ca42`（2026-08-11） | `v3.19.0-80-gcb6ca42` | 32 MB |
| `skills/claude-autoresearch/` | `git@github.com:yin52133/claude-autoresearch.git` | `e397b9f`（2026-04-21） | 无 tag | 0.12 MB |
| `skills/Research-Paper-Writing-Skills/` | `git@github.com:Master-cai/Research-Paper-Writing-Skills.git` | `77e7c2c`（2026-06-23） | 无 tag | 0.10 MB |
| `skills/papercraft/` | 本仓库自制（原在 `.claude/skills/papercraft/`） | — | — | 9 KB |

三个上游目录保留各自的 `.git`，可 `git -C skills/<name> pull` 升级；升级后把对应 skill 目录复制到 `.dsh/skills/` 覆盖。

## 3. 维护约定

1. 升级上游后，同步更新本文件的提交号与日期。
2. `.dsh/skills/` 与 `.claude/skills/` 是本机配置，**不入库**；跨机器迁移时按本节表格重新安装。
3. `skills/*/` 已在 `.gitignore` 中排除（它们是带自己 `.git` 的 vendored 仓库），只有本文件与 `skills/papercraft/` 入库。
4. 新增外部 skill 时，克隆到 `skills/<仓库名>/`，并在本文件加一行来源与提交。
