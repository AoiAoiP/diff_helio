# AGENTS.md — 定日镜面型可微优化（Bezier 定日镜优化器）

> 本文件是本仓库唯一的 agent 入口与操作约定，2026-10-19 由 `CLAUDE.md` 改名并重写；旧版内容已并入本文，历史见 git。
> 面向人的项目介绍见 `README.md`；论文证据台账见 `experiments/INDEX.md`；图表台账见 `figures/paper/INDEX.md`。
> 本文只写可复现的事实（路径、命令、口径、坑），不写计划。计划写进台账。

---

## 1. 项目是什么

**工程**：C++17 + Vulkan 计算着色器（Slang 自动微分）的定日镜面板面型优化器。

链路：35 根支撑螺栓行程 `h` → TPS 影响函数 `Φ_b` + 20 倾角三平面重力查找表 → 表面高度与斜率场 `w, ∂w/∂u, ∂w/∂v` → GPU 蒙特卡洛光线追踪（Buie 日轮、双层玻璃折射、斜率误差）→ 接收器能流 `157×50` → S95 光斑面积 → 反向自动微分 → 力学投影 → Adam。一次 command submit 覆盖一次前向加一次反向，循环内不回读能流。

**科研**：论文《Physics-Coupled Differentiable Rendering for Heliostat Surface Optimization》，目标期刊 Advanced Engineering Informatics（CCF-B），备选 Computational Visual Media。三条贡献：

1. 物理耦合可微渲染框架：显式表面场作为渲染一等输入，结构形变到光斑对机械设计变量端到端可微（§3）。
2. 梯度可达性界限分析：固定 35 栓布局、重力惩罚显著的镜位，84%–87% 的优化差距落在梯度不可达的支撑几何子空间（§5.3）。
3. 界限驱动的结构层重设计：以螺栓边距、网格密度、镜面材料压低结构性界限（§5.4–5.5）。

---

## 2. 论文当前状态

| 部分 | 权威文件 | 状态 |
|---|---|---|
| 摘要、贡献、图清单、框架 | `docs/paper/draft.md` | 有稿；摘要 4 处数字与记录不符，见 §7.2 |
| §1 引言、§2 相关工作 | `docs/paper/draft.md`（已并入）；重写稿 `ch1_ch2_rewrite.md` | 成稿 v9 |
| §3 框架 | `docs/paper/draft.md`（已并入）；重写稿 `ch3_method_v1.md` | 成稿 v2，已与实现逐条核对 |
| §4 验证 | `docs/paper/ch4_validation_v1.md` | v1 稿，**未并入主稿**；2 项待跑 |
| §5 应用 | `docs/paper/ch5_application_v1.md` | v1 稿，**未并入主稿**；表 4 远距行作废 |
| §6 讨论与结论 | — | 未写 |
| 图 1–12 | — | 全部未绘，见 `figures/paper/INDEX.md` |
| 表 1–4 | 表 1、表 4 在 ch5；表 2 仅轮廓；表 3 缺 | 编号需统一（draft 写表 1–3，ch5 出现表 4） |
| 参考文献 [1]–[35] | `docs/paper/draft.md` 末 + `ref/literature_index.md` | 18 条已核；[4][9][18][19][21] 书目待核 |

主稿只有 Markdown，没有 `.tex`，也没有任何图文件。投稿模板在 `docs/els-cas-templates/`（AEI）与 `docs/CVM_LaTeX_Template_2025/`（CVM）。

---

## 3. 目录约定

### 3.1 现行结构（不要动）

