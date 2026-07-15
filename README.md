# diff_helio — 物理可微分定日镜面型优化

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![C++](https://img.shields.io/badge/C%2B%2B-23-blue.svg)](https://en.cppreference.com/)
[![Vulkan](https://img.shields.io/badge/Vulkan-1.4-red.svg)](https://www.vulkan.org/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-yellow.svg)](https://www.python.org/)

基于 **GPU 加速的可微分渲染管线**，通过优化 35 根螺栓推拉高度最小化圆柱接收器上的 S95 光斑面积。采用 **TPS（薄板样条）物理代理模型** + **FEA 重力场**，在局部板坐标系下实现严格线性的螺栓→曲面映射。全 GPU 自动微分（Slang `bwd_diff`）支持端到端优化。

---

## 当前状态 (2026-07-15)

| 模块 | 状态 | 说明 |
|------|:---:|------|
| TPS 代理模型 | ✅ | 单位分解误差 < 10⁻⁶，自影响 ~1.0 |
| 重力模型 | ✅ | 20-bin FEA 插值 (10°–80°)，已知 bin 可用 |
| 端到端优化 | ✅ | 32×32 网格，S95 从 227 → **52.35 m²** (77% 改善, 300 iter) |
| 梯度验证 | ✅ | AD/FD sign=88.6%, cosine=0.97 (alt init) |
| 性能优化 | ✅ | Phase 1/2/5 已完成，532s/300iter, ~720 MB VRAM |

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

依赖项 (fmt, glm, Slang) 通过 CMake `FetchContent` 自动下载，无需手动安装。

强制重编译 shader：`rm build/shaders/*.spv && cmake --build build --config Release`

### 运行优化

```bash
# 生成 TPS 影响函数 (~1s)
python scripts/generate_tps_influence.py --output data_vsm_mnvn_tik32

# 运行优化 (300 轮, RTX 4070 SUPER ~9 分钟)
./build/src/Release/bezier_opt.exe configs/bolt_vsm_mnvn_300iter.json
```

### 其他运行模式

```bash
# 光斑输出（完整 C++ Vulkan 光追）
./build/src/Release/bezier_opt.exe --dump-flux --surface-file <path> <config>

# 梯度检验（螺栓模式）
./build/src/Release/bezier_opt.exe --check-grad <config>
```

---

## 管线数据流

```
螺栓高度 h[35] + 影响函数 φ_b/∂φ_b [35×1024] + 20-bin 重力 FEA bins
       ↓ boltForwardSurface() → GPU: computeBoltSurface
曲面 yGrid + 法向 nGrid + yuGrid + yvGrid (32×32)
       ↓ forwardRender() → GPU: clearFlux → renderForward → finalizeFlux
光线追踪 (玻璃双折射, Buie CSR=0.01 太阳, Wang hash + Box-Muller, 1 mrad 斜率误差)
       ↓
能流分布 renderedFlux (157×50)
       ↓ readFlux() → computeS95Level() [CPU 二分搜索]
       ↓ computeS95Loss() [GPU sigmoid 梯度写入 fluxGradient]
S95 sigmoid 损失 → fluxGradient (dL/dflux 逐像素)
       ↓ boltBackwardPassCmd() 两阶段 (单 command buffer)
  Stage 1: renderBackwardBolt (自微分光追)
           → InterlockedAdd 到 gradPartialTile (12 KB 定点数累加器)
  Stage 2: reduceSurfaceGradients (int→float 转换, 写入 surfaceGradient)
  Stage 3: projectBoltGradients
           力学梯度: dL/dh_b = Σ_p [dL/dy_p·φ_b + dL/dyu_p·∂φ_b/∂u + dL/dyv_p·∂φ_b/∂v]
       ↓ boltAdamStep() → GPU: adamUpdateBolt
h -= lr · m̂/(√v̂ + ε)
```

**梯度链**（链式法则沿数据流反向传播）：

$$\frac{\partial L}{\partial h_b} = \sum_{\text{sun}} \sum_{p} \left[ \frac{\partial L}{\partial\text{flux}} \cdot \left( \frac{\partial\text{flux}}{\partial y} \cdot \phi_b(p) + \frac{\partial\text{flux}}{\partial y_u} \cdot \frac{\partial\phi_b}{\partial u}(p) + \frac{\partial\text{flux}}{\partial y_v} \cdot \frac{\partial\phi_b}{\partial v}(p) \right) \right]$$

### 损失函数

| 损失 | 状态 | 公式 |
|------|:---:|------|
| **S95 sigmoid** | ✅ 默认 | $L = \sum_p \sigma\bigl(6 \cdot (f_p / \text{level} - 1)\bigr)$, $dL/df = 6s(1-s)/\text{level}$ |
| **MSE (理想椭圆)** | 可选 | $L = \frac{1}{N}\sum_p (f_p - f_p^{\text{ideal}})^2$ |

### S95 计算

- **阈值**：`computeS95Level()` — CPU 二分搜索找到 95% 能量对应的能流阈值
- **面积**：`S95 = N_{f≥level} × pixelArea`, `pixelArea = 2πRH / totalPixels`（圆柱 R=10m, H=20m）
- **为什么用 CPU**：GPU 256-bin 直方图 (~3.1 W/m²/bin) 产生 ~1.5 W/m² 系统偏差，导致 sigmoid 损失过早饱和。CPU 二分搜索使用精确浮点值

### 关键源文件

| 步骤 | C++ 函数 | GPU Shader | 文件 |
|------|----------|------------|------|
| 曲面计算 | `boltForwardSurfaceCmd()` | `computeBoltSurface` | `bolt_forward.slang` |
| 光线追踪 | `forwardRenderCmd()` | `renderForward` | `forward.slang` |
| S95 阈值 | `computeS95Level()` | — (CPU) | `pipeline.cpp` |
| S95 损失梯度 | `computeS95LossCmd()` | `computeS95Loss` | `loss.slang` |
| 光学反传 | `boltBackwardPassCmd()` | `renderBackwardBolt` | `bolt_backward.slang` |
| 定点数归约 | — | `reduceSurfaceGradients` | `bolt_backward.slang` |
| 螺栓投影 | — | `projectBoltGradients` | `bolt_backward.slang` |
| Adam 更新 | `boltAdamStep()` | `adamUpdateBolt` | `bolt_optimizer.slang` |
| 影响函数求值 | — | `boltSurfaceAtGrid` | `bolt_common.slang` |
| 重力插值 | — | `sampleGravityUY` | `bolt_common.slang` |

---

## 优化结果

### North 300m

| 配置 | 初始 S95 | 最优 S95 | 改善 | 螺栓行程 | 耗时 | 显存 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| TPS 零初始化, 32×32, 300 iter | 227.36 m² | **52.35 m²** | 77.0% | 33.00 mm | 532s (8.9 min) | ~720 MB |

> S95=52.35 m² 是当前 TPS+Vulkan 渲染器在此定日镜配置下的物理正确结果。与其他渲染器（Taichi、MCRT）的 S95 数值不可直接比较——S95 算法对渲染噪声、接收器离散化、太阳模型实现的差异敏感。

---

## 物理代理模型

### 核心公式（板局部坐标系）

$$w(\mathbf{r}) = UY_{\text{grav}}^{\text{FEA}}(\theta) + \sum_{b=1}^{N_b} h_b \cdot \phi_b^{\text{TPS}}(\mathbf{r})$$

模型定义在板平面局部坐标系下。重力项 $UY_{\text{grav}}^{\text{FEA}}(\theta)$ 由对应角度 FEA 结果插值而得。$\phi_b$ 描述单位螺栓位移在此坐标系下的响应，$dy/dh = \phi$ 链式法则直接成立。

### TPS 影响函数

通过 `scripts/generate_tps_influence.py` 离线预计算（< 1s），求解 TPS 系统：

$$A \cdot [c; d] = [\mathbf{e}_b; \mathbf{0}_3], \quad A = \begin{bmatrix} K & P \\ P^T & 0 \end{bmatrix}$$

其中 $K_{ij} = r_{ij}^2 \log(r_{ij}^2)$（无限大板点载荷 Green 函数），$P = [\mathbf{1}, BX, BZ]$，Tikhonov 正则 λ = 1e⁻⁶。

**关键性质（32×32 实测）**：
- **单位分解**：$\sum_b \phi_b(x,z) \equiv 1$，保证物理正确的线性叠加
- **自影响**：均值 1.007，范围 [0.93, 1.12]
- **系统规模**：38×38（35 螺栓 + 3 多项式），条件数 ~4.2×10⁶

### 重力模型（FEA-Direct + 角度插值）

20 个角度 FEA 解（NLGEOM-ON，10°/14°/18°/.../78°/80°），shader 侧双线性插值。重力分量直接取自对应角度零螺栓 FEA 解的局部坐标系 UY 值。

---

## 性能优化历程

| 阶段 | 名称 | 状态 | 每迭代 | 显存节省 | 说明 |
|:---:|------|:---:|:---:|:---:|------|
| — | 基线 | — | 3.9s | — | Sobol 1.5GB + gradPartial 386MB |
| **1** | 内联 Box-Muller | ✅ | — | −1,500 MB | Wang hash + Box-Muller 替代 Sobol 池 |
| **2** | Command Buffer 合批 | ✅ | — | — | RawComputePass, 消除 per-dispatch fence |
| **3** | GPU S95 | ❌ 跳过 | — | — | GPU 直方图偏差导致 Loss 饱和 (见下方) |
| **4** | 多太阳 Push Constants | ❌ 跳过 | — | — | 性能退步, 未来可重新评估 |
| **5** | gradPartial 归约 | ✅ | **1.8s** | −386 MB | InterlockedAdd 定点数, 12KB gradPartialTile |

### GPU S95 回归 (Phase 3) — 教训

Phase 3 引入的 GPU 端 S95 直方图 (`computeS95LevelGPU`) 使用 256-bin 固定范围，产生 ~1.5 W/m² 的系统偏差。S95 sigmoid 损失函数对 level 参数极其敏感——1.5 W/m² 的偏差导致 Loss 在 iter 20-40 过早归零，优化器失去梯度信号，S95 止步于 ~115 m²。**修复**：保留 CPU 端 S95 计算路径，`readFlux` 每 sun 仅增加 ~0.5ms 开销。

### Phase 5 技术要点

Slang 的 `InterlockedCompareExchange` (CAS) 在包含 `bwd_diff` auto-diff 的 shader 中生成不执行的 SPIR-V（编译器 bug），但 `InterlockedAdd` 正常工作。通过定点数方案绕过：
- 梯度 × 1e4 → `int` → `uint` (二进制补码)，`InterlockedAdd` 原子累加到 12 KB `gradPartialTile`
- `reduceSurfaceGradients` 读取 `int` 恢复符号，÷1e4 转回 `float`

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
│   ├── bolt_backward.slang       光学反向传播 (InterlockedAdd 归约)
│   ├── bolt_common.slang         影响函数与重力求值
│   ├── bolt_optimizer.slang      螺栓 Adam 优化器
│   ├── forward.slang             光学正向：光线追踪
│   ├── backward.slang             Bézier 模式光学反传
│   ├── loss.slang                 S95 sigmoid 损失 (梯度 + 计数)
│   ├── loss_gpu.slang             GPU 侧损失归约 (仅显示用)
│   ├── s95_histogram.slang        GPU S95 直方图 (未使用, 有偏差)
│   ├── optimizer.slang            Bézier 模式 Adam
│   ├── common.slang               共享 UBO、坐标变换、Box-Muller
│   ├── sunshape.slang             可微太阳形状 (Buie/Pillbox/Gaussian)
│   └── wos_*.slang                WoS 离线影响函数计算
├── scripts/
│   ├── generate_tps_influence.py  TPS 影响函数 .bin 生成
│   └── ansys_gravity.py           ANSYS MAPDL 批量重力仿真
├── data/                          太阳方向、椭圆参数
├── data_vsm_mnvn_tik32/           预生成 TPS 数据 (32×32)
│   ├── influence_phi.bin          φ_b 位移 [35×32×32]
│   ├── influence_phi_u/v.bin      一阶导数
│   └── gravity_{10..80}deg.bin    20 角度 FEA 重力 UY
├── configs/                       JSON 优化配置文件
│   ├── bolt_vsm_mnvn_300iter.json 主配置 (300 iter, lr=2e-4)
│   ├── bolt_layouts/              螺栓布局 (7×5, 6×6)
│   └── bolt_4mirror_swe.json     四面镜配置
├── optimization_plan.md           分阶段优化方案与修复文档
├── CLAUDE.md                      详细方法论与参数速查
└── README.md                      本文件
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

### 螺栓坐标

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

---

## 性能参考 (RTX 4070 SUPER, 32×32, 20-bin)

| 指标 | 数值 |
|------|------|
| 像素 / 每像素 SPP | 7,850 / 1,024 (32²) |
| 每 iter 光线 (fwd+bwd, 36 sun) | ~0.58 B |
| 300 iter 总光线 | ~174 B |
| 每 iter 平均 | **1.8s** |
| 总耗时 (300 iter) | **532s (~9 min)** |
| GPU 显存占用 | ~720 MB |

**瓶颈分布**：forwardRender ~55%, boltBackward ~35%, boltForwardSurface <5%, 其他 ~5%

---

## 后续方向

| 优先级 | 方向 | 说明 |
|:---:|------|------|
| P0 | 椭圆初始化替代零初始化 | 降低初始 S95，加速收敛 |
| P0 | GPU S95 精度修复 | 增加直方图 bin 数 (256→2048) 或改用自适应范围，消除 CPU readFlux |
| P1 | 多 sun 批量并行 | 36 sun 打包单次 dispatch，预期 2–3× 加速 |
| P1 | 螺栓驱动 NLGEOM 修正 | 消除线性代理模型剩余 ~1.3mm 面型误差 |
| P2 | 四面镜 (E/S/W) 优化 | 验证多位置泛化能力 |
| P2 | C++ shader 直接 TPS | 替代 .bin 预计算，支持任意分辨率 |

---

## 引用

核心方法论见 [CLAUDE.md](CLAUDE.md)，包含完整的数据流推导、NLGEOM 分析和物理模型细节。性能优化方案与 Phase 3 GPU S95 回归分析见 [optimization_plan.md](optimization_plan.md)。
