# bezier_opt — 物理可微分定日镜面型优化

基于 GPU 加速的可微分渲染管线，通过优化 35 根螺栓推拉高度最小化圆柱接收器上的 S95 光斑面积。采用 **TPS（薄板样条）物理代理模型**和 **FEA 重力场**，在局部板坐标系下实现严格线性的螺栓→曲面映射。

## 当前状态 (2026-07-08)

- ✅ **TPS 代理模型** — 替代已废弃的 VSM/MFS；单位分解 = 0（误差 < 10⁻⁶），vs FEA RMS = **1.50 mm**
- ✅ **重力模型** — FEA 直接提取 5 角度 bins (0°/30°/45°/60°/75°)，已知角度 RMS = **0.049 mm**
- ✅ **端到端优化** — TPS 影响函数 + 重力 + C++ Vulkan 光追 → S95 损失 → 反向传播 → Adam
- ✅ **面型验证** — TPS vs FEA at 58.5°: RMS=1.50mm, R²=0.92, 形状相关=0.96
- 🔄 **S95 调查中** — 初始 S95=228 m² vs 文献理想椭圆~43 m²，待排查

## 快速开始

```powershell
# 编译
$env:VULKAN_SDK = "C:\VulkanSDK\1.4.341.1"
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release

# 安装 Python 依赖
pip install numpy scipy matplotlib

# 生成 TPS 影响函数 (~1s)
python scripts/generate_tps_influence.py --output data_vsm_mnvn_tik25

# 运行优化 (50 轮, RTX 4070 ~2 分钟)
./build/src/Release/bezier_opt.exe configs/bolt_vsm_mnvn_50iter.json

# 强制重编译 shader
rm build/shaders/*.spv && cmake --build build --config Release
```

## 物理代理模型

### 核心公式（板局部坐标系）

$$w(\mathbf{r}) = UY_{\text{grav}}^{\text{FEA}}(\theta) + \sum_{b=1}^{N_b} h_b \cdot \phi_b^{\text{TPS}}(\mathbf{r})$$

- **无 cos(θ) 系数**：模型定义在板平面局部坐标系下。螺栓沿板法向推拉，φ_b 描述单位位移在此坐标系下的响应，dy/dh = φ 链式法则直接成立。
- **重力项** $UY_{\text{grav}}^{\text{FEA}}(\theta)$：从对应角度零螺栓 FEA 解中直接提取的局部坐标系 UY 值。5 个已知角度 (0°/30°/45°/60°/75°) 间线性插值。

### TPS 影响函数

通过 `scripts/generate_tps_influence.py` 生成。对每个螺栓 b，设 h_b=1（其余为 0），求解 TPS 系统：

$$A \cdot [c; d] = [\mathbf{e}_b; \mathbf{0}_3]$$

其中 $A = \begin{bmatrix} K & P \\ P^T & 0 \end{bmatrix}$，$K_{ij} = r_{ij}^2 \log(r_{ij}^2)$，$P = [\mathbf{1}, BX, BZ]$。

全板面响应 $φ_b(x,z) = Σ_j c_j·φ(r_j) + d₀ + d₁x + d₂z$ 即为影响函数。

**关键性质**：
- **单位分解**：Σ_b φ_b(x,z) ≡ 1（精度 ~10⁻⁶），保证物理正确的线性叠加
- **线性性**：TPS 对螺栓高度严格线性，φ_b = ∂w/∂h_b 定义良好
- **自影响**：均值 ~0.53（受 25×25 粗网格限制）

### 与 VSM 对比

| 性质 | TPS（当前） | MFS-Tikhonov（已废弃） |
|------|:---:|:---:|
| 单位分解 | **0.000** | 13.996 |
| 物理基础 | 无限大板点载荷 Green 函数 | 虚拟源点 + 边界配置 |
| 自影响 | 0.53 | 0.13 |
| 生成速度 | <1s (Python) | ~120s (Python SVD) |

### 重力模型（FEA-Direct + 角度插值）

重力分量直接取自对应角度零螺栓 FEA 解的局部坐标系下的 UY 值。

| 角度 | 源文件 | 局部 UY PV | bin 文件 |
|:---:|------|:---:|------|
| 0° | `zero_heights/node_dump_0deg.csv` | 16.8 mm | `gravity_0deg.bin` |
| 30° | `zero_heights/node_dump_30deg.csv` | 13.0 mm | `gravity_30deg.bin` |
| 45° | `zero_heights/node_dump_45deg.csv` | 8.6 mm | `gravity_45deg.bin` |
| 60° | `zero_heights/node_dump_60deg.csv` | 4.2 mm | `gravity_60deg.bin` |
| 75° | `zero_heights/node_dump_75deg.csv` | 1.0 mm | `gravity_75deg.bin` |

5 个已知角度间线性插值。验证结果：已知 bin RMS=0.049mm，插值 RMS=0.28mm。

### 面型验证结果

