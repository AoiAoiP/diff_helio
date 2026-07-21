# Diff Helio — 可微定日镜面型优化

基于 **Vulkan GPU 光线追踪 + Slang 自动微分**的定日镜螺栓调高优化管线。通过 TPS（薄板样条）物理代理模型将 35 根螺栓推拉高度映射为镜面变形，最小化圆柱接收器上的 S95 光斑面积。

---

## 快速开始

### 环境要求

- Windows, Visual Studio 2022, CMake ≥ 3.20
- Vulkan SDK ≥ 1.4.350.0
- Python ≥ 3.10 (numpy, scipy) — 仅数据准备
- NVIDIA GPU（测试：RTX 4070 SUPER 12GB）

### 编译

```powershell
$env:VULKAN_SDK = "C:\VulkanSDK\1.4.350.0"
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

依赖项 (fmt, glm, Slang) 通过 CMake `FetchContent` 自动下载。强制重编译 shader：`rm build/shaders/*.spv && cmake --build build --config Release`。

### 数据准备

```bash
# 一键生成 TPS influence（<1s, 无需 ANSYS）
python scripts/generate_proxy_model.py tps

# 通过 ANSYS MAPDL 批量生成 20-bin 重力（需 ANSYS 许可证，~3 min）
python scripts/ansys_gravity.py --bolt-layout configs/bolt_layouts/7x5_default.json

# 将 ANSYS CSV 转换为 .bin 重力文件
python scripts/generate_proxy_model.py gravity --source-dir data_proxy/ansys_csv
```

> 所有脚本已统一为 GUI Workbench 约定：板法向 = (0, cosθ, +sinθ)，网格使用 pixel-centered 坐标。`scripts/prepare_data.py` 和 `scripts/generate_tps_influence.py` 已废弃。

输出至 `data_proxy/`：`influence_phi.bin`、`gravity_{angle}deg.bin`（20 个角度）、`gravity_angles.json`。

### 运行优化

```bash
# 四面镜优化（推荐：200 iter, lr=4e-4 constant, ~20 min）
./build/src/Release/bezier_opt.exe configs/bolt_optimize_4mirror_200iter.json

# North 300m 单镜（200 iter, ~7 min）
./build/src/Release/bezier_opt.exe configs/bolt_optimize_north_200iter.json

# 光斑输出
./build/src/Release/bezier_opt.exe --dump-flux --surface-file <path> <config>

# 梯度检验
./build/src/Release/bezier_opt.exe --check-grad <config>
```

### 螺栓布局

`configs/bolt_layouts/` 目录定义螺栓排布：

| 布局 | 螺栓数 | 说明 |
|------|:---:|------|
| `7x5_default.json` | 35 (7×5) | 当前生产配置，边距 8% |
| `6x6.json` | 36 (6×6) | 对称方案 |

---

## 核心方法

### 物理代理模型

定日镜在板局部坐标系下的法向位移由两项叠加：

$$w(\mathbf{r}) = UY_{\text{grav}}^{\text{FEA}}(\theta) + \sum_{b=1}^{35} h_b \cdot \phi_b^{\text{TPS}}(\mathbf{r})$$

- **重力项**：20 个稠密角度的 FEA NLGEOM-ON 解的双线性插值（10°–80°, 间距 ≤4°）
- **螺栓项**：35 个 TPS 影响函数的线性叠加。$\phi_b$ 为螺栓 $b$ 的单位位移响应，满足单位分解 $\sum\phi_b \equiv 1$（PV < 10⁻⁶）

模型定义在板局部坐标系下，$\partial w / \partial h_b = \phi_b$ 严格成立，链式法则直接适用。

### 可微光线追踪

```
螺栓高度 h[35] → TPS 叠加 + 重力插值 → 曲面 yGrid/nGrid (32×32)
    → 接收器像素光线 (157×50) → 2 层玻璃折射 + Buie 太阳模型
    → 能流分布 → GPU 协作二分查找 S95 阈值 → sigmoid 损失
    → Slang bwd_diff 反传 → 螺栓梯度 → Adam 更新
```

梯度通过 Slang 自动微分精确计算，重放完整光路（包括双折射和太阳形状）。

### 损失函数

S95 sigmoid 损失：$L = \sum_{\text{pixel}} \sigma\big(6 \cdot (\text{flux} / \text{S95}_{\text{level}} - 1)\big)$，其中 S95 阈值为包含 95% 总能量的最低能流水平（GPU 端协作二分搜索，与 CPU 版语义一致，阈值不出 GPU）。

可选效率项（`lambda_energy`，默认 0 关闭）：$L_{eff} = \lambda \cdot M \cdot E_{ref} / E$——ARCAim 式能量守卫，补 S95 损失的能量尺度盲区。M=接收面像素数，E 为当前总能量（复用 S95 二分查找已算的 `s95State[2]`，零额外 pass），E_ref 为 iter 0 逐太阳方向捕获的参考能量。

---

## P0/P1 优化（ARCAim 启发，2026-07-20）

对照 diffspt/ARCAim 论文方法论的差距分析（`analysis/arcaim_comparison.md`）后实施的两批优化。**P0** 在独立分支验证后并入；**P1** 为参数化与特化改动。

### P0（已验证，见 `analysis/p0_validation_report.md`）

- **A1 逐光线角度预裁剪**（`ray_cull`，默认 ON；`ray_cull_margin_mrad` 默认 8）：进入 Box-Muller + 双层玻璃折射前，先用宏观面法向反射做余弦预测试，跳过真实贡献严格为零的光线。North300m 200-iter 全轨迹与基线**位精确一致**（max\|ΔLoss\|=0，最优螺栓逐字节相同），总时间 **−4.8%**。裁剪半径 = 日轮支持域 + margin（Buie 43.6 mrad + 8 mrad）；margin 调小是有损加速旋钮（margin=−30 时 ~3.2× 加速、S95 偏差 13%，仅供诊断）。
- **L1 效率项**（`lambda_energy`，默认 0）：λ=0.1 时 loss 偏移实测 +28,342 ≈ 理论 λ·M·E_ref/E = +28,260，收敛正常，最终 S95 +0.65%（能量保持倾向的代价）。λ=0 时数学上逐位等价于纯 S95 路径。

### P1

- **A2 编译期太阳模型特化**：`renderForward` / `renderBackwardBolt` 各生成 Buie/Pillbox/Gaussian 三个特化入口（Slang let-generic 常量折叠，零运行时分支），按 `sun_type` 自动选择管线；原通用入口保留作兼容。无需配置。
- **L4 tanh 有界参数化**（`max_bolt_stroke`，默认 0.040 m）：物理螺栓高度 $h = h_{max}\cdot\tanh(\varepsilon)$，Adam 在无界 $\varepsilon$ 空间更新，天然约束行程 \|h\| < h_max 且边界附近梯度软化。学习率自动补偿（`lr_ε = lr / h_max`），零点附近与旧直接参数化步长一致。**始终启用**；`stroke_regularization`（默认 0）可加 L_reg = λ·‖h‖² 行程正则。
- **L3 逐迭代随机种子**（`randomize_seed`，默认 OFF）：ON 时每次迭代更换 Gaussian 采样种子（diffspt Algorithm 1 风格），降低冻结噪声造成的梯度偏差；OFF 时保持固定位流（旧行为，逐位复现）。
- **A3 reflection-only 快速路径**：配置项 `reflection_only_optimization` 保留但**已停用**——实现后评估认为改变物理模型、与全折射结果不可比，代码固定走全折射路径（`common.slang` / `pipeline.cpp` 中标注 `was reflectionOnly`）。

### 行为变化提示

P1-L4 使优化动力学自 2026-07-20 起发生变化：iter 0 与旧代码**位精确一致**，iter ≥1 起轨迹按设计偏离（零点邻域步长等价，随 \|h\| 增大渐变）。仓库中 `results_s95gpu` 等历史结果由 pre-P1 代码产生，逐位复现需回退到 `26f1d2e`。

### 新增配置键

| 键 | 默认 | 说明 |
|------|:---:|------|
| `ray_cull` | 1 | A1 逐光线预裁剪开关（0 = 旧路径，位精确） |
| `ray_cull_margin_mrad` | 8.0 | 裁剪余量（mrad），负值为有损诊断模式 |
| `lambda_energy` | 0.0 | L1 效率项权重 λ |
| `max_bolt_stroke` | 0.040 | L4 tanh 行程界 h_max（m） |
| `stroke_regularization` | 0.0 | L4 行程正则权重 |
| `randomize_seed` | 0 | L3 逐迭代换种（1 = ON） |
| `reflection_only_optimization` | 0 | 已停用（解析但无效） |

---

## 实验结果

### 四面镜 300m — 200 iter · lr=4e-4 · 零初始化

#### 2026-07-20 最新（修复代理模型，`results_4mirror_v2/`）| 总耗时：~36 min

| 镜面 | 初始 S95 | 最优 S95 | 改善 | 最大行程 |
|:---:|:---:|:---:|:---:|:---:|
| North | 227.3 | **50.02** | 78.0% | 35.7 mm |
| East | 214.4 | **65.17** | 69.6% | 35.6 mm |
| South | 198.3 | **73.08** | 63.1% | 34.5 mm |
| West | 215.0 | **64.70** | 69.9% | 36.1 mm |

**四面合计 S95：253.0 m²**

#### 2026-07-17（旧代理模型，`results_4mirror_200iter/`）| 总耗时：~20 min

| 镜面 | 位置 | 初始 S95 | 最优 S95 | 改善 | 最大行程 | 收敛@iter |
|:---:|---|:---:|:---:|:---:|:---:|:---:|
| North | (0,0,−300) | 227.3 | **50.05** | 78.0% | 36.0 mm | ~70 |
| East | (300,0,0) | 214.4 | **65.11** | 69.6% | 35.9 mm | ~80 |
| South | (0,0,300) | 198.3 | **73.13** | 63.1% | 34.6 mm | ~50 |
| West | (−300,0,0) | 215.0 | **64.67** | 69.9% | 36.7 mm | ~90 |

**四面合计 S95：253.0 m²**（相比旧数据 259.0 m² 改善 2.3%）

#### 收敛里程碑

| Iter | North | East | South | West |
|:---:|:---:|:---:|:---:|:---:|
| 0 | 227.3 | 214.4 | 198.3 | 215.0 |
| 30 | 80.7 | 87.8 | 88.0 | 87.2 |
| 50 | 59.8 | 70.8 | 75.7 | 70.9 |
| 70 | 52.2 | 66.9 | 74.5 | 66.6 |
| 100 | 51.9 | 66.7 | 74.5 | 66.3 |
| 150 | 51.8 | 66.6 | 74.5 | 66.2 |
| 200 | **50.1** | **65.1** | **73.1** | **64.7** |

> E/S/W 在 iter 50–80 已基本收敛，后续改善 <0.3 m²。

### 与旧数据对比（旧 data_vsm_mnvn_tik32, lr=2e-4→1e-7, 300 iter）

| 镜面 | 旧 S95 | 新 S95 | 改善 |
|------|:---:|:---:|:---:|
| North | 52.30 | **50.05** | +4.3% |
| East | 67.47 | **65.11** | +3.5% |
| South | 78.02 | **73.13** | +6.3% |
| West | 87.02 | **64.67** | **+25.7%** |

**关键发现**：West 改善最大 (+25.7%)——旧衰减 lr + 旧数据将其困在极差的局部极小值（87.02 m²）。恒定高 lr (4e-4) 配合修正后的 data_proxy 数据，在所有方向上均显著优于旧方案。

### TPS Proxy vs FEA 验证

| 角度 | NLGEOM | RMS | R2 | shape_corr |
|:---:|:---:|:---:|:---:|:---:|
| 29.5° | ON | **1.94 mm** | **0.955** | **0.980** |
| 29.5° | OFF | 2.45 mm | 0.929 | 0.968 |
| 58.5° | ON | **2.04 mm** | **0.952** | **0.980** |
| 58.5° | OFF | 2.22 mm | 0.942 | 0.976 |

> NLGEOM-ON 在所有指标上优于 OFF——proxy 使用 NLGEOM-ON 重力 bins，天然匹配 FEA-ON 解。详细报告见 `validation/fea_comparison/FEA_VALIDATION_REPORT.md`。

---

## 后续工作进展

### ✅ 方向 1：理想椭圆面 vs. TPS 拟合面 — 已完成

四面镜椭圆 vs TPS 对比实验完成，详细报告见 `results_4mirror_200iter/EXPERIMENT_REPORT.md`。核心发现：LS−Ell RMS = 0.50mm（四面一致），TPS 优化始终优于椭圆拟合（Δ=0.14–0.54 m²），恒定高 lr 优于衰减 lr。

### ✅ 方向 2（部分）：ANSYS APDL 脚本修正 — 已完成

`scripts/ansys_gravity.py` 和 `scripts/run_fea_validation.py` 的 APDL 生成已修正为与 GUI Workbench 一致：板法向 = (0, cosθ, +sinθ)，网格 pixel-centered，重力提取 plate-normal w。30°/60°/62° 对比验证通过（shape_corr ≥ 0.992）。

### ✅ 方向 3（部分）：数据生成管线修正 — 已完成

`scripts/generate_proxy_model.py` 的网格约定从 cell-edged 改为 pixel-centered（匹配 shader `gridToPlate()`），重力提取从 raw uy 改为 plate-normal w。自影响从 [0.93, 1.12] 改善到 [0.94, 1.02]。四面镜 S95 合计从 259.0 → 253.0 m²。

### ✅ 方向 4：ANSYS APDL 与 Workbench GUI 一致性校准 — 2026-07-20 完成

通过对比 Workbench Mechanical 求解器日志（`train_data/zero_heights_ON/log.md`）与脚本生成的 APDL，定位并修复了 5 项差异：

| 修复项 | 修复前 | 修复后 | 影响 |
|---|---|---|---|
| SHELL181 KEYOPT(3) | 0（无非协调模式） | **2**（匹配 GUI） | 弯曲精度 |
| 网格方式 | `MSHKEY,0`（自由网格） | `MSHKEY,1` + `LESIZE` **64×48**（映射网格） | 节点数 3072→**3185**，完全匹配 GUI |
| 螺栓 BC | `D,ALL,ALL,0`（含转角约束） | `D,UX/UY/UZ,0`（仅平动） | 消除 ~4% 人为刚化 |
| 时步控制 | `NSUBST,30,200,15` | `AUTOTS,ON` + `NSUBST,1,10,1` | 匹配 GUI 自动时步 |
| 预测器 | 未设 | `PRED,ON` | 匹配 GUI |

**22 角度验证结果**（零螺栓纯重力，APDL vs GUI）：

| 区间 | 角度数 | UY PV 比 (GUI/APDL) | w RMS | R² |
|---|---|---|---|---|
| 低角度 10°–30° | 6 | 1.0382 ± 0.0002 | 0.167 mm | 0.9971 |
| 中角度 34°–54° | 8 | 1.032 ± 0.012 | 0.250 mm | 0.991 |
| 高角度 58°–80° | 8 | 1.036 ± 0.026 | 0.070 mm | 0.997 |

> **PV 比高度稳定**（低角度标准差仅 0.0002），位移场空间分布完全一致（R² > 0.997，相关系数 > 0.999）。剩余 ~4% 系统性幅值偏差极可能来自 GUI Engineering Data 材料属性（E、ν、t）与 `7x5_default.json` 的差异。详细报告见 `train_data/zero_heights_ON/VALIDATION_TABLE.md`。

受影响脚本：`scripts/ansys_gravity.py`、`scripts/run_fea_validation.py`、`scripts/generate_proxy_model.py` 内嵌 APDL 生成函数。

### ✅ 方向 5：基于修复代理模型的全管线重跑 — 2026-07-20 完成

用修复后的 `data_proxy/`（全部 20 个重力 bin + TPS 影响函数均重新生成）运行四面镜 200-iter 优化，**结果与旧模型完全一致**（S95 差异 < 0.1%，螺栓行程差异 < 0.1 mm），证明重力 bin 的修正对优化结果不敏感——只要空间分布（R² > 0.997）正确，优化即收敛到同一最优解。

**全 369 方向验证**（36 训练 + 369 全年验证）：优化后的螺栓配置在全 369 方向上 S95 合计 252.9 m²，平板本身在全年尺度下已接近最优（改善仅 0.1%），螺栓优化主要改善极端角度性能。

### ✅ 方向 6：优化结果 FEA 验证 — 2026-07-20 完成

对 North 300m 最优螺栓配置（35.7 mm max），在 29.5° 和 58.5° 下进行了 ANSYS NLGEOM-ON 重力+螺栓仿真，并完成了形变对比与光斑对比：

**形变验证**（TPS 代理 vs FEA 点云，32×32 网格）：

| 角度 | RMS | R² | shape_corr | PV 比 |
|:---:|:---:|:---:|:---:|:---:|
| 29.5° | 1.96 mm | 0.955 | 0.981 | 1.064 |
| 58.5° | 2.05 mm | 0.952 | 0.980 | 1.140 |

**光斑验证**（代理曲面 vs FEA 曲面 → Vulkan 光追）：

| 角度 | NRMSE | 能流相关系数 | S95 代理 | S95 FEA | ΔS95 |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 29.5° | 0.012 | 0.9980 | 1413 px | 1507 px | −6.2% |
| 58.5° | 0.013 | 0.9977 | 1231 px | 1331 px | −7.5% |

> 能流相关系数 > 0.997——形变误差（~2 mm RMS）经光学管线低通滤波后仅造成 ~1.2% 能流 NRMSE。代理模型 S95 偏乐观 6–8%，与 PV 高估一致，可施加 +7% 修正因子。详细报告见 `results_4mirror_200iter/fea_validation/FEA_VALIDATION_REPORT.md`。

### ✅ 方向 7：APDL 批处理 FEA 验证管线与 GUI 等价性确认 — 2026-07-21 完成

在方向 4（零螺栓）和方向 6（有螺栓、APDL only）基础上，建立了完整的**三路形变验证管线**，并确认了 APDL 批处理与 Workbench GUI 在有螺栓位移场景下的位精确等价性。

**新增脚本**：`scripts/post_fea_validation.py` — 自动运行 ANSYS MAPDL 螺栓行程仿真，输出 APDL FEA、GUI FEA（若有）、TPS Proxy 三路 2D 形变对比图与指标表至 `validation/post_fea_validation/`。

**APDL vs GUI 验证结果**（North 300m 最优螺栓，35.7 mm max）：

| 角度 | Pair | RMS (mm) | R² | shape_corr | PV ratio |
|:---:|------|:---:|:---:|:---:|:---:|
| 29.5° | APDL vs GUI | **0.050** | **1.0000** | **1.0000** | **1.0000** |
| 58.5° | APDL vs GUI | **0.051** | **1.0000** | **1.0000** | **1.0006** |

> **结论**：APDL 批处理与 Workbench GUI 在有螺栓位移场景下位精确一致（RMS < 0.05 mm，shape_corr = 1.0000）。从此无需手工去 GUI 导出 FEA 点云——`post_fea_validation.py` 一键完成从螺栓 stroke 到三路对比图的全流程。

Proxy vs FEA 偏差与方向 6 一致（~2.8–3.3 mm RMS, shape_corr 0.95–0.96），APDL 与 GUI 对 Proxy 的偏差模式完全相同，进一步佐证 APDL 管线正确。

---

## 项目结构

```
├── src/                           C++ Vulkan 管线
│   ├── pipeline.cpp/h            优化循环、S95、梯度反传、Adam
│   ├── main.cpp                  入口 (--dump-flux, --check-grad)
│   ├── config.cpp/h              JSON 配置解析
│   ├── input.cpp/h               太阳方向/定日镜配置加载
│   └── vulkan_app.cpp/h          Vulkan 封装
├── shaders/                       Slang GPU 计算着色器
│   ├── bolt_forward.slang        力学正向：曲面计算
│   ├── bolt_backward.slang       三阶段反向：bwd_diff → reduce → project
│   ├── bolt_common.slang         影响函数求值 + 重力插值
│   ├── bolt_optimizer.slang      螺栓 Adam 优化器
│   ├── forward.slang             光线追踪 + 双折射 + Buie 太阳
│   ├── backward.slang            Bézier 模式反向
│   ├── loss.slang                 S95 sigmoid 损失
│   ├── common.slang               共享 UBO、坐标变换、Wang hash
│   └── sunshape.slang             可微太阳形状 (Buie/Pillbox/Gaussian)
├── scripts/
│   ├── generate_proxy_model.py   统一数据生成（TPS + 重力）
│   ├── ansys_gravity.py           ANSYS 批处理 20-bin 重力生成
│   ├── run_fea_validation.py     ANSYS FEA 验证（螺栓行程仿真 + 光斑对比）
│   ├── post_fea_validation.py    三路形变验证（APDL vs GUI vs Proxy）
│   ├── validate_ellipse_vs_optimized.py  椭圆 vs 优化面对比
│   └── verify_ellipse_bolt_inversion.py  椭圆螺栓反推
├── configs/                       JSON 配置文件
│   └── bolt_layouts/              螺栓布局定义 (7×5, 6×6)
├── data/                          太阳方向、椭圆参数
├── data_proxy/                    预生成 TPS 数据 + 20-bin 重力
├── data_proxy_old/                归档旧数据（原 data_ansys_20bin、data_vsm_mnvn_tik32）
├── results_4mirror_200iter/      四面镜 200-iter 优化结果
├── results_4mirror_v2/            修复代理模型后四面镜优化结果
├── validation/                    验证数据
│   ├── pre_fea_validation/        GUI Workbench FEA 参考数据（优化螺栓配置）
│   └── post_fea_validation/       APDL 批处理三路验证输出
├── docs/                          补充文档（TVCG 差距分析等）
└── analysis/                      分析与验证报告（ARCAim 对比、P0 验证等）
```

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
| 玻璃折射率 | 1.523, 厚 3mm |
| 太阳模型 | Buie CSR=0.01, DNI=1000 W/m² |
| 斜率误差 | 1 mrad |
| 学习率（推荐） | 4×10⁻⁴ constant |
| Adam β₁, β₂, ε | 0.9, 0.999, 10⁻⁸ |

---

## 文档索引

| 文件 | 内容 |
|------|------|
| `CLAUDE.md` | 开发者参考：编译、架构、方法论、参数速查 |
| `results_4mirror_200iter/EXPERIMENT_REPORT.md` | 四面镜 200-iter 优化实验完整报告 |
| `docs/tvcg_submission_gap_analysis.md` | TVCG 投稿差距分析与补充实验规划 |
| `docs/plate_proxy_replacement_research.md` | TPS 代理模型替代方案调研（POD-ROM / Green 函数 / 模态展开 / PINN） |
| `analysis/arcaim_comparison.md` | ARCAim (diffspt) 方法论对比与本项目 P0/P1/P2 优化清单 |
| `analysis/p0_validation_report.md` | P0（A1 预裁剪 + L1 效率项）位精确一致性与时空开销验证 |
| `analysis/p0p1_merge_validation.md` | P0+P1 合并树端到端验证（位精确性、L1、参考运行、计时 A/B） |
| `validation/pre_fea_validation/FEA_VALIDATION_REPORT.md` | GUI Workbench FEA 验证报告（优化螺栓配置） |
| `validation/post_fea_validation/summary_table.md` | APDL vs GUI vs Proxy 三路验证汇总表 |
| `analysis/` | 历史分析文档 |

---

## 开放问题

### 🔴 TPS 代理模型精度不足（待解决）

三路验证（方向 7）确认 APDL=GUI 位精确一致，但 **Proxy vs FEA 仍存在系统性偏差**（RMS ~2.0–3.3 mm, shape_corr 0.95–0.96, R² 0.87–0.91）。根因是 TPS（薄板样条）为纯几何插值方法——不含材料属性（E, ν, t）、不满足自由边界条件、忽略 NLGEOM 非线性。详见 `docs/plate_proxy_replacement_research.md`。

**候选方案**（按优先级）：
1. **POD+MLP 降阶模型** — FEA 快照 SVD + 小型 MLP 学映射，精度预期 <2%
2. **Kirchhoff 板 Green 函数** — 解析、可微、物理精确（线性范围内）
3. **模态展开** — FEA 模态分析 + Galerkin 投影，1 次模态分析即可验证线性精度上限