| 路径 | 内容 | 状态与注意 |
|---|---|---|
| `src/` `shaders/` `cmake/` `CMakeLists.txt` | C++ 与 Slang 源码、构建入口 | 在用；`shaders/*.spv` 是产物 |
| `build/` | VS2022 构建产物，`build/src/Release/bezier_opt.exe` 已编译（2026-09-08） | 勿提交 |
| `data_proxy/` | 6 张影响函数表（35×32×32）、20 个重力 bin（12,288 B/个）、`gravity_angles.json`、`ansys_csv/`（21 个倾角点云） | 已跟踪，51 个文件 |
| `data/` | sundir 集（36/110/334/1558）、`ellipse*.txt`、`init*/` 初始螺栓 | 已跟踪 |
| `configs/` | 23 个正式配置 + `bolt_layouts/`（154 个布局 JSON，含 `density/`、`free/`）+ `archive/` 98 个一次性配置 | 已跟踪 |
| `scripts/` | 数据生成、FEA/光斑验证、对比分析脚本；`remote/` 为远程访问 PowerShell（5 个） | 在用；19 个根脚本 + 4 个历史实验 + 7 个已退役，分类见 `scripts/README.md` |
| `experiments/runs/` | 13 个正式运行目录（2026-10-19 从根目录 `results_*` 迁入）+ 1 个迁移冒烟 | 全部可入库；`experiments/INDEX.md` 是唯一台账 |
| `analysis/` | 派生统计表（§5.2–5.4 的数字来源）+ 6 张早期 png | 在用 |
| `docs/` | 研究文档 10 个 md + `archive/` 归档 + 两份期刊模板 | 在用 |
| `docs/paper/` | 论文草稿 5 个 `.md` | 已跟踪（2026-10-19 入库） |
| `ref/` | 9 篇 PDF + `literature_index.md` | 被 `.gitignore` 排除 |
| `archive/` | 退役 Python 管线、ROM 脚本快照 | 只读 |
| `proxy/` | 早期 TPS Python 实现 | 历史；主线用 `scripts/generate_proxy_model.py` |
| `archive/work_template_2026-10-11/` | 任务书 docx 解包工作区（2026-10-11） | 归档；源 docx 与成品均不在仓库，确认无用后可整目录删 |
| `skills/` | 3 个上游 skill 仓库（academic-research-skills / claude-autoresearch / Research-Paper-Writing-Skills）+ 自制 `papercraft/` | 来源、提交与升级方式见 `skills/SOURCES.md`；运行时用 `.dsh/skills/` 的副本；上游目录已 gitignore |
| `.dsh/skills/` `.claude/skills/` | skill 运行副本（7 + 2） | 本机配置，被 gitignore |

### 3.2 新增目录与硬规则

新增 `experiments/`（台账）与 `figures/`（图表）。四条规则，写论文期间必须遵守：

1. **实验必登记**：任何一次补跑，在 `experiments/INDEX.md` 加一行，字段为 ID、目的、支撑 claim、配置路径、原始输出路径、口径（方向数 / 迭代 / coupling / 日期）、状态。
2. **图必有映射**：每张进正文的图在 `figures/paper/` 下有同名映射文件 `figN_<slug>.md`，写明生成脚本、输入数据、最后生成时间。图片本体放 `figures/paper/`，中间产物放 `figures/generated/`。
3. **脚本不得直写 `figures/paper/`**：数据图脚本写 `figures/generated/`，人工挑选后复制进 `figures/paper/` 并登记；绘图脚本放 `figures/scripts/`，与 `scripts/`（实验与代理管线）分开。TikZ 源放 `figures/scripts/tikz/`，不经过 `generated/`。
4. **正文数字必须可追**：正文出现的每个数字，必须能在 `experiments/INDEX.md`、`docs/` 或 `analysis/` 找到一处出处；找不到的写"待补"，不得估算填充。

---

## 4. 环境与编译

- Windows 10/11 x64，Visual Studio 2022（MSVC），CMake，Python 3.12
- **Vulkan SDK 1.4.341.1**：`C:\VulkanSDK\1.4.341.1`（`slangc.exe`、`slang.dll`、`vulkan-1.lib` 都来自这里）。旧文档里的 `1.4.350.0` 在本机不存在。

