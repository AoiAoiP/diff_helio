# CLAUDE.md — Bezier 定日镜面型优化器

## 编译与运行

### 本机编译

```powershell
$env:VULKAN_SDK = "C:\VulkanSDK\1.4.341.1"
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

强制重编译 shader：`rm build/shaders/*.spv && cmake --build build --config Release`

依赖项 (fmt, glm, Slang) 通过 CMake `FetchContent` 自动下载。

### 数据准备（一键生成）

```bash
# TPS 影响函数 + 20-bin 重力（从已有 ANSYS CSV 生成）
python scripts/generate_proxy_model.py all

# 仅 TPS 影响函数
python scripts/generate_proxy_model.py tps

# 通过 ANSYS MAPDL 批量生成 20-bin 重力 + TPS（需 ANSYS 许可证）
python scripts/generate_proxy_model.py all-ansys

# 自定义螺栓布局
python scripts/generate_proxy_model.py all --bolt-layout configs/bolt_layouts/6x6.json
```

> **已废弃**：`scripts/prepare_data.py`、`scripts/generate_tps_influence.py` 已被 `generate_proxy_model.py` 替代，保留为薄封装层。

输出至 `data_proxy/`（默认）：`influence_phi.bin`、`influence_phi_u/v.bin`、`gravity_{angle}deg.bin`（20 个角度）、`gravity_angles.json`、`gravity_y.bin`。

### 运行优化

```bash
# North 300m 单镜（200 iter, lr=4e-4 constant, ~7 min）
./build/src/Release/bezier_opt.exe configs/bolt_optimize_north_200iter.json

# 四面镜优化（200 iter, lr=4e-4 constant, ~20 min）
./build/src/Release/bezier_opt.exe configs/bolt_optimize_4mirror_200iter.json

# North 300m（300 iter, lr=2e-4→1e-7 衰减）
./build/src/Release/bezier_opt.exe configs/bolt_optimize_north_300iter.json
```

### 其他运行模式

```bash
# 光斑输出（完整 C++ Vulkan 光追，3 个太阳方向）
./build/src/Release/bezier_opt.exe --dump-flux --surface-file <path> <config>

# 梯度检验（螺栓模式）
./build/src/Release/bezier_opt.exe --check-grad <config>

# 面型验证（ANSYS FEA 点云 vs TPS proxy，倾角形变 + 光斑）
python scripts/run_fea_validation.py --result-dir results_north_300iter --angles 0 29.5 58.5
```

Shader 由 Slang 编译，入口点映射见 `CMakeLists.txt:68-87`。每个 entry point 生成独立 `.spv` 文件。运行时 SPIR-V 文件需在 `./shaders/` 下（cmake 自动复制到 exe 同级目录）。

---

## 架构

### 核心管线（`src/pipeline.cpp` `BezierPipeline::optimize`）

- **Bolt 模式**（当前默认）：35 螺栓调节量 → TPS 影响函数叠加 → 表面位移 → Vulkan 光追 → S95 光斑损失 → Slang bwd_diff 反传梯度 → Adam 更新
- **Bezier 模式**（已废弃）：16 个 Bézier 控制点参数化表面

### 数据流（每太阳方向 × 每迭代）

```
boltForwardSurface (力学正向) → forwardRender (光追) → S95 loss (CPU 二分搜索)
→ boltBackwardPass (光学反传 + 力学投影) → boltAdamStep (参数更新)
```

### GPU Dispatch 总览（每太阳方向 × 每迭代）

| Dispatch | Shader | Grid | 说明 |
|----------|--------|------|------|
| `(1,1,1)` | `computeBoltSurface` | 1024 threads | 力学正向 |
| `(1,1,1)` | `clearFlux` | 7850 threads | 清零能流 |
| `(ceil(7850/256),1,1)` | `renderForward` | ~31 groups | 光追正向 |
| `(1,1,1)` | `finalizeFlux` | 7850 threads | 归一化 |
| `(1,1,1)` | `computeS95Loss` | 7850 threads | 损失梯度 |
| `(7850, kTileCount, 1)` | `renderBackwardBolt` | ~31400 groups | 光追反向 |
| `(1,1,1)` | `reduceSurfaceGradients` | 1 group | 跨 group 归约 |
| `(1,1,1)` | `projectBoltGradients` | 35 threads | 投影到螺栓梯度 |
| `(1,1,1)` | `boltAdamStep` | 35 threads | Adam 更新 |

### 关键源文件

| 文件 | 功能 |
|------|------|
| `src/pipeline.cpp` | 优化循环、Vulkan dispatch、S95、梯度反传、Adam |
| `shaders/bolt_forward.slang` | 力学正向：影响函数 + 重力叠加 → yGrid/nGrid |
| `shaders/bolt_backward.slang` | 三阶段反向：bwd_diff → reduceSurfaceGradients → projectBoltGradients |
| `shaders/bolt_common.slang` | 影响函数求值、20-bin 重力插值 `sampleGravityUY` |
| `shaders/forward.slang` | 光线追踪、双折射玻璃、Buie 太阳模型 |
| `shaders/loss.slang` | S95 sigmoid 损失、GPU 直方图 |
| `shaders/bolt_optimizer.slang` | Adam 参数更新 |
| `shaders/common.slang` | UBO、坐标变换、Wang hash |
| `src/vulkan_app.h/cpp` | Vulkan 封装：buffer/texture/cmd/pipeline |

---

## 方法论：TPS 代理模型与可微优化管线

### 1. 核心公式与坐标系约定

定日镜面板在局部坐标系下的法向位移场由两项叠加：

$$w(\mathbf{r}) = UY_{\text{grav}}^{\text{FEA}}(\theta) + \sum_{b=1}^{N_b} h_b \cdot \phi_b^{\text{TPS}}(\mathbf{r})$$

- **第一项** $UY_{\text{grav}}^{\text{FEA}}(\theta)$：零螺栓纯重力 FEA 解（NLGEOM-ON）在倾角 $\theta$ 下的局部坐标系 UY 位移场，通过 20 个稠密角度 bins 的双线性插值获得。
- **第二项**：35 个螺栓单位位移影响函数的线性叠加，$h_b$ 为螺栓调节量，$\phi_b$ 为 TPS 影响函数。

模型位于**板局部坐标系**（板法向为 y），无需 $\cos\theta$ 因子——$\phi_b$ 描述的是单位螺栓位移在局部坐标下的响应，$dy/dh_b = \phi_b$。计算出 $w(\mathbf{r})$ 后经 local→world 变换得到世界坐标点云，再进入光线追踪（`forwardRender`）。

### 2. TPS 影响函数

#### 2.1 生成方法

对每个螺栓 $b$，设 $h_b=1$（其余为零），求解薄板样条系统：

$$A \cdot [c; d] = [\mathbf{e}_b; \mathbf{0}_3], \quad A = \begin{bmatrix} K & P \\ P^T & 0 \end{bmatrix}$$

其中 $K_{ij} = r_{ij}^2 \log(r_{ij}^2)$ 为 TPS 核函数，$P = [\mathbf{1}, \mathbf{BX}, \mathbf{BZ}]$ 为多项式项，对角加 Tikhonov 正则 $K_{ii} = \phi(0) + \lambda$（$\lambda=10^{-6}$）。

全板面响应 $\phi_b(x,z) = \sum_j c_j \cdot r_j^2\log(r_j^2) + d_0 + d_1 x + d_2 z$ 即为螺栓 $b$ 的影响函数。一阶导数按归一化坐标解析给出（供 shader 求法向）：

$$\frac{\partial \phi_b}{\partial u} = \frac{\partial \phi_b}{\partial x} \cdot W, \quad \frac{\partial \phi_b}{\partial v} = \frac{\partial \phi_b}{\partial z} \cdot L$$

与 `bolt_common.slang` 切向量约定 `tu=(W, yu, 0)`、`tv=(0, yv, L)` 一致。

#### 2.2 自影响修正与网格约定

TPS 系统矩阵对角为 $K_{ii} = \phi(0) + \lambda$，但逐点评估核函数 $\phi(0) = r^2\log(r^2)|_{r\to 0} \approx 0$，丢失了 $\lambda$ 项，导致螺栓自位置影响被系统性压低至 ~0.53。修复方式：在每个螺栓最近网格点补回 `phi_kernel[j, self] += λ`，并统一核函数为 $r^2\log(r^2)$（此前误用 $r^2\log(r)$，因子差 2）。

**网格约定**（2026-07-17 修正）：influence 和 gravity 数据现在使用 **pixel-centered** 网格，与 shader 的 `gridToPlate()` 一致：
```python
u = (np.arange(GS) + 0.5) / GS        # pixel center
x = (u - 0.5) * W                      # 匹配 shader: gridToPlate(gridU, gridV)
```
此前使用 `linspace(-W/2, W/2, GS)`（cell-edged），与 shader 偏移 ~200mm。修正后自影响从 [0.93, 1.12] 改善到 **[0.94, 1.02]**（均值 0.98）。

#### 2.3 关键性质（32×32 实测）

- **单位分解**：$\sum_b \phi_b(x,z) \equiv 1$，PV $\approx 1.3\times 10^{-6}$ — 保证物理正确的线性叠加
- **线性性**：$\phi_b = \partial w/\partial h_b$ 定义良好
- **系统**：38×38（35 螺栓 + 3 多项式项），条件数 $\sim 4.2 \times 10^6$
- **生成**：`scripts/generate_proxy_model.py tps` <1s，输出 6 个 `.bin` 文件

> **已废弃 — MFS-Tikhonov (VSM)**：虚拟源点 + 边界配置，系统极度欠定（358 未知 / 198 方程），单位分解 PV≈14、自影响仅 0.13，不再使用。

### 3. 重力模型：FEA-Direct + 稠密角度插值

#### 3.1 问题：稀疏 bin 的插值误差

重力沉降随倾角呈非线性变化（低角度膜刚化效应强）。初始方案仅用 5 个角度 bin（0°/30°/45°/60°/75°）做线性插值，在非 bin 角度产生系统性幅度低估。例如 ellipse 12°/35°/52° 工况 R² 仅 ~0.90，slopeRatio ≈ 0.77–0.82（法向幅度偏小 ~20%），导致光斑 S95 系统性偏小——这是"小光斑假象"的根因。

#### 3.2 稠密 bin 方案

将重力 bin 从 5 个加密到 **20 个**（10°/14°/18°/22°/26°/30°/34°/38°/42°/46°/50°/54°/58°/62°/66°/70°/73°/76°/78°/80°），间距 ≤4° 使得线性插值残余可忽略。

生成方式：
- **从 ANSYS MAPDL 批量仿真**：`python scripts/ansys_gravity.py` 自动对每个角度运行 NLGEOM-ON 静力学仿真，输出 7 列 CSV
- **CSV → .bin 转换**：`python scripts/generate_proxy_model.py gravity` 从 CSV 中提取 plate-normal 位移 `w = uy·cosθ + uz·sinθ`（匹配 GUI 约定：板法向 = (0, cosθ, +sinθ)），插值到 pixel-centered 32×32 网格

**坐标系约定**（2026-07-17 修正）：所有 APDL 脚本统一使用 GUI 约定：
- 板角点：`y = −z_local·sinθ`（顶部边缘在原点下方）
- 板法向：`(0, cosθ, +sinθ)`（全局坐标）
- 螺栓位移：`(UX=0, UY=stroke·cosθ, UZ=stroke·+sinθ)`
- 重力提取：`w = uy·cosθ + uz·sinθ`（板法向分量，非 raw global UY）

管线集成：shader 侧 `kGravityAngles[20]` + 合并单 buffer 直接索引，C++ 侧 `m_gravityBinsMerged`。

#### 3.3 效果

| 角度 | R² (5-bin) | R² (20-bin) | slopeCorr (5→20 bin) |
|:---:|:---:|:---:|:---:|
| 12° | 0.905 | **0.985** | 0.957 → **0.994** |
| 35° | 0.907 | **0.998** | 0.959 → **0.9995** |
| 52° | 0.887 | **0.962** | 0.931 → **0.996** |

R² 全面 ≥0.96，slopeCorr ≥0.994。**但优化结果对 bin 密度不敏感**：20-bin 优化（S95=52.32 m²）与 10-bin（52.30 m²）差异极小（螺栓相关 0.999996，RMS 差 0.027mm），10-bin 已充分捕捉重力非线性。

### 4. 可微优化管线

#### 4.1 梯度链

$$\frac{dL}{dh_b} = \sum_{\text{sun}} \sum_{p} \left[ \frac{\partial L}{\partial\text{flux}} \cdot \left( \frac{\partial\text{flux}}{\partial y} \cdot \phi_b + \frac{\partial\text{flux}}{\partial y_u} \cdot \frac{\partial\phi_b}{\partial u} + \frac{\partial\text{flux}}{\partial y_v} \cdot \frac{\partial\phi_b}{\partial v} \right) \right]$$

#### 4.2 螺栓后处理

```
h_pipe_final = h_opt − max(h_opt) − 0.5mm    (管线约定, 全部 ≤ −0.5mm)
h_phys       = −h_pipe_final                   (物理约定, 全部 ≥ +0.5mm)
h_stroke     = h_phys − min(h_phys)            (实际螺栓伸出量)
```

S95 不变。物理上等效于安装基座沿负法向统一后移。

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
| Adam β₁, β₂ | 0.9, 0.999 |

---

## 实验日志

| 文件 | 内容 |
|------|------|
| `results_4mirror_200iter/EXPERIMENT_REPORT.md` | 四面镜 200-iter 优化实验报告（2026-07-16） |
| `validation/fea_comparison/FEA_VALIDATION_REPORT.md` | TPS Proxy vs FEA 验证报告（2026-07-17） |
| `validation/fea_comparison/62deg_comparison.png` | 62° GUI vs Python 重力对比图 |
| `docs/tvcg_submission_gap_analysis.md` | TVCG 投稿差距分析与补充实验规划 |
| `analysis/` | 历史分析文档 |

### 最新四面镜结果（2026-07-17, data_proxy 修正后）

| 镜面 | 初始 S95 | 最优 S95 | 改善 | Max Stroke |
|:---:|:---:|:---:|:---:|:---:|
| North | 227.3 | **50.05** | 78.0% | 36.0 mm |
| East | 214.4 | **65.11** | 69.6% | 35.9 mm |
| South | 198.3 | **73.13** | 63.1% | 34.6 mm |
| West | 215.0 | **64.67** | 69.9% | 36.7 mm |
| **合计** | | **253.0** | | |

> 配置：200 iter, lr=4e-4 constant, Adam β=(0.9,0.999), pixel-centered 32×32 网格, 20-bin plate-normal 重力, GUI-apdl 约定。

### TPS Proxy vs FEA 验证（2026-07-17）

| 角度 | NLGEOM | RMS | R2 | shape_corr |
|:---:|:---:|:---:|:---:|:---:|
| 29.5° | ON | 1.94 mm | 0.955 | 0.980 |
| 29.5° | OFF | 2.45 mm | 0.929 | 0.968 |
| 58.5° | ON | 2.04 mm | 0.952 | 0.980 |
| 58.5° | OFF | 2.22 mm | 0.942 | 0.976 |

> NLGEOM-ON 在所有指标上优于 OFF——proxy 使用 NLGEOM-ON 重力 bins，天然匹配 FEA-ON 解。
