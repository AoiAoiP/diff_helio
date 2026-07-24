# CLAUDE.md — Bezier 定日镜面型优化器

## 编译与运行

### 本机编译

```powershell
$env:VULKAN_SDK = "C:\VulkanSDK\1.4.350.0"
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

### 太阳方向采样（全年 sundir 生成）

```bash
# 推荐：balanced 模式（12 月 × 3 天 × 13 时点, ~334 方向, 日常优化用）
python scripts/generate_sundir_year.py

# 论文级最小集（12 月 × 1 天 × 13 时点, ~110 方向, 快速迭代）
python scripts/generate_sundir_year.py --mode paper

# 稠密集（12 月 × 14 天 × 13 时点, ~1556 方向, 验证/最终生产）
python scripts/generate_sundir_year.py --mode dense

# 自定义位置与时区
python scripts/generate_sundir_year.py --lat 37.36 --lon 97.29 --tz Asia/Shanghai
```

**设计原则**（详见 `sundir_sample/analysis_and_recommendations.md`）：
- 以**真太阳正午**（azimuth=180°）为基准对称采样——消除均时差（EoT）导致的上午/下午不对称
- 12 个月月度覆盖——日期维度已饱和（论文结论）
- 日内 1h 间隔（13 时点）——比旧脚本 2h 间隔加密一倍

**推荐训练集**（基于 2026-07-22 对比实验）：

| 场景 | 训练集 | 方向数 | 耗时（200 iter） |
|------|--------|--------|-----------------|
| 快速迭代（仅北/南侧） | `data/36_sundir_fast.txt` | 36 | ~5 min |
| **日常优化（全方向）** | `data/334_sundir_balanced.txt` | 334 | ~50 min |
| 最终生产运行 | 同上 balanced 模式 | 334 | ~50 min |

> 东西侧镜面对训练集大小更敏感：36dir 过拟合达 +1.7 m²，110dir 降至 +0.4 m²，334dir 基本消除。详见 `sundir_sample/EXPERIMENT_REPORT_EAST_WEST.md`。

> **已废弃**：`sundir_sample/DE_sundir_year.py`（平太阳时 + 2h 间隔）和 `data/738_sundir_year.txt` 已被新脚本替代，保留仅用于历史参考。旧脚本使用平太阳时（仅经度修正）而非真太阳时，存在 ±15 min 的不对称偏差。

### 运行优化

```bash
# North 300m 单镜（200 iter, lr=4e-4 constant, ~7 min）
./build/src/Release/bezier_opt.exe configs/bolt_optimize_north_200iter.json

# 四面镜优化（200 iter, lr=4e-4 constant, ~20 min）
./build/src/Release/bezier_opt.exe configs/bolt_optimize_4mirror_200iter.json

# North 300m（300 iter, lr=2e-4→1e-7 衰减）
./build/src/Release/bezier_opt.exe configs/bolt_optimize_north_300iter.json
```

### Ellipse → LS-Fit → S95 验证管线

对比理想椭圆曲面最小二乘 TPS 拟合 vs 端到端 S95 优化的光斑质量差异。

```bash
# 1. LS 拟合：对 ellipse.txt 中全部 20 面镜子做 TPS LS 拟合
python scripts/lsq_fit_elliptic.py
# 输出: data/init/{NEWS}_{distance}m_lsq_bolt_init.txt + data/init/lsq_fit_summary.csv