```powershell
$env:VULKAN_SDK = "C:\VulkanSDK\1.4.341.1"
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

- 改 shader 后强制重编：`Remove-Item build\shaders\*.spv -Force` 再 build。CMake 把 `.spv`、`configs/`、`data/` 复制到 exe 同级目录（`build/src/Release/`）。
- 配置改完若 exe 同级目录是旧副本，重新 build 一次，或直接改 `build/src/Release/configs/` 下的副本。
- 依赖 fmt / glm 由 `third_party/` 或 FetchContent 提供，Slang 由 SDK 提供。

---

## 5. 数据与代理模型

```bash
python scripts/generate_proxy_model.py all           # TPS + 20-bin 重力（从已有 ANSYS CSV）
python scripts/generate_proxy_model.py tps           # 只重建影响函数，<1 s
python scripts/generate_sundir_year.py               # balanced，334 方向（日常与终评）
python scripts/generate_sundir_year.py --mode paper  # 110 方向（快速扫描）
python scripts/generate_sundir_year.py --mode dense  # 1558 方向（验证）
```

**格式校验（换机、交接、复现前必做）**

- 重力 bin 必须 **12,288 B/个** = 3 平面 × 32×32 × float32。旧版 4,096 B 只有位移、没有斜率，重力对法线不产生影响，结果会"光学隐形"并假收敛到无重力下界（幻影重力事故，见 `docs/gravity_compensation_experiment.md`）。
- `gravity_angles.json` 的 `format` 必须是 `w_du_dv_v2`；启动日志必须出现 `Loaded gravity_* (3-plane, ...)`。
- 影响函数 `influence_phi*.bin` 为 143,360 B = 35×32×32×4。
- `.gitignore` 忽略 `data_proxy_old/`、`data_proxy_steel/`、`data_proxy_margin/`、`data_proxy_truth/`；当前 `data_proxy/` 是被跟踪的 v2 版本。

**坐标与网格（改了就全错）**

- 板局部系：`u` 沿板宽、`v` 沿板长、`y` 沿板法向朝外；网格 pixel-centered，`u = (i+0.5)/GS`。
- 板角点 `y = -z_local·sinθ`，板法向 `(0, cosθ, +sinθ)`；螺栓位移 `(UX=0, UY=stroke·cosθ, UZ=stroke·sinθ)`；重力取板法向分量 `w = uy·cosθ + uz·sinθ`。
- shader 切向量 `tu=(W, yu, 0)`、`tv=(0, yv, L)`，法向 `n = -(tu × tv)/‖tu × tv‖`。
- 20 个重力 bin 在 GPU 侧合并为单 buffer（`20×3×1024` float），`gravity_normal_coupling:1` 时导数进入法线。

---

## 6. 运行实验

```powershell
# 优化（200 iter，lr=4e-4 恒定）
.\build\src\Release\bezier_opt.exe configs\bolt_optimize_north_200iter.json

# 纯评估：iterations=1 + learning_rate=0.0
.\build\src\Release\bezier_opt.exe configs\archive\_eval_lsq_c1_36.json

# 光斑 dump（3 个太阳方向，NPY）
.\build\src\Release\bezier_opt.exe --dump-flux --surface-file <surface> <config>

# 梯度检验（解析 vs 中心差分）
.\build\src\Release\bezier_opt.exe --check-grad <config>