| 方法 | RMS (mm) | R² | 形状相关 | 状态 |
|------|:---:|:---:|:---:|:---:|
| **TPS Direct（本项目）** | **1.50** | **0.92** | **0.96** | ✅ |
| finite_difference | 4.60 | 0.25 | — | ❌ |
| baseline_tps | 7.20 | -0.82 | — | ❌ |
| global_tikhonov | 7.37 | -0.91 | — | ❌ |
| rayleigh_ritz | 173.1 | -1054 | — | ❌ |

## 数据流

```
螺栓高度 h[35] + 影响函数 φ_b/∂φ_b [35×625] + 5 角度重力 FEA bins
       ↓ boltForwardSurface() → GPU: computeBoltSurface
曲面 yGrid + 法向 nGrid + yuGrid + yvGrid (25×25)
       ↓ forwardRender() → GPU: clearFlux → renderForward → finalizeFlux
光追 (玻璃折射, Buie 太阳模型, MC 采样, 斜率误差)
       ↓
能流分布 renderedFlux (157×50)
       ↓ computeS95Level() [CPU 二分搜索] + computeS95Loss() [GPU sigmoid]
S95 sigmoid 损失 → fluxGradient (dL/dflux 逐像素)
       ↓ boltBackwardPass() 两阶段
  Stage 1: clearSurfaceGradient → renderBackwardBolt (bwd_diff)
           → reduceSurfaceGradients
           光学梯度: dL/dy_p, dL/dyu_p, dL/dyv_p 逐网格点累加
  Stage 2: projectBoltGradients
           力学梯度: dL/dh_b = Σ_p [dL/dy_p·φ_b + dL/dyu_p·∂φ_b/∂u + dL/dyv_p·∂φ_b/∂v]
       ↓ boltAdamStep() → GPU: adamUpdateBolt
h -= lr · m̂/(√v̂ + ε)
```

### 关键函数位置

| 步骤 | C++ 函数 | GPU Shader | 文件:行号 |
|------|----------|------------|-----------|
| 曲面计算 | `boltForwardSurface()` | `computeBoltSurface` | `bolt_forward.slang:16` |
| 光线追踪 | `forwardRender()` | `renderForward` | `forward.slang:83` |
| S95 阈值 | `computeS95Level()` | — (CPU) | `pipeline.cpp:1294` |
| S95 损失 | `computeS95Loss()` | `computeS95Loss` | `loss.slang:21` |
| 梯度清零 | `clearFluxGradient()` | `clearFluxGradient` | `loss.slang:32` |
| 曲面梯度清零 | — | `clearSurfaceGradient` | `bolt_backward.slang:226` |
| 光学反传 | — | `renderBackwardBolt` | `bolt_backward.slang:102` |
| 曲面梯度归约 | — | `reduceSurfaceGradients` | `bolt_backward.slang:180` |
| 螺栓投影 | — | `projectBoltGradients` | `bolt_backward.slang:207` |
| Adam 更新 | `boltAdamStep()` | `adamUpdateBolt` | `bolt_optimizer.slang:25` |
| 影响求值 | — | `boltSurfaceAtGrid` | `bolt_common.slang:83` |
| 重力插值 | — | `sampleGravityUY` | `bolt_common.slang:58` |

### 损失函数

| 损失 | 状态 | 说明 |
|------|:---:|------|
| **S95 sigmoid** | ✅ 使用中 | 平滑 S95 光斑面积损失 |
| **MSE** | ✅ 可选 | 匹配理想椭圆面型光斑 (`enable_mse_loss`) |
| 能量损失 | ❌ 已删除 | 能量守恒正则化 (已废弃) |
| 斜率损失 | ❌ 已删除 | Bézier 模式斜率约束 (已废弃) |
| 曲率损失 | ❌ 已删除 | 弯曲能量正则化 (已废弃) |
| RSD 损失 | ❌ 已删除 | CV² 方差损失 (已废弃) |
| L2 正则化 | ❌ 已删除 | 螺栓高度 L2 惩罚 (已废弃) |
| 正螺栓惩罚 | ❌ 已删除 | 螺栓正值约束 (已废弃) |

## 优化结果

| 配置 | 初始 S95 | 最优 S95 | 改善 | 迭代 |
|------|:---:|:---:|:---:|:---:|
| TPS（零初始化） | 228.5 m² | **98.1 m²** | 57.1% | 100 |

> **S95 计算调查中**：文献表明理想椭圆面型北300m S95≈43m²。当前零初始化即达228m²，数值偏高。S95 计算涉及：`src/pipeline.cpp:1294`（computeS95Level）、`shaders/loss.slang`（S95 sigmoid loss）。

## 项目结构

