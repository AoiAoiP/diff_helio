# Diff Helio — 可微定日镜面型优化

基于 **Vulkan GPU 光线追踪 + Slang 自动微分**的定日镜螺栓调高优化管线。通过 TPS（薄板样条）物理代理模型将 35 根螺栓推拉高度映射为镜面变形、将 FEA 重力形变耦合进表面法线，最小化圆柱接收器上的年均 S95 光斑面积。

**当前研究主线**：重力补偿与结构性地板认证（2026-07-27 起，Phase 0–3 已闭环）——见
`docs/gravity_compensation_experiment.md`（主报告）与下文「研究主线」一节。

---

## 快速开始

### 环境要求

- Windows, Visual Studio 2022, CMake ≥ 3.20
- Vulkan SDK ≥ 1.4.350.0
- Python ≥ 3.10 (numpy, scipy) — 仅数据准备/验证脚本
- NVIDIA GPU（测试：RTX 4070 SUPER 12GB / RTX 4060 Laptop）
- ANSYS（**可选**）：仅重新生成重力数据或跑 FEA 验证时需要；仓库已含预生成数据，优化开箱即跑

### 编译

```powershell
$env:VULKAN_SDK = "C:\VulkanSDK\1.4.350.0"
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

依赖项 (fmt, glm, Slang) 通过 CMake `FetchContent` 自动下载。强制重编译 shader：`rm build/shaders/*.spv && cmake --build build --config Release`。

### 数据准备（仓库已含全部预生成数据，本节仅再生成时需要）

```bash
# 一键生成 TPS influence（<1s, 无需 ANSYS）
python scripts/generate_proxy_model.py tps

# 通过 ANSYS MAPDL 批量生成 20-bin 重力（需 ANSYS，~3 min）
python scripts/ansys_gravity.py --bolt-layout configs/bolt_layouts/7x5_default.json

# 将 ANSYS CSV 转换为 .bin 重力文件（v2 三平面 [w, dw/du, dw/dv] 格式）
python scripts/generate_proxy_model.py gravity --source-dir data_proxy/ansys_csv
```

> 重力 bin 为 v2 三平面格式（12288 B/bin，`gravity_angles.json` 标记 `w_du_dv_v2`）。
> **环境自检**：运行日志须含 20 行 `Loaded gravity_*deg.bin (3-plane, ...)`；
> 若为 `legacy 1-plane` 则重力光学失效（幻影重力），结果全部无效——见主报告 §1.6。

### 运行优化

```bash
# 重力下端到端优化（Phase 3 基线组，300m NEWS 四镜，36dir，100 iter）
./build/src/Release/bezier_opt.exe configs/_fw_tanh_a0.json

# eval 模式（iterations:1, lr:0，不重训只评估）
./build/src/Release/bezier_opt.exe configs/_eval_lsq_c1_36.json

# 光斑输出 / 梯度检验
./build/src/Release/bezier_opt.exe --dump-flux --surface-file <path> <config>
./build/src/Release/bezier_opt.exe --check-grad <config>
```

### 螺栓布局

`configs/bolt_layouts/` 目录定义螺栓排布：`7x5_default.json`（35 螺栓，当前生产配置，边距 8%）、`6x6.json`（36，对称方案）。

---

## 核心方法

### 物理代理模型

定日镜在板局部坐标系下的法向位移由两项叠加：

$$w(\mathbf{r}) = UY_{\text{grav}}^{\text{FEA}}(\theta) + \sum_{b=1}^{35} h_b \cdot \phi_b^{\text{TPS}}(\mathbf{r})$$

- **重力项**：20 个稠密角度 FEA NLGEOM-ON 解的插值（10°–80°, 间距 ≤4°），v2 三平面格式
  同时提供 $w$、$\partial w/\partial u$、$\partial w/\partial v$——重力斜率直接进入表面法线
  （`gravity_normal_coupling`，2026-07-27 修复；此前重力只改高度不改法线，光学上完全隐身）；
- **螺栓项**：35 个 TPS 影响函数的线性叠加，$\phi_b$ 满足单位分解（PV < 10⁻⁶）。

模型定义在板局部坐标系下，$\partial w / \partial h_b = \phi_b$ 严格成立，链式法则直接适用。

### 可微光线追踪

```
螺栓高度 h[35] → TPS 叠加 + 重力插值(含法线耦合) → 曲面 yGrid/nGrid (32×32)
    → 接收器像素光线 (157×50) → 2 层玻璃折射 + Buie 太阳模型
    → 能流分布 → GPU 协作二分查找 S95 阈值 → sigmoid 损失
    → Slang bwd_diff 反传 → 螺栓梯度 → Adam 更新
```

### 损失函数与正则体系

S95 sigmoid 损失：$L = \sum_{\text{pixel}} \sigma\big(6 \cdot (\text{flux} / \text{S95}_{\text{level}} - 1)\big)$，
S95 阈值为包含 95% 总能量的最低能流水平（GPU 端协作二分搜索，阈值不出 GPU）。

可选正则（全部闭式梯度，详见主报告 §2.3）：

```
L(h) = L_S95 + λ_E·L_energy                效率项（默认 0）
     + λ_s·(h−h*)ᵀ G (h−h*)                R_anchor：斜率 Gram 锚定（锚点含闭式重力补偿）
     + λ_b·hᵀ K h                           R_bend：弯曲能
     + λ_h·Σ max(|h_b|−h_max, 0)²           R_soft：软行程墙（tanh_bound:0 时替代硬界）
```

螺栓参数化默认 L4 tanh 有界（$h = h_{max}\tanh(\varepsilon)$，`max_bolt_stroke`），
`tanh_bound:0` 切换为无界物理空间 + 软墙；两种模式 lr 语义已对齐（推荐 lr=4e-4）。

---

## 研究主线：重力补偿与结构性地板（2026-07-27 起，Phase 0–3 闭环）

**动机**：旧管线"优化 ≈ 椭圆拟合"——诊断证明重力在原渲染器中光学隐身（只改高度、不进法线），
proxy 对光学目标的贡献结构上为零。修复重力→法线耦合后，重力成为光学主导项，
由此建立"B_ideal / B_naive / B_comp / B\*"基线体系与差距三分解框架。

**核心结论**（36dir, 300m NEWS, S95 m²）：

| 镜 | B_naive（LSQ+重力） | B_comp（闭式补偿 init） | 端到端最优 | B\*（无重力下界） | 地板残余占比 |
|---|:---:|:---:|:---:|:---:|:---:|
| North | 51.31 | 51.75 | 50.34 | 49.77 | 37%（免罚镜） |
| East | 77.90 | 76.71 | 76.21 | 65.00 | **86.9%** |
| South | 98.33 | 94.90 | 94.28 | 73.07 | **84.0%** |
| West | 78.07 | 76.83 | 76.19 | 64.68 | **86.0%** |

- 9 组消融（参数化 × 锚定 × 行程约束 × 弯曲能 × init）终值极差 ≤0.13 m²——
  **E/S/W 重力地板是 35 螺栓支撑布局的结构性硬约束**，与优化器/正则/init 均无关；
- 螺栓面型调节对重力畸变的补偿上限 ~13–16%；理论可缩小差距的 84–87% 不可达，
  出路在支撑布局/刚度设计而非螺栓调节；
- 闭式补偿（proxy 线性性直接做功）+ 地板定量归因 = 对"proxy 未起优化作用"的完整回答。

**主报告**：`docs/gravity_compensation_experiment.md`（诊断结论 / 诊断方案 / 实验日志 / 文件清单四段式）。

---

## P0/P1 优化（ARCAim 启发，2026-07-20）

- **A1 逐光线角度预裁剪**（`ray_cull`，默认 ON）：宏观法向反射余弦预测试，North300m 全轨迹
  位精确一致，总时间 −4.8%；margin 调小是有损加速旋钮（仅供诊断）。
- **L1 效率项**（`lambda_energy`，默认 0）：λ=0.1 时最终 S95 +0.65%（能量保持倾向的代价）。
- **A2 编译期太阳模型特化**：Buie/Pillbox/Gaussian 三特化入口，按 `sun_type` 自动选择。
- **L4 tanh 有界参数化**（`max_bolt_stroke`）：始终启用；优化动力学自 2026-07-20 起变化，
  iter 0 与旧代码位精确一致，iter ≥1 按设计偏离。
- **L3 逐迭代随机种子**（`randomize_seed`，默认 OFF）。
- **A3 reflection-only**：已停用（改变物理模型、与全折射不可比）。

---

## 历史实验结果（2026-07，重力耦合修复前）

> ⚠️ 以下结果产生于 `gravity_normal_coupling` 修复之前——当时重力光学隐身，
> 优化 ≈ 理想椭圆拟合，S95 数值与修复后（coupling=1）**不可直接比较**。

### 四面镜 300m（200 iter, lr=4e-4, 零初始化）

| 镜面 | 初始 S95 | 最优 S95 | 改善 | 最大行程 |
|:---:|:---:|:---:|:---:|:---:|
| North | 227.3 | **50.02** | 78.0% | 35.7 mm |
| East | 214.4 | **65.17** | 69.6% | 35.6 mm |
| South | 198.3 | **73.08** | 63.1% | 34.5 mm |
| West | 215.0 | **64.70** | 69.9% | 36.1 mm |

四面合计 S95：253.0 m²。

### TPS Proxy vs FEA 验证（North 300m 最优螺栓，NLGEOM-ON）

| 角度 | RMS | R² | shape_corr |
|:---:|:---:|:---:|:---:|
| 29.5° | 1.94–1.96 mm | 0.955 | 0.980 |
| 58.5° | 2.04–2.05 mm | 0.952 | 0.980 |

能流相关系数 > 0.997（形变误差经光学低通滤波后仅 ~1.2% NRMSE）；proxy S95 偏乐观 6–8%，
与 PV 高估一致。APDL 批处理与 Workbench GUI 位精确一致（RMS < 0.05 mm），
自动化 FEA 管线可完全替代手工 GUI 导出。
（原始 CSV/报告已随 2026-07-30 仓库瘦身归档移出 git；结论数据以本表与 `analysis/` 为准。）

---

## 项目结构

```
├── src/                           C++ Vulkan 管线（pipeline.cpp：优化循环/S95/反传/Adam）
├── shaders/                       Slang GPU 计算着色器
│   ├── bolt_common.slang          影响函数求值 + 重力三平面插值 + 法线耦合开关
│   ├── bolt_forward/backward.slang  力学正向 / 三阶段反向
│   ├── bolt_optimizer.slang       螺栓 Adam（锚定/弯曲/软墙梯度 + tanh_bound 分支）
│   ├── forward.slang / loss.slang   光线追踪 + 双折射 + Buie / S95 sigmoid 损失
│   └── sunshape.slang             可微太阳形状 (Buie/Pillbox/Gaussian)
├── scripts/
│   ├── generate_proxy_model.py    统一数据生成（TPS + v2 三平面重力）
│   ├── ansys_gravity.py           ANSYS 批处理 20-bin 重力生成
│   ├── gravity_decomposition.py   重力三频带分解与可补偿性诊断（Phase 0）
│   ├── lsq_fit_compensated.py     闭式重力补偿 init + 锚定 buffer 生成（Phase 2）
│   ├── run_fea_validation.py      ANSYS FEA 验证（螺栓行程仿真 + proxy 对比）
│   └── post_fea_validation.py     三路形变验证（APDL vs GUI vs Proxy）
├── configs/                       JSON 配置（_fw_* Phase 3 消融、_eval_* 基线、_bound_* 下界）
│   └── bolt_layouts/              螺栓布局定义 (7×5, 6×6)
├── data/                          太阳方向（36/110/334/369dir）、椭圆参数、init 螺栓
│   ├── init_lsq/                  LSQ 椭圆拟合 init（naive）
│   └── init_comp_36/              闭式重力补偿 init + 逐镜锚定 buffer（36dir）
├── data_proxy/                    TPS 影响函数 + v2 三平面重力 bins（12288 B/bin）
├── proxy/                         Python 侧 TPS 管线参考实现
├── results_fw_*/                  Phase 3 消融结果（9 组，BEST_bolts + history）
├── results_bound_300m_36/         B* 无重力下界结果
├── results_*_eval_*_36/           基线 eval 结果（B_ideal / B_naive / B_comp）
├── sundir_sample/                 太阳方向采样策略分析报告
├── docs/                          主报告、投稿策略、论文初稿、移交文档
└── analysis/                      诊断与惩罚表报告
```

> 2026-07-30 仓库瘦身：`train_data/`、`validation/`、`data_proxy_old/`、`wang/`、`logs/` 及
> 过期结果目录已移出 git（FEA 原始证据留有本地归档）；历史经 filter-repo 重写，
> 旧 commit 哈希与 bundle 全部失效，协作方请重新 clone。

---

## 参数速查

| 参数 | 值 |
|------|-----|
| 镜面尺寸 | 12.84 × 9.45 m × 4 mm |
| 螺栓数 / 布局 | 35 (7×5), 边距 8% |
| 渲染网格 | 32×32 |
| 接收器 | 圆柱 R=10m H=20m, 157×50 px |
| 板弯曲刚度 D | 392 N·m |
| 重力载荷 q | 98.1 N/m² |
| 玻璃折射率 | 1.523, 厚 4mm |
| 太阳模型 | Buie CSR=0.01, DNI=1000 W/m² |
| 斜率误差 | 1 mrad |
| 学习率（推荐） | 4×10⁻⁴ constant（tanh 与无界模式一致） |
| Adam β₁, β₂, ε | 0.9, 0.999, 10⁻⁸ |

### 配置键速查

| 键 | 默认 | 说明 |
|------|:---:|------|
| `gravity_normal_coupling` | 1 | 重力导数进入法线（0=legacy 幻影行为，供消融/自检） |
| `anchor_lambda` (λ_s) | 0.0 | 斜率 Gram 锚定强度（>0 需 `{name}_anchor.bin`） |
| `bend_lambda` (λ_b) | 0.0 | 弯曲能正则强度 |
| `soft_stroke_lambda` (λ_h) | 0.0 | 软行程墙强度（单边二次） |
| `tanh_bound` | 1 | 1=L4 tanh 有界；0=无界物理空间 + 软墙 |
| `max_bolt_stroke` | 0.040 | tanh 行程界（m）；重力实验用 0.06（容纳 comp init ~54mm） |
| `ray_cull` / `ray_cull_margin_mrad` | 1 / 8.0 | A1 预裁剪开关 / 余量 |
| `lambda_energy` | 0.0 | L1 效率项权重 |
| `stroke_regularization` | 0.0 | L4 行程正则权重 |
| `randomize_seed` | 0 | L3 逐迭代换种 |

---

## 文档索引

| 文件 | 内容 |
|------|------|
| `CLAUDE.md` | 开发者参考：编译、架构、方法论、实验日志 |
| `docs/gravity_compensation_experiment.md` | **重力补偿主报告**（诊断结论/方案/日志/清单，Phase 0–3 闭环） |
| `docs/gravity_compensation_experiment.md` §3.7 | **Phase 4 FEA 抽查**（台式机，South+North 300m × 3 角度：地板为真实物理，含执行/产物补记） |
| `docs/phase4_110dir_desktop_handoff.md` | 110dir 复核台式机操作文档（采样证伪实验，执行中） |
| `docs/submission_strategy_and_outline.md` | 投稿方向分析（AEI 首选）+ 论文大纲 + 后续工作 |
| `docs/draft.md` | 论文初稿中文版（摘要 + 引言 + 相关工作，§3 起为大纲） |
| `docs/experiment_handoff.md` | 双机交接记录（历史，bundle 方案已作废） |
| `analysis/gravity_compensability_report.md` | Phase 0 重力可补偿性诊断（三频带分解、H3 预测） |
| `analysis/real_gravity_penalty_table.md` | Phase 1 真实重力惩罚表（20 镜 A/B） |
| `sundir_sample/` | 太阳方向采样策略分析（36/110/334dir 一致性） |
| `analysis/` | 其他历史分析文档 |