# FEA 验证（需 ANSYS 许可证，台式机）
python scripts/run_fea_validation.py --result-dir <results> --angles 0 29.5 58.5
```

成本（单张桌面 GPU）：36 dir × 200 iter 单镜约 7 min、四镜约 20 min；334 dir × 200 iter 单镜约 50 min（约 15 s/迭代）；1 iter 评估几乎免费。

- 九组消融配置：`configs/archive/_fw_*.json`，输出在 `experiments/runs/fw_*`。
- 所有配置的 `output_dir` 已指向 `experiments/runs/<name>`，程序默认值为 `experiments/runs/unnamed`；不要期待根目录再出现 `results_*`。
- 基线评估：`_eval_lsq_c0_36.json`（无重力理想面）、`_eval_lsq_c1_36.json`（真实重力）、`_eval_comp_c1_36.json`（闭式补偿初值）、`_bound_nograv_300m_36.json`（无重力下界）。
- 能量项 `lambda_energy`：≤600 m 取 0；900 m 取 0.1–0.5；1200 m 取 0.5。λ=0 时远距优化会把光线驱出接收器，能量保持率降到 1%–50%，S95 虚假变小。
- 行程界 `max_bolt_stroke = 0.040`，tanh 参数化（`tanh_bound=1`）；`tanh_bound=0` 走物理空间 Adam + 软墙。

---

## 7. 数字口径与已知冲突

### 7.1 权威来源

| 数字 | 去哪看 |
|---|---|
| 代理 vs FEA 的 RMS / R² / shape_corr | `README.md`「TPS Proxy vs FEA 验证」；`docs/gravity_compensation_experiment.md` |
| APDL vs GUI 位精确一致（RMS<0.05 mm） | `README.md`；本机原始报告已不在 |
| 纯椭圆无重力 S95 基准 | §7.3 |
| B_ideal / B_naive / B\* / 三段分解 | `docs/gravity_compensation_experiment.md` §1.3–1.5；`experiments/runs/lsq_eval_c0_36`、`experiments/runs/lsq_eval_c1_36`、`experiments/runs/bound_300m_36` |
| 九组消融地板 | `docs/gravity_compensation_experiment.md`；`experiments/runs/fw_*` |
| Phase 5 边距 / 密度 / 材料 | `docs/phase5_report.md` §3.1–3.3 |
| 20 镜全场 | `data/lsq_vs_opt_334d.csv`；`analysis/real_gravity_penalty_table.md` |
| 重力场分量、悬挑占比 | `docs/gravity_compensation_experiment.md` §1.1；`analysis/layout_scan_report.md` |
| sundir 采样依据 | `docs/sundir_sampling.md` |

### 7.2 冲突清单（写进正文前必须处理）

| # | 草稿里的说法 | 记录里的数字 | 处置 |
|---|---|---|---|
| 1 | §4.1「R² > 0.98、RMS < 0.2 mm」 | R² 0.952–0.955、RMS 1.94–2.05 mm、shape_corr 0.980 | 按记录改正文 |
| 2 | 摘要「惩罚随镜位相差 3–4 倍」 | 300 m 四镜 N–S 惩罚差约 25×；20 镜 `S95_naive/B_ideal` = 1.001–1.539 | 改为区间或"近两个量级" |
| 3 | 摘要「80%–90% 源于螺栓点间悬挑弯曲」 | 80–91% 是**外圈悬挑带**（占板面积 34%）的斜率能量；螺栓点间凹陷只占小头 | 改为"螺栓网格之外的悬挑带" |
| 4 | 摘要「差距收窄至 4%–10%」 | 相对理想面型 +4.8 / +9.2 / +12.6 / +8.6%（@110dir，300 m 四镜） | 改"约 5%–13%"或注明三镜 |
| 5 | 表 4 的 900 / 1200 m 收益 | λ_E=0，能量保持 1%–50%，比值 1.9–3.7 不可用 | 删行，或补 λ≥0.5 重跑 |
| 6 | `lsq_s95_334d` 列 | 与纯椭圆无重力逐值相同，疑 `disable_gravity=1` | 核配置；确认前不得称"LS 在重力下仍近理想" |
| 7 | 光斑「总能量差距 < 1%」 | 前向能量未乘反射率 0.88，绝对能量不可比 | 改"同渲染器内相对差"，或补反射率重跑 |
| 8 | §5.4 密度红利 | 100-iter 真值 −9.8…−14.4%；ch5 写 −13.7…−15.4%（200-iter） | 统一口径，表注写明迭代数 |

### 7.3 基准值

纯椭圆无重力年均 S95（334 方向，m²）——`_eval_ellipse_nograv.json`（`disable_gravity=1` + LS 初值 + 1 iter）：

```
        150m    300m    600m    900m   1200m
