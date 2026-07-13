# diff_helio — 物理可微分定日镜面型优化

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![C++](https://img.shields.io/badge/C%2B%2B-23-blue.svg)](https://en.cppreference.com/)
[![Vulkan](https://img.shields.io/badge/Vulkan-1.4-red.svg)](https://www.vulkan.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-yellow.svg)](https://www.python.org/)

基于 **GPU 加速的可微分渲染管线**，通过优化 35 根螺栓推拉高度最小化圆柱接收器上的 S95 光斑面积。采用 **TPS（薄板样条）物理代理模型** + **FEA 重力场**，在局部板坐标系下实现严格线性的螺栓→曲面映射。全 GPU 自动微分支持端到端优化。

---

## 当前状态 (2026-07-09)

| 模块 | 状态 | 说明 |
|------|:---:|------|
| TPS 代理模型 | ✅ | 单位分解误差 < 10⁻⁶，自影响 ~1.0，vs FEA RMS = 2.45 mm |
| 重力模型 | ✅ | 10-bin 稠密 FEA 插值 (0°–75°)，已知 bin RMS = 0.049 mm |
| 端到端优化 | ✅ | 32×32 网格，S95 从 227 → **52.30 m²** (77% 改善, 300 iter) |
| 面型验证 | ✅ | 12°/35°/52° R² ≥ 0.96, shapeCorr ≥ 0.99, fluxCorr ≥ 0.998 |
| NLGEOM | ⚠️ | 线性螺栓项固有局限 ~1.3mm；gravity=ON 已确认正确 |

## 快速开始

### 环境要求

- **Windows** + Visual Studio 2022
- **Vulkan SDK** ≥ 1.4.341.1
- **CMake** ≥ 3.25
- **Python** ≥ 3.10 (numpy, scipy)

### 编译

```powershell
$env:VULKAN_SDK = "C:\VulkanSDK\1.4.341.1"
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

依赖项 (fmt, glm) 通过 CMake `FetchContent` 自动下载，无需手动安装。

强制重编译 shader：`rm build/shaders/*.spv && cmake --build build --config Release`

### 运行优化

```bash
# 生成 TPS 影响函数 (~1s)
python scripts/generate_tps_influence.py --output data_vsm_mnvn_tik32

# 运行优化 (300 轮, RTX 4070 SUPER ~22 分钟)
./build/src/Release/bezier_opt.exe configs/bolt_vsm_mnvn_300iter.json
```

### 其他运行模式

```bash
# 光斑输出（完整 C++ Vulkan 光追）
./build/src/Release/bezier_opt.exe --dump-flux --surface-file <path> <config>

# 梯度检验（螺栓模式）
./build/src/Release/bezier_opt.exe --check-grad <config>

# 四面镜优化
./build/src/Release/bezier_opt.exe configs/bolt_4mirror_swe.json
```

---

## 物理代理模型

### 核心公式（板局部坐标系）

$$w(\mathbf{r}) = UY_{\text{grav}}^{\text{FEA}}(\theta) + \sum_{b=1}^{N_b} h_b \cdot \phi_b^{\text{TPS}}(\mathbf{r})$$

模型定义在板平面局部坐标系下。重力项 $UY_{\text{grav}}^{\text{FEA}}(\theta)$ 由对应角度 FEA 结果插值而得，后一项**无需乘 cos(θ)**——螺栓沿板法向推拉，$\phi_b$ 描述单位位移在此坐标系下的响应，$dy/dh = \phi$ 链式法则直接成立。计算出局部坐标系下的板方程 $w(\mathbf{r})$ 后，经 local→world 变换转换到世界坐标系进行光线追踪。

### TPS 影响函数

通过 `scripts/generate_tps_influence.py` 离线预计算（< 1s），对每个螺栓 b 设 h_b=1（其余为 0），求解 TPS 系统：

$$A \cdot [c; d] = [\mathbf{e}_b; \mathbf{0}_3], \quad A = \begin{bmatrix} K & P \\ P^T & 0 \end{bmatrix}$$

其中 $K_{ij} = r_{ij}^2 \log(r_{ij}^2)$（无限大板点载荷 Green 函数），$P = [\mathbf{1}, BX, BZ]$，对角加 Tikhonov 正则（λ = 1e⁻⁶）。全板面响应 $\phi_b(x,z) = \sum_j c_j \cdot r^2\log(r^2) + d_0 + d_1x + d_2z$ 即为影响函数。

一阶导数按**归一化坐标**解析给出（供 shader 求法向），与网格分辨率无关：

$$\partial\phi_b/\partial u = \partial\phi_b/\partial x \cdot W, \quad \partial\phi_b/\partial v = \partial\phi_b/\partial z \cdot L$$

**关键性质（32×32 实测）**：
- **单位分解**：$\sum_b \phi_b(x,z) \equiv 1$，PV ≈ 1.3×10⁻⁶ — 保证物理正确的线性叠加
- **线性性**：TPS 对螺栓高度严格线性，$\phi_b = \partial w/\partial h_b$ 定义良好
- **自影响**：均值 **1.007**，范围 [0.93, 1.12]，34/35 螺栓 > 0.95
- **系统规模**：38×38（35 螺栓 + 3 多项式），条件数 ~4.2×10⁶

### 重力模型（FEA-Direct + 角度插值）

重力分量直接取自对应角度零螺栓 FEA 解（NLGEOM-ON）的局部坐标系 UY 值。10 个已知角度间线性插值（间距 ≤ 15°）。

| 角度 | 局部 UY PV | bin 文件 |
|:---:|:---:|------|
| 0° | 16.8 mm | `gravity_0deg.bin` |
| 12° | 16.2 mm | `gravity_12deg.bin` |
| 22° | 14.7 mm | `gravity_22deg.bin` |
| 30° | 13.0 mm | `gravity_30deg.bin` |
| 35° | 11.8 mm | `gravity_35deg.bin` |
| 45° | 8.6 mm | `gravity_45deg.bin` |
| 52° | 6.6 mm | `gravity_52deg.bin` |
| 60° | 4.2 mm | `gravity_60deg.bin` |
| 67° | 2.4 mm | `gravity_67deg.bin` |
| 75° | 1.0 mm | `gravity_75deg.bin` |

### 面型验证结果

| 条件 | RMS | R² | PV_ratio | shape_corr |
|------|:---:|:---:|:---:|:---:|
| 0° 无重力 | **2.45 mm** | **0.938** | 1.20 | 0.981 |
| 0° 重力 | 3.69 mm | 0.844 | 1.01 | 0.929 |
| 29.5° 重力 | 3.77 mm | 0.832 | 1.04 | 0.928 |
| 58.5° 重力 | 3.59 mm | 0.850 | 1.14 | 0.945 |

### 光斑验证（29.5°, 天顶太阳）

| 指标 | TPS Proxy | FEA |
|------|:---:|:---:|
| 峰值能流 | 620 W/m² | 613 W/m² |
| 总能量 | 424,240 | 423,344 |
| S95 像素 | 1,492 px | 1,702 px |

### 废弃方法对比

| 方法 | RMS (mm) | R² | 形状相关 | 状态 |
|------|:---:|:---:|:---:|:---:|
| **TPS Direct（本项目）** | **2.45** | **0.94** | **0.98** | ✅ |
| finite_difference | 4.60 | 0.25 | — | ❌ |
| baseline_tps | 7.20 | -0.82 | — | ❌ |
| global_tikhonov | 7.37 | -0.91 | — | ❌ |
| rayleigh_ritz | 173.1 | -1054 | — | ❌ |

---

## 管线数据流

```
螺栓高度 h[35] + 影响函数 φ_b/∂φ_b [35×1024] + 10-bin 重力 FEA bins
       ↓ boltForwardSurface() → GPU: computeBoltSurface
曲面 yGrid + 法向 nGrid + yuGrid + yvGrid (32×32)
       ↓ forwardRender() → GPU: clearFlux → renderForward → finalizeFlux
光线追踪 (玻璃双折射, Buie CSR=0.01 太阳, Sobol MC, 1 mrad 斜率误差)
       ↓
能流分布 renderedFlux (157×50)
       ↓ computeS95Level() [CPU 二分搜索] + computeS95Loss() [GPU sigmoid]
S95 sigmoid 损失 → fluxGradient (dL/dflux 逐像素)
       ↓ boltBackwardPass() 三阶段
  Stage 0: clearSurfaceGradient
  Stage 1: renderBackwardBolt (自微分光追 + wave-reduce)
           → reduceSurfaceGradients (跨 group 归约)
           光学梯度: dL/dy_p, dL/dyu_p, dL/dyv_p 逐网格点累加
  Stage 2: projectBoltGradients
           力学梯度: dL/dh_b = Σ_p [dL/dy_p·φ_b + dL/dyu_p·∂φ_b/∂u + dL/dyv_p·∂φ_b/∂v]
       ↓ boltAdamStep() → GPU: adamUpdateBolt
h -= lr · m̂/(√v̂ + ε)
```

**梯度链**（链式法则沿数据流反向传播）：

$$\frac{\partial L}{\partial h_b} = \sum_{\text{sun}} \sum_{p} \left[ \frac{\partial L}{\partial\text{flux}} \cdot \left( \frac{\partial\text{flux}}{\partial y} \cdot \phi_b(p) + \frac{\partial\text{flux}}{\partial y_u} \cdot \frac{\partial\phi_b}{\partial u}(p) + \frac{\partial\text{flux}}{\partial y_v} \cdot \frac{\partial\phi_b}{\partial v}(p) \right) \right]$$

### 损失函数

| 损失 | 状态 | 公式 |
|------|:---:|------|
| **S95 sigmoid** | ✅ 使用中 | $s = \sigma(6 \cdot (\text{flux}/\text{level} - 1))$ |
| **MSE** | ✅ 可选 | $2(\text{flux} - \text{ideal}) / N_{\text{pix}}$ |

### 关键源文件

| 步骤 | C++ 函数 | GPU Shader | 文件 |
|------|----------|------------|------|
| 曲面计算 | `boltForwardSurface()` | `computeBoltSurface` | `bolt_forward.slang` |
| 光线追踪 | `forwardRender()` | `renderForward` | `forward.slang` |
| S95 阈值 | `computeS95Level()` | — (CPU) | `pipeline.cpp` |
| S95 损失 | — | `computeS95Loss` | `loss.slang` |
| 光学反传 | `boltBackwardPass()` | `renderBackwardBolt` | `bolt_backward.slang` |
| 曲面梯度归约 | — | `reduceSurfaceGradients` | `bolt_backward.slang` |
| 螺栓投影 | — | `projectBoltGradients` | `bolt_backward.slang` |
| Adam 更新 | `boltAdamStep()` | `adamUpdateBolt` | `bolt_optimizer.slang` |
| 影响函数求值 | — | `boltSurfaceAtGrid` | `bolt_common.slang` |
| 重力插值 | — | `sampleGravityUY` | `bolt_common.slang` |

### S95 计算

- **阈值**：`computeS95Level()` — 二分搜索找到 95% 能量对应的能流阈值
- **面积**：`pixelArea = 2πRH / totalPixels = 0.1601 m²/pixel`（圆柱接收器 R=10m, H=20m）
- **损失**：sigmoid 平滑阶跃 $s = \sigma(6 \cdot (\text{flux}/\text{level} - 1))$，$dL/d\text{flux} = 6s(1-s)/\text{level}$

---

## 优化结果

### North 300m（当前主结果）

| 配置 | 分辨率 | 初始 S95 | 最优 S95 | 改善 | 迭代 |
|------|:---:|:---:|:---:|:---:|:---:|
| TPS 零初始化 | 25×25 | ~228 m² | **~53 m²** | ~77% | — |
| **TPS 零初始化（修复后）** | **32×32** | 227.4 m² | **52.30 m²** | **77.0%** | 300 |

> ⚠️ **S95 数值偏高**：文献理想椭圆面型北 300m S95 ≈ 43 m²，当前零初始化即达 ~228 m²。涉及 `computeS95Level`(pipeline.cpp)、`pixelArea`、sigmoid loss。

### 四面镜优化 (E/S/W/N 300m, 32×32, 300 轮, 零初始化)

| 镜 | 位置 | 初始 S95 | 最优 S95 | 改善 | 最大行程 |
|:---:|---|:---:|:---:|:---:|:---:|
| North | (0, 0, −300) | 227.4 | **52.30** | 77.0% | 32.87 mm |
| East | (300, 0, 0) | 214.6 | **67.47** | 68.6% | 32.71 mm |
| South | (0, 0, 300) | 198.4 | **78.02** | 60.7% | 36.65 mm |
| West | (−300, 0, 0) | 214.4 | **87.02** | 59.4% | 38.49 mm |

- 每镜独立 `aimPoint` 和 `heliostatPosition`，宏观法向随位置变化
- E/W 不对称来自太阳方向集东西不对称 + 椭圆目标参数略异
- West 行程最大 (38.5mm ≈ 9.6× 板厚)，NLGEOM 效应预期最强

---

## 项目结构

```
diff_helio/
├── src/                           C++ Vulkan 管线
│   ├── pipeline.cpp/h            优化循环、S95、梯度反传、Adam
│   ├── main.cpp                  入口 (--dump-flux, --check-grad)
│   ├── config.cpp/h              JSON 配置解析
│   ├── input.cpp/h               太阳方向/定日镜配置加载
│   └── vulkan_app.cpp/h          Vulkan 封装
├── shaders/                       Slang GPU 计算着色器 (.slang)
│   ├── bolt_forward.slang        力学正向：曲面计算
│   ├── bolt_backward.slang       三阶段光学反向传播
│   ├── bolt_common.slang         影响函数与重力求值
│   ├── bolt_optimizer.slang      螺栓 Adam 优化器
│   ├── forward.slang             光学正向：光线追踪
│   ├── backward.slang             Bézier 模式光学反传
│   ├── loss.slang                 S95 sigmoid 损失
│   ├── loss_gpu.slang             GPU 侧损失归约
│   ├── optimizer.slang            Bézier 模式 Adam
│   ├── common.slang               共享 UBO、坐标变换
│   ├── sunshape.slang             可微太阳形状 (Buie/Pillbox/Gaussian)
│   └── wos_*.slang                WoS 离线影响函数计算
├── proxy/                         Python 参考管线
│   ├── tps_pipeline/
│   │   ├── tps_solver.py         可微 TPS 求解器 (A_inv 反传)
│   │   ├── optimizer.py           Adam 优化器
│   │   ├── validate_surface.py    面型验证 vs FEA
│   │   ├── validate_flux.py       光斑验证
│   │   └── optimize_heliostat.py  完整优化管线
│   └── validation_utils.py        共享 FEA 对比工具
├── scripts/
│   ├── generate_tps_influence.py  TPS 影响函数 .bin 生成
│   └── train_residual/
│       └── precompute_gravity_bins.py  重力 bin 生成
├── data/                          太阳方向、椭圆参数、初始螺栓高度
├── data_vsm_mnvn_tik32/           预生成 TPS 数据 (32×32)
│   ├── influence_phi.bin          φ_b 位移 [35×32×32]
│   ├── influence_phi_u/v.bin      一阶导数
│   ├── influence_kxx/kzz/kxz.bin  二阶导 (仅 Python 用)
│   ├── gravity_{0..75}deg.bin     10 角度 FEA 重力 UY
│   ├── gravity_y.bin              重力插值辅助数据
│   └── gravity_angles.json        重力角度索引
└── configs/                       JSON 优化配置文件
```

---

## 物理参数速查

| 参数 | 值 |
|------|-----|
| 镜面尺寸 | 12.84 × 9.45 m × 4 mm |
| 螺栓数 | 35 (7×5), 边距 8% |
| 渲染网格 | 32×32 |
| 接收器 | 圆柱 R=10m H=20m, 157×50 px |
| 板弯曲刚度 D | 392 N·m |
| 重力载荷 q | 98.1 N/m² |
| 玻璃折射率 | 1.523, 厚 3mm |
| 太阳模型 | Buie CSR=0.01, DNI=1000 W/m² |
| 斜率误差 | 1 mrad |
| 学习率 (零初始) | 2×10⁻⁴ → 1×10⁻⁷ (线性衰减) |
| Adam β₁, β₂, ε | 0.9, 0.999, 10⁻⁸ |

## 螺栓坐标

7×5 网格，边距 8%：
- BU = [0.08, 0.22, 0.36, 0.50, 0.64, 0.78, 0.92]（7 列）
- BV = [0.08, 0.29, 0.50, 0.71, 0.92]（5 行）
- BX = (u−0.5)×W, BZ = (v−0.5)×L

### 后处理约定

```
h_pipe_final = h_opt - max(h_opt) - 0.5mm    (管线约定, 全部 ≤ −0.5mm)
h_phys       = -h_pipe_final                   (物理约定, 全部 ≥ +0.5mm)
h_stroke     = h_phys - min(h_phys)            (实际螺栓伸出量, 最短 = 0)
```

S95 不变。物理上等效于将螺栓安装基座沿负法向统一后移。

---

## 性能参考 (RTX 4070 SUPER, 32×32, 10-bin)

| 指标 | 数值 |
|------|------|
| 像素 | 7,850 (157×50) |
| 每像素 SPP | 1,024 (32² grid) |
| 每 iter 光线 (forward, 36 sun) | 289.4 M |
| 每 iter 总光线 (fwd + backward) | ~0.58 B |
| 300 iter 总光线 | ~174 B |
| 每 iter 平均 | ~5.4s |
| 光线吞吐 (forward) | ~55 M rays/s |
| 总耗时 (300 iter) | ~22 min |
| GPU 显存占用 | ~650 MB |

**瓶颈**：forwardRender (~55%) + boltBackward (~35%)。最大加速方向为多 sun 并行 + 直接累加器归约（预期 22min → 8–10min）。

---

## 后续方向

| 优先级 | 方向 | 说明 | 难度 |
|:---:|------|------|:---:|
| P0 | 排查 S95 数值偏高 | 零初始 ~228 vs 文献理想椭圆 ~43 m² | 中 |
| P0 | 椭圆初始化替代零初始化 | 降低初始 S95 | 低 |
| P1 | 螺栓驱动 NLGEOM 修正 | 消除剩余 ~1.3mm 面型误差 | 高 |
| P1 | gravity bins 溯源统一 | 用当前 `zero_heights_ON` 重生成 bins | 低 |
| P2 | 32×32 多角度端到端 S95 验证 | NLGEOM + gravity=ON 最终物理确认 | 中 |
| P2 | C++ shader 直接 TPS | 替代 .bin 预计算，支持任意分辨率 | 高 |
| P2 | 多 sun 并行 + 直接累加器归约 | 消除 gradPartial 386MB 缓冲，~2× 加速 | 中 |

---

## 引用

本项目基于 TPS 薄板样条代理模型 + GPU 自动微分光追。核心方法见 [CLAUDE.md](CLAUDE.md)，包含完整的数据流推导、NLGEOM 分析、kernel 修正历史和性能分析。
