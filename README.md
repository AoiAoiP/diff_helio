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
# 默认配置（35 螺栓 7×5, 32×32 网格, 20-bin 重力）
python scripts/generate_proxy_model.py all

# 自定义螺栓布局
python scripts/generate_proxy_model.py all --bolt-layout configs/bolt_layouts/6x6.json

# 通过 ANSYS MAPDL 批量生成 20-bin 重力（需 ANSYS 许可证）
python scripts/generate_proxy_model.py all-ansys
```

输出至 `data_proxy/`（默认）：`influence_phi.bin`、`influence_phi_u/v.bin`、`gravity_{angle}deg.bin`（20 个角度）、`gravity_angles.json`、`gravity_y.bin`。

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

**日期**：2026-07-16 | **总耗时**：~20 min (1213s)

| 镜面 | 位置 | 初始 S95 | 最优 S95 | 改善 | 最大行程 | 收敛@iter |
|:---:|---|:---:|:---:|:---:|:---:|:---:|
| North | (0,0,−300) | 227.4 | **51.74** | 77.2% | 35.4 mm | ~70 |
| East | (300,0,0) | 214.4 | **66.61** | 68.9% | 35.6 mm | ~80 |
| South | (0,0,300) | 198.3 | **74.46** | 62.4% | 34.1 mm | ~50 |
| West | (−300,0,0) | 215.0 | **66.21** | 69.2% | 36.0 mm | ~90 |

**四面合计 S95：259.0 m²**

#### 收敛里程碑

| Iter | North | East | South | West |
|:---:|:---:|:---:|:---:|:---:|
| 0 | 227.4 | 214.4 | 198.3 | 215.0 |
| 30 | 80.7 | 87.8 | 88.0 | 87.2 |
| 50 | 59.8 | 70.8 | 75.7 | 70.9 |
| 70 | 52.2 | 66.9 | 74.5 | 66.6 |
| 100 | 51.9 | 66.7 | 74.5 | 66.3 |
| 150 | 51.8 | 66.6 | 74.5 | 66.2 |
| 200 | **51.7** | **66.6** | **74.5** | **66.2** |

> E/S/W 在 iter 50–80 已基本收敛，后续改善 <0.3 m²。若接受微小损失，可将 E/S/W 迭代缩至 100 iter，节省 50% 时间。

### 与旧方案对比（lr=2e-4→1e-7 线性衰减, 300 iter）

| 镜面 | 旧 S95 | 新 S95 | 改善 |
|------|:---:|:---:|:---:|
| North | 52.30 | **51.74** | +1.1% |
| East | 67.47 | **66.61** | +1.3% |
| South | 78.02 | **74.46** | +4.5% |
| West | 87.02 | **66.21** | **+23.9%** |

**关键发现**：West 改善最大 (+23.9%)——旧的衰减 lr 将其困在极差的局部极小值。恒定高 lr (4e-4) 配合 Adam 自身的 adaptivity 在所有方向上均优于线性衰减。

---

## 后续工作进展

### ✅ 方向 1：理想椭圆面 vs. TPS 拟合面的形变/光斑验证

**状态**：已完成（2026-07-16），详细报告见 `results_4mirror_200iter/EXPERIMENT_REPORT.md`。

**核心发现**：

**1. TPS 表示能力充分且一致**

四面镜的 LS−Ell RMS 均为精确的 **0.50 mm**，shape_corr 均 ≥ 0.9987。TPS 基函数对二次型椭圆面的表示能力不受镜面方位影响——模型误差仅为 ±0.5 mm RMS。

| 镜面 | LS−Ell RMS (mm) | Opt−Ell RMS (mm) | corr(LS, Ell) | corr(Opt, Ell) |
|------|:---:|:---:|:---:|:---:|
| North | 0.50 | 0.86 | 0.9989 | 0.9973 |
| East | 0.50 | 0.68 | 0.9989 | 0.9980 |
| South | 0.50 | 0.69 | 0.9987 | 0.9978 |
| West | 0.50 | 0.73 | 0.9988 | 0.9983 |

**2. 优化器主动偏离椭圆面型**

Opt−Ell RMS (0.68–0.86 mm) 始终大于 LS−Ell RMS (0.50 mm)。优化器为降低 S95 放弃最佳面型拟合，优先光学性能。North 偏离最大（0.86 mm）——正对接收器的几何关系对法向误差更敏感。

**3. 椭圆拟合面型 S95 vs 优化面型 S95**

| 镜面 | LS-fit S95 (m²) | Optimized S95 (m²) | Δ | Opt 优势 |
|------|:---:|:---:|:---:|:---:|
| North | 52.28 | **51.74** | +0.54 | 1.0% |
| East | 66.83 | **66.61** | +0.22 | 0.3% |
| South | 74.60 | **74.46** | +0.14 | 0.2% |
| West | 66.67 | **66.21** | +0.47 | 0.7% |

优化面型的 S95 **始终优于**椭圆拟合面型（Δ = 0.14–0.54 m²），验证了梯度优化的有效性。

### 🔄 方向 2：ANSYS FEA 验证（螺栓位移 → 变形点云）

**状态**：管线就绪，待讨论。`scripts/run_fea_validation.py` 已实现端到端 FEA 验证流程。

### 🔄 方向 3：程序性能分析与 Shader 优化

**状态**：P0-P2 shader 优化已在 `worktree-perf-optimization` 分支完成，包括：
- P0：消除 CAS 原子竞争（gradPartial 私槽 + reduce kernel）
- P1a：热路径 InterlockedAdd → groupshared + WaveActiveSum
- P1b：并行化 S95FindLevel（wave-level reduction）
- P2：合并 20 个 gravity binding 为单 buffer 直接索引

待重新编译并验证端到端性能数据。

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