```
bezier_opt/
├── src/                           C++ Vulkan 管线
│   ├── pipeline.cpp/h            优化循环、S95 计算、梯度反传、Adam
│   ├── main.cpp                  入口（--dump-flux, --check-grad）
│   ├── config.cpp/h              JSON 配置解析
│   ├── input.cpp/h               太阳方向/定日镜配置加载
│   └── vulkan_app.cpp/h          Vulkan 封装
├── shaders/                       Slang GPU 计算着色器 (.slang + .spv)
│   ├── bolt_forward.slang        曲面计算（影响函数 + 重力）
│   ├── bolt_backward.slang       两阶段梯度反传
│   ├── bolt_common.slang         影响函数与重力求值
│   ├── bolt_optimizer.slang      螺栓 Adam 优化器
│   ├── forward.slang             光线追踪（玻璃折射、Buie、MC）
│   ├── backward.slang             Bézier 模式光学反传
│   ├── loss.slang                 S95 sigmoid 损失 + fluxGradient 清零
│   ├── optimizer.slang            Bézier 模式 Adam
│   ├── common.slang               共享 UBO、坐标变换、Bernstein 基
│   └── sunshape.slang             可微太阳形状（Buie/Pillbox/Gaussian）
├── scripts/
│   └── generate_tps_influence.py  TPS 影响函数 .bin 生成
├── proxy/
│   ├── tps_pipeline/              Python TPS 求解器 + 优化器
│   │   ├── tps_solver.py          TPSSolver (正算 + A_inv 反传)
│   │   ├── optimizer.py           Adam 优化器
│   │   ├── validate_surface.py    面型验证 vs FEA
│   │   ├── validate_flux.py       光斑验证
│   │   └── optimize_heliostat.py  完整优化管线
│   └── validation_utils.py        共享 FEA 对比工具
├── data_vsm_mnvn_tik25/           TPS 影响数据 + FEA 重力 bins
│   ├── influence_phi.bin          φ_b 位移 [35×25×25]
│   ├── influence_phi_u.bin        ∂φ/∂u x-斜率
│   ├── influence_phi_v.bin        ∂φ/∂v z-斜率
│   ├── gravity_{0,30,45,60,75}deg.bin  各角度 FEA 重力 UY
│   └── gravity_angles.json        重力角度索引
├── configs/                       JSON 优化配置文件
├── docs/                          设计文档
├── results_tps_pipeline/          TPS 优化输出
└── validation/                    FEA 验证数据
```

## 物理参数速查

| 参数 | 值 |
|------|-----|
| 镜面尺寸 | 12.84 × 9.45 m × 4 mm |
| 螺栓数 | 35 (7×5), 边距 8% |
| 渲染网格 | 25×25 |
| 接收器 | 圆柱 R=10m H=20m, 157×50 px |
| 板弯曲刚度 D | 392 N·m |
| 重力载荷 q | 98.1 N/m² |
| 玻璃折射率 | 1.523, 厚 3mm |
| 太阳模型 | Buie CSR=0.01, DNI=1000 W/m² |
| 斜率误差 | 1 mrad |
| 学习率 (零初始) | 2×10⁻⁴ |
| Adam β₁, β₂ | 0.9, 0.999 |

## 运行模式

```bash
# 完整优化 (TPS 影响函数, 当前默认)
./build/src/Release/bezier_opt.exe configs/bolt_vsm_mnvn_50iter.json      # 50 轮
./build/src/Release/bezier_opt.exe configs/bolt_vsm_mnvn_200iter.json    # 200 轮

# 光斑输出（完整 C++ Vulkan 光追，3 个太阳方向）
./build/src/Release/bezier_opt.exe --dump-flux --surface-file <path> <config>

# 梯度检验（螺栓模式）
./build/src/Release/bezier_opt.exe --check-grad <config>

# TPS 影响函数生成
python scripts/generate_tps_influence.py --output data_vsm_mnvn_tik25    # ~1s

# 面型验证（Python TPS vs FEA）
python proxy/tps_pipeline/validate_surface.py
```

## 螺栓坐标

7×5 网格，边距 8%：
- BU = [0.08, 0.22, 0.36, 0.50, 0.64, 0.78, 0.92]（7 列）
- BV = [0.08, 0.29, 0.50, 0.71, 0.92]（5 行）
- BX = (u-0.5)×W, BZ = (v-0.5)×L

## 螺栓后处理

```
h_pipe_final = h_opt - max(h_opt) - 0.5mm    (管线约定, 全部 ≤ -0.5mm)
h_phys       = -h_pipe_final                   (物理约定, 全部 ≥ +0.5mm)
h_stroke     = h_phys - min(h_phys)            (实际螺栓伸出量, 最短=0)
```

S95 不变。物理上等效于将螺栓安装基座沿负法向统一后移。

## 后续计划

| 优先级 | 方向 | 预期收益 | 难度 |
|:---:|------|:---:|:---:|
| P0 | 排查 S95 计算偏差 (228→43 m²) | 正确 S95 基线 | 低 |
| P0 | 椭圆初始化替代零初始化 | 降低初始 S95 | 低 |
| P0 | S95 驱动多角度优化 | 匹配文献最优值 | 中 |
| P1 | 多角度重力 + S95 端到端验证 | 物理正确性确认 | 中 |
| P2 | C++ shader 直接 TPS（替代 .bin 预计算） | 消除中间步骤 | 高 |
| P2 | Python S95 驱动优化（C++ 作光追后端） | 真正可微优化 | 中 |