North   38.78   51.61  137.79  276.76  377.11
East    49.00   67.17  167.60  295.33  383.96
South   52.06   72.24  188.56  312.81  393.37
West    48.92   67.33  167.41  294.88  383.71
```

300 m 四镜三档参照（36 方向，m²）：

| | North | East | South | West |
|---|---|---|---|---|
| B_ideal（无重力理想面） | 51.32 | 65.68 | 73.51 | 65.60 |
| B_naive（同解 + 真实重力） | 51.31 | 77.90 | 98.33 | 78.07 |
| B\*（无重力端到端下界） | 49.77 | 65.00 | 73.07 | 64.68 |
| 结构性地板占比 | 37%（不适用） | 86.9% | 84.0% | 86.0% |

Phase 5 结构层（110 方向真值）：边距 m\*=0.05，逐镜 76.16/99.16/109.96/99.12 → 54.07/72.85/81.55/72.70，合计 384.4 → 281.2（−26.8%）；密度甜点 9×7 @m05；材料钢 5 mm 把 North 300 m 由 54.73 压到 51.75。

---

## 8. 实验与图的登记规程

**实验 ID**：`E-<YYYYMMDD>-<slug>`，例如 `E-20261020-rmcrt-crosscheck`。原始输出一律放 `experiments/runs/<ID>/`。配置的 `output_dir`、程序默认值与脚本路径都已指向这里；不要新建根目录 `results_*`（会被 `.gitignore` 挡在版本控制外）。

**状态取值**：`planned` / `running` / `done` / `partial` / `invalid`（口径作废但保留证据）。

**图 ID**：`figN_<slug>`，与正文图号一一对应。映射文件模板：

```markdown
# fig10_bounds_decomposition
- 章节：§5.3
- 生成脚本：figures/scripts/fig10_bounds.py
- 输入数据：experiments/runs/bound_300m_36/optimization_summary.csv 等
- 最后生成：YYYY-MM-DD HH:MM
- 状态：draft / final
```

---

## 9. 已知坑

1. **幻影重力**：legacy 4 KB 重力 bin 让重力在光路中失效，日志显示正常、结果是假收敛。任何含 `data_proxy` 的交接都要校验字节数与 `(3-plane, ...)` 日志。
2. **能量溢出**：λ_E=0 时远距镜可以把光线驱出接收器换取虚假小 S95。远距行必须给能量保持率。
3. **历史不可比**：2026-07-27 前后（法向耦合）、tanh 参数化前后（L4）、三平面 bin 前后，结果不能直接对比；论文只用修复后的数。
4. **半像素偏移**：网格必须 pixel-centered，用 `linspace(-W/2, W/2)` 会让影响函数与渲染采样错开 ~200 mm。
5. **gitignore 吞证据**：`validation/`、`ref/`、`results_*/` 仍被忽略（4 个基线已迁入 `experiments/runs/` 并随仓库入库）。新增证据不要放回根目录 `results_*`，放 `experiments/runs/`；文献 PDF 与 `ref/literature_index.md` 需 `git add -f` 才能入库。
6. **已移除的开关**：`reflection_only_optimization`、`geometry_sample_grid`、`proxy_mode`、WoS 路线、`loss_gpu.slang` 均已删除；旧文档仍可能提到，遇到以实现为准。
7. **`.gitignore` 尾部有 GBK 乱码注释行**（历史编码事故），不影响规则匹配，勿按乱码重写。

---

## 10. 常驻文档索引

| 问题 | 文档 |
|---|---|
| 项目总览、方法、参数 | `README.md` |
| 论文结构、图清单、贡献定义 | `docs/paper/draft.md` |
| 投稿方向与取舍 | `docs/paper_strategy.md` |
| 重力补偿 Phase 0–3、九组消融、三段分解 | `docs/gravity_compensation_experiment.md` |
| Phase 5 结构优化（边距/密度/材料/ROM） | `docs/phase5_report.md`（过程日志：`docs/archive/phase5_structural_optimization.md`） |
| 螺栓位置优化（Phase 5.4/6，支线） | `docs/bolt_position_optimization_stage_report.md` |
| sundir 采样策略 | `docs/sundir_sampling.md` |
| 光斑验证协议 | `docs/flux_fea_vs_proxy_validation_guide.md` |
| 钢材热膨胀补充实验（待做） | `docs/steel_cte_experiment_guide.md` |
| 写作规范与 skill 手册 | `docs/paper_strategy.md`、`skills/papercraft/GUIDE.md` |
| 远程访问（Tailscale + OpenSSH）、排障与台式机自检 | `docs/remote_desktop_workflow.md`、`docs/prompts/desktop_link_readiness.md`、`scripts/remote/` |
| 实验台账 / 图表台账 | `experiments/INDEX.md`、`figures/paper/INDEX.md` |
| 脚本分拣与用法 | `scripts/README.md`、`archive/scripts_retired_2026-10-19/README.md` |