# 2. 准备 bolt init 目录（匹配 C++ "auto" 命名约定）
mkdir -p data/init_lsq data/init_opt
for f in data/init/*_lsq_bolt_init.txt; do
    name=$(basename "$f" _lsq_bolt_init.txt)
    cp "$f" "data/init_lsq/${name}_bolt_init.txt"
done
# 同理复制优化后的 BEST_bolts.txt 到 data/init_opt/

# 3. 编译（确保 main.cpp 无距离过滤，bolt_init_dir 可配置）
cmake --build build --config Release

# 4. 评估 LS 和 Opt 螺栓的年均 S95（334 方向）
./build/src/Release/bezier_opt.exe configs/_eval_lsq.json   # → results_lsq_eval/
./build/src/Release/bezier_opt.exe configs/_eval_opt.json   # → results_opt_eval/

# 5. 对比汇总
python scripts/compare_lsq_vs_opt.py \
    --lsq-s95 "North_300m=51.61" ... \
    --opt-s95 "North_300m=50.40" ... \
    --opt-summary-dir results_Field
```

**配置文件**：`_eval_lsq.json` 设置 `bolt_init_file: "auto"` + `bolt_init_dir: "data/init_lsq/"` + `iterations: 1` + `learning_rate: 0.0`（纯评估，不优化）。

**已有脚本**（仅 300m NEWS，3 太阳方向 `--dump-flux` 模式）：
- `scripts/validate_ellipse_tps_news.py` — 椭圆 → TPS LS 拟合 + 形变指标对比图
- `scripts/compute_s95_from_flux.py` — 从 `--dump-flux` NPY 计算 S95（纯 Python）

**2026-07-22 全镜场对比结论**（150m-1200m NEWS，334 方向年均 S95）：

| 距离 | LS/Opt 比值 | 结论 |
|------|------------|------|
| 150m | 1.01–1.05x | LS 拟合几乎等同优化 |
| 300m | 1.004–1.02x | LS 拟合极接近优化 |
| 600m | 1.004–1.01x | LS 拟合略逊于优化 |
| 900m | **1.95–2.93x** | LS 严重不足，优化器找到非椭圆面型 |
| 1200m | **2.07–3.70x** | LS 完全失败，需端到端优化 |

**关键发现**：近距离（≤600m）理想椭圆面可通过 LS 拟合良好近似；远距离（≥900m）优化器主动偏离椭圆面型（螺栓行程 70-76mm vs LS 的 10-13mm），通过非椭圆面型补偿重力 + 接收器几何 + 太阳形状的耦合效应。

**⚠️ 2026-07-23 Bug 发现与修复 — 远距离能量溢出**：上述 900m/1200m 的初始优化结果存在严重缺陷。优化器在 λ_energy=0 时将大部分光线溢出接收器（能量保持率仅 1-50%），从而"作弊式"获得虚假的小 S95。根因为损失函数缺少能量保持约束 + TPS 线性代理在 70mm+ 行程下失准。

**修复方案**（已实现为配置参数，无需代码改动）：
```json
"lambda_energy": 0.5,            // 能量效率正则化（保持 >95% 能量）
"stroke_regularization": 0.001   // 螺栓行程正则化（限制在已验证范围）
```

**λ_energy 参数扫描结论（1200m NEWS, 200 iter, 36 dir）**：

| λ_energy | S95 改善 | 螺栓行程 | 能量保持 | 结论 |
|----------|---------|---------|---------|------|
| 0.0 | 60–75% | 70–76mm | 1–50% | 虚假——能量崩溃 |
| 0.1 | 24–35% | 37–44mm | 60–87% | 部分有效，能量损失仍大 |
| 0.3 | 5–15% | 20–23mm | 高 | 保守可用 |
| **0.5** | **0–7%** | 12–23mm | **~100%** | **推荐——能量安全** |

**最终结论**：在塔式 CSP 场景下，能量是首要指标。用能量损失换 S95 缩小是因小失大。λ≥0.5 时远距离端到端优化几乎无收益——理想椭圆面已是能量守恒下的近最优解。

**推荐 λ 值 by 距离**：

| 距离 | λ_energy | 原因 |
|------|----------|------|
| ≤600m | 0 | 接收器张角大，所有光线自然落在接收器上 |
| 900m | 0.1–0.5 | 轻量防护，North 可达 7% 边际改善 |
| 1200m | 0.5 或 LS-fit | 优化几乎无收益，LS 直接可用 |

**纯椭圆面无重力 S95 参考表（334 方向，论文基准值）**：
```
        150m    300m    600m    900m    1200m
North   38.78   51.61  137.79  276.76  377.11
East    49.00   67.17  167.60  295.33  383.96
South   52.06   72.24  188.56  312.81  393.37
West    48.92   67.33  167.41  294.88  383.71
```
生成方式：`disable_gravity: 1` + LS 螺栓 init + 1 iter 334-dir 评估（configs/_eval_ellipse_nograv.json）。注：North_300m=51.61 m²，非参考值 43.6（可能与 sunshape/光学参数差异有关）。

### 其他运行模式

```bash
# 光斑输出（完整 C++ Vulkan 光追，3 个太阳方向）
./build/src/Release/bezier_opt.exe --dump-flux --surface-file <path> <config>

# 梯度检验（螺栓模式）
./build/src/Release/bezier_opt.exe --check-grad <config>

# 面型验证（ANSYS FEA 点云 vs TPS proxy，倾角形变 + 光斑）
python scripts/run_fea_validation.py --result-dir results_north_300iter --angles 0 29.5 58.5

# 三路形变验证（APDL vs GUI vs Proxy）
python scripts/post_fea_validation.py --stroke-file <path> --angles 29.5 58.5
```

Shader 由 Slang 编译，入口点映射见 `CMakeLists.txt:69-97`。每个 entry point 生成独立 `.spv` 文件。运行时 SPIR-V 文件需在 `./shaders/` 下（cmake 自动复制到 exe 同级目录）。

---

## 架构

### 核心管线（`src/pipeline.cpp` `BezierPipeline::optimize`）

- **Bolt 模式**（当前默认）：35 螺栓调节量 → TPS 影响函数叠加 → 表面位移 → Vulkan 光追 → S95 光斑损失 → Slang bwd_diff 反传梯度 → Adam 更新
- **Bezier 模式**（已废弃）：16 个 Bézier 控制点参数化表面

### 数据流（每太阳方向 × 每迭代，单次 submit）

```
boltForwardSurface (力学正向) → forwardRender (光追) → computeS95FindLevel (GPU 协作二分查找)
→ computeS95LossBUF (从 GPU buffer 读阈值) → boltBackwardPass (光学反传 + 力学投影)
→ boltAdamStep (参数更新，每迭代一次)
```

> S95 阈值不再回读 CPU：单 workgroup 在 GPU 上做与 CPU 版语义一致的二分查找（20 轮、严格 `f>mid` 能量和、>0.95 判定），精度仅受浮点归约顺序影响（~1e-6 相对误差）。标量 loss 以定点数 ×1e3 在 GPU 累加，每迭代回读 4 字节。环境变量 `BEZIER_S95_GPU=0` 可回退到旧 CPU 路径（A/B 对比用）。历史教训：Phase 3 的固定范围 256-bin 直方图有 ~1.5 W/m² 系统偏差，导致 sigmoid 饱和 —— 见 `optimization_plan.md`。

### GPU Dispatch 总览（每太阳方向 × 每迭代，单次 submit）

| Dispatch | Shader | Grid | 说明 |
|----------|--------|------|------|
| `(1,1,1)` | `computeBoltSurface` | 1024 threads | 力学正向 |
| `(1,1,1)` | `clearFlux` | 7850 threads | 清零能流 |
| `(kTileCount, ~3950, 1)` | `renderForward{Buie,Pillbox,Gaussian}` | 稀疏像素 | 光追正向（A2 特化，按 sun_type 选管线；内含 A1 逐光线预裁剪） |
| `(1,1,1)` | `finalizeFlux` | 7850 threads | 归一化 |
| `(1,1,1)` | `computeS95FindLevel` | 256 threads × 1 group | GPU 协作二分查找 S95 阈值 |
| `(10,4,1)` | `computeS95LossBUF` | 7850 threads | 损失梯度 + 标量 loss 累加（L1 效率项经 16B push constants） |
| `(~3950, kTileCount, 1)` | `renderBackwardBolt{Buie,Pillbox,Gaussian}` | ~15800 groups | 光追反向（A2 特化） |
| `(1,1,1)` | `reduceSurfaceGradients` | 1 group | 跨 group 归约 |
| `(1,1,1)` | `projectBoltGradients` | 35 threads | 投影到螺栓梯度 |
| `(1,1,1)` | `boltAdamStep` | 35 threads | Adam 更新（每迭代一次，L4 tanh 参数化） |

### 关键源文件

| 文件 | 功能 |
|------|------|
| `src/pipeline.cpp` | 优化循环、Vulkan dispatch、S95、梯度反传、Adam |
| `shaders/bolt_forward.slang` | 力学正向：影响函数 + 重力叠加 → yGrid/nGrid |
| `shaders/bolt_backward.slang` | 三阶段反向：bwd_diff → reduceSurfaceGradients → projectBoltGradients（含 A2 特化入口） |
| `shaders/bolt_common.slang` | 影响函数求值、20-bin 重力插值 `sampleGravityUY` |
| `shaders/s95_gpu.slang` | GPU 端 S95：协作二分查找阈值 + buffer 版 sigmoid 损失（含 L1 效率项） |
| `shaders/forward.slang` | 光线追踪、双折射玻璃、Buie 太阳模型（A1 逐光线预裁剪 + A2 特化入口） |
| `shaders/loss.slang` | S95 sigmoid 损失（push-constant 版，Bezier/MSE 路径用）、GPU 直方图 |
| `shaders/bolt_optimizer.slang` | Adam 参数更新（L4：无界 ε 空间更新，h = h_max·tanh(ε)） |
| `shaders/common.slang` | UBO、坐标变换、Wang hash |
| `src/vulkan_app.h/cpp` | Vulkan 封装：buffer/texture/cmd/pipeline |

### P0/P1 优化实现要点（2026-07-20）

对照 `analysis/arcaim_comparison.md` 的优先级清单实施。设计/验证细节见 `analysis/p0_validation_report.md`（P0）与 README「P0/P1 优化」节（总览）。

**UBO 槽位约定（SunParams，勿动顺序）**：`sunp[9]=type`，`sunp[10]=iterationSeed`（L3），`sunp[11]=cullCosCutoff`（A1），`sunp[12]` 保留。

- **A1 逐光线预裁剪**（`ray_cull`，默认 ON）：`forward.slang` 在 Box-Muller 前做宏观法向反射余弦测试 `dot(reflect(dir, surfNrm), sunDir) >= cullCos`；cutoff = cos(日轮支持域 + `ray_cull_margin_mrad`)，支持域 Buie=0.0436 rad / pillbox=θ_max / Gaussian=5σ。`ray_cull=0` → cullCos=−2 完全旁路（位精确回退）。North300m 200-iter 与基线位精确一致，总时间 −4.8%。
- **L1 效率项**（`lambda_energy`，默认 0）：`s95_gpu.slang` 的 `S95LossPC{eRef, lambdaEff}` 16B push constants；E=`s95State[2]`（level find 已算），E_ref 在 iter 0 逐太阳方向捕获（每方向一次 16B 回读）。λ=0 逐位退化为纯 S95；λ=0.1 实测 loss 偏移 +28,342 ≈ 理论 +28,260。仅 GPU-S95 非 MSE 路径生效（否则打印 WARNING 并忽略）。
- **A2 编译期特化**：`renderForwardTyped<let SUNSHAPE_TYPE>` / `renderBackwardBoltTyped` 由 Slang 常量折叠；C++ 建 3 条管线按 `m_cfg.sunType` 分派（`m_pipeForwardTyped[3]` / `m_pipeBoltBackwardTyped[3]`）。通用入口 `renderForward` / `renderBackwardBolt` 保留编译但运行时不使用。
- **L3 逐迭代种子**（`randomize_seed`，默认 OFF）：ON 时 `sunp[10] = m_currentIteration + 1`，`generateGaussianSamples` 混入逐迭代种子；OFF（=0.0）回退 `kSamplingSeed` 固定流（位精确旧行为）。
- **L4 tanh 有界参数化**（始终启用）：Adam 在 ε 空间更新，`h = h_max·tanh(ε)`（`max_bolt_stroke` 默认 0.040 m）。每迭代从物理 h 经 `atanh(clamp(h/h_max, ±0.999))` 恢复 ε，链式因子 `dh/dε = h_max(1−tanh²ε)`，lr 补偿 `lr_ε = lr/h_max`（零点附近与旧直接参数化步长一致）。`stroke_regularization` > 0 时加 2λ·h·dh/dε 梯度。**行为变化**：iter 0 与旧代码位精确一致，iter ≥1 轨迹按设计偏离；逐位复现历史结果需回退 `26f1d2e`。
- **A3 reflection-only**：已停用。配置项仍解析（`reflection_only_optimization`）但光路固定全折射（`pipeline.cpp` `helio[7]=0.0f // always refraction`）。

新增/变更配置键：`ray_cull`(1)、`ray_cull_margin_mrad`(8.0)、`lambda_energy`(0.0)、`max_bolt_stroke`(0.040)、`stroke_regularization`(0.0)、`randomize_seed`(0)、`reflection_only_optimization`(0，停用)。

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
| 玻璃折射率 | 1.523, 厚 4mm |
| 太阳模型 | Buie CSR=0.01, DNI=1000 W/m² |
| 斜率误差 | 1 mrad |
| 学习率（推荐） | 4×10⁻⁴ constant |
| Adam β₁, β₂ | 0.9, 0.999 |

---

## 实验日志

| 文件 | 内容 |
|------|------|
| `results_4mirror_200iter/EXPERIMENT_REPORT.md` | 四面镜 200-iter 优化实验报告（2026-07-16） |
| `train_data/zero_heights_ON/VALIDATION_TABLE.md` | APDL vs GUI 零螺栓重力 22 角度验证表（2026-07-20） |
| `results_4mirror_200iter/fea_validation/FEA_VALIDATION_REPORT.md` | TPS Proxy vs FEA 验证报告（优化螺栓，2026-07-20） |
| `docs/tvcg_submission_gap_analysis.md` | TVCG 投稿差距分析与补充实验规划 |
| `analysis/arcaim_comparison.md` | ARCAim (diffspt) 第三章方法论 ↔ 代码映射 + 本项目优化空间（2026-07-20） |
| `analysis/p0_validation_report.md` | P0 位精确一致性与时空开销验证（2026-07-20） |
| `analysis/p0p1_merge_validation.md` | P0+P1 合并树端到端验证纪要（2026-07-20） |
| `validation/pre_fea_validation/FEA_VALIDATION_REPORT.md` | GUI Workbench FEA 验证报告（2026-07-20） |
| `validation/post_fea_validation/summary_table.md` | APDL vs GUI vs Proxy 三路验证汇总（2026-07-21） |
| `docs/progress_2026-07-21.md` | **POD-Linear 代理模型原型实现与验证**（方案 E），含 100 FEA 快照、K=51 POD 模型、6 次优化 lr 扫描（2026-07-21） |
| `docs/plate_proxy_replacement_research.md` | TPS 代理替代方案调研 + §7 POD-Linear 实验报告（2026-07-21） |
| `sundir_sample/analysis_and_recommendations.md` | **太阳方向采样策略分析** — 论文结论 vs 本项目需求、真太阳时对称采样设计（2026-07-22） |
| `sundir_sample/EXPERIMENT_REPORT.md` | **North 300m sundir 对比实验** — 36/110/334dir 验证 S95 几乎一致（<0.03%），东西侧需更密采样（2026-07-22） |
| `sundir_sample/EXPERIMENT_REPORT_EAST_WEST.md` | **东西侧 sundir 对比实验** — 东西侧过拟合达北侧 4–5 倍，110dir 为最低可行训练集（2026-07-22） |
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

### APDL 批处理 vs GUI Workbench 等价性验证（2026-07-21）

对 North 300m 最优螺栓配置（35.7 mm max）在 29.5° 和 58.5° 下进行三路对比（APDL / GUI / TPS Proxy）。详见 `scripts/post_fea_validation.py`。

**APDL vs GUI FEA 形变对比**：

| 角度 | RMS | R² | shape_corr | PV ratio |
|:---:|:---:|:---:|:---:|:---:|
| 29.5° | **0.050 mm** | **1.0000** | **1.0000** | **1.0000** |
| 58.5° | **0.051 mm** | **1.0000** | **1.0000** | **1.0006** |

> **结论**：APDL 批处理管线与 Workbench GUI 在有螺栓位移场景下**位精确一致**（RMS < 0.05 mm ≈ 节点输出精度量级）。自动化 APDL 管线可完全替代手工 GUI 导出 FEA 点云。

**Proxy vs FEA**：RMS ~2.8–3.3 mm, shape_corr 0.95–0.96（与方向 6 结论一致，当前 data_proxy 版本）。

### 全镜场 LS-Fit vs 优化 + λ 参数扫描（2026-07-23）

**实验设置**：对 150m/300m/600m/900m/1200m 五距离 × NEWS 四方向共 20 面镜子，进行 LS 拟合 vs 端到端优化对比，发现远距离能量溢出 bug 并完成 λ_energy 参数扫描修复。

**数据文件**：
- `scripts/lsq_fit_elliptic.py` — TPS LS 拟合脚本（R²>0.99799）
- `scripts/compare_lsq_vs_opt.py` — S95 对比脚本
- `data/lsq_vs_opt_334d.csv` — 完整对比表
- `data/init/lsq_fit_summary.csv` — LS 拟合质量汇总
- `configs/bolt_optimize_{900m,1200m}_lam*.json` — λ 扫描配置
- `configs/_eval_ellipse_nograv.json` — 纯椭圆面无重力评估

**全 20 面镜子三路 S95 对比（334 方向年均，单位 m²）**：

```
                 Pure Ellipse (no grav)      LS-Fit (with grav)       Optimized (λ=0)
              150m  300m  600m  900m 1200m  150m  300m  600m  900m 1200m  150m  300m  600m  900m 1200m
North         38.78 51.61 137.79 276.76 377.11  38.79 51.61 137.79 276.76 377.10  37.46 50.40 137.13  94.62* 101.83*
East          49.00 67.17 167.60 295.33 383.96  49.00 67.17 167.60 295.33 383.96  46.45 66.89 165.77 138.21* 158.11*
South         52.06 72.24 188.56 312.81 393.37  52.06 72.24 188.56 312.81 393.36  51.65 71.80 187.88 160.83* 190.50*
West          48.92 67.33 167.41 294.88 383.71  48.92 67.33 167.41 294.88 383.71  46.55 66.58 166.02 138.79* 156.98*
```

> **注意**：
> - Pure Ellipse：`disable_gravity: 1` + LS 螺栓 init + 1 iter 334-dir 评估
> - LS-Fit：重力开启 + LS 螺栓 init + 1 iter 334-dir 评估（与 Pure Ellipse 几乎一致）
> - Optimized：`results_Field/` BEST_bolts.txt 在 334-dir 下评估（λ_energy=0, 200 iter）
> - **\*标记者能量溢出**：900m/1200m 优化 S95 在 λ_energy=0 下取得，能量保留率仅 1–50%（虚假改善）。λ≥0.5 下几乎无改善。
> - Optimized 螺栓行程：150m≈52mm, 300m≈36mm, 600m≈21mm, 900m≈70mm*, 1200m≈74mm*
> - North_300m 纯椭圆 = 51.61 m²（非参考值 43.6，可能因 sunshape/光学参数差异）

**λ_energy 参数扫描（1200m NEWS, 200 iter, 36 dir）**：
| λ | S95 改善 | 行程 | 能量保持 |
|----|---------|------|---------|
| 0.0 | 60-75% | 74-76mm | 1-50% |
| 0.1 | 24-35% | 37-44mm | 60-87% |
| 0.3 | 5-15% | 20-23mm | 高 |
| 0.5 | 0-7% | 12-23mm | ~100% |

**最终结论**：λ≥0.5 约束下远距离优化几乎无收益，理想椭圆面即是能量守恒最优解。≤600m 天然安全（不需正则化）。

Usage:
```bash
# 三路对比（需 ANSYS 许可证）
python scripts/post_fea_validation.py \
    --stroke-file results_4mirror_200iter/North_300m_STROKE_bolts.txt \
    --angles 29.5 58.5 \
    --gui-csv validation/pre_fea_validation/node_dump_295deg.csv ...

# 仅比较（跳过 ANSYS，使用已有 APDL CSV）
python scripts/post_fea_validation.py \
    --stroke-file ... --angles 29.5 58.5 \
    --apdl-csv <existing_apdl>.csv --gui-csv <gui_ref>.csv

# Dry-run：只生成 APDL 输入文件
python scripts/post_fea_validation.py --stroke-file ... --dry-run
```

---

## 开放问题

### 🔴 TPS 代理模型精度不足（待解决，2026-07-21 识别）

APDL=GUI 位精确一致性已确认，但 **Proxy vs FEA 仍存在系统性偏差**（RMS ~2.0–3.3 mm, shape_corr 0.95–0.96）。根因：TPS 是纯几何 RBF 插值（核函数 r²log(r²)），不含板弯曲刚度 D、材料属性（E, ν）、自由边界条件、NLGEOM 非线性。

详见 `docs/plate_proxy_replacement_research.md` — 调研了 5 类替代方案：POD-ROM、Kirchhoff Green 函数、模态展开、PINN/算子学习、POD+MLP 混合。

**推荐路线**：POD+MLP 降阶模型（复用现有 APDL 管线采集 FEA 快照 → SVD → 轻量 MLP），精度预期 <2%。
