# Diff Helio — 可微定日镜面型优化

基于 **Vulkan GPU 光线追踪 + Slang 自动微分**的定日镜螺栓调高优化管线。通过 TPS（薄板样条）物理代理模型将 35 根螺栓推拉高度映射为镜面变形，最小化圆柱接收器上的 S95 光斑面积。

---

## 快速开始

### 环境要求

- Windows, Visual Studio 2022, CMake ≥ 3.20
- Vulkan SDK ≥ 1.4.341.1
- Python ≥ 3.10 (numpy, scipy) — 仅数据准备
- NVIDIA GPU（测试：RTX 4070 SUPER 12GB）

### 编译

```powershell
$env:VULKAN_SDK = "C:\VulkanSDK\1.4.341.1"
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
    → 能流分布 → CPU S95 阈值 → sigmoid 损失
    → Slang bwd_diff 反传 → 螺栓梯度 → Adam 更新
```

梯度通过 Slang 自动微分精确计算，重放完整光路（包括双折射和太阳形状）。

### 损失函数

S95 sigmoid 损失：$L = \sum_{\text{pixel}} \sigma\big(6 \cdot (\text{flux} / \text{S95}_{\text{level}} - 1)\big)$，其中 S95 阈值为包含 95% 总能量的最低能流水平（CPU 端二分搜索计算）。

---

## 实验结果

### 四面镜 300m（200 iter, lr=4e-4 constant, 零初始化）

**日期**：2026-07-17 | **数据**：`data_proxy/`（pixel-centered + plate-normal gravity + GUI-apdl） | **总耗时**：~20 min

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
│   ├── run_fea_validation.py     ANSYS FEA 验证
│   ├── validate_ellipse_vs_optimized.py  椭圆 vs 优化面对比
│   └── verify_ellipse_bolt_inversion.py  椭圆螺栓反推
├── configs/                       JSON 配置文件
│   └── bolt_layouts/              螺栓布局定义 (7×5, 6×6)
├── data/                          太阳方向、椭圆参数
├── data_proxy/                    预生成 TPS 数据 + 20-bin 重力
├── results_4mirror_200iter/      四面镜 200-iter 优化结果
├── docs/                          补充文档（TVCG 差距分析等）
└── analysis/                      历史分析文档
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
| `analysis/` | 历史分析文档 |
