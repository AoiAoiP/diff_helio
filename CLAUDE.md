# CLAUDE.md

## 编译与运行

### 本机编译

```powershell
$env:VULKAN_SDK = "C:\VulkanSDK\1.4.341.1"
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

强制重编译 shader：`rm build/shaders/*.spv && cmake --build build --config Release`

### 生成 TPS 影响函数

```bash
python scripts/generate_tps_influence.py --output data_vsm_mnvn_tik32   # ~1s
```

输出 6 个 `.bin` 文件到 `data_vsm_mnvn_tik32/`：
- `influence_phi.bin` — 位移影响函数 φ_b [35×32×32]
- `influence_phi_u.bin` — ∂φ/∂u（x 斜率）
- `influence_phi_v.bin` — ∂φ/∂v（z 斜率）
- `influence_kxx/kzz/kxz.bin` — 二阶导数（曲率正则化用，C++ 管线不再加载）

> 重力 bins 由 `scripts/train_residual/precompute_gravity_bins.py`（默认 32×32 / `zero_heights_ON` / `data_vsm_mnvn_tik32`）单独生成。

### 运行优化

```bash
# TPS 影响函数 (当前默认，32×32)
./build/src/Release/bezier_opt.exe configs/bolt_vsm_mnvn_300iter.json    # 300 iter → S95=52.30 m²
```

### 其他运行模式

```bash
# 光斑输出（完整 C++ Vulkan 光追，3 个太阳方向）
./build/src/Release/bezier_opt.exe --dump-flux --surface-file <path> <config>

# 梯度检验（螺栓模式）
./build/src/Release/bezier_opt.exe --check-grad <config>

# 面型验证（Python TPS vs FEA，4 倾角形变 + 光斑）
python scripts/validate_fixed.py
```

---

## TPS 代理模型（当前方案，2026-07-08）

### 核心公式

$$w(\mathbf{r}) = UY_{\text{grav}}^{\text{FEA}}(\theta) + \sum_{b=1}^{N_b} h_b \cdot \phi_b^{\text{TPS}}(\mathbf{r})$$

注：此模型所对应的是板平面的局部坐标系，而非世界坐标系下的板方程。所以，$UY_{\text{grav}}^{\text{FEA}}(\theta)$ 项实际由对应角度的FEA结果根据实际镜面的倾角θ插值而得，且后一项无需乘上$cos(\theta)$。在根据当前的boltHeights[35]计算出局部坐标系下的带重力的板方程$w(\mathbf{r})$后，将$w(\mathbf{r})$进行local2world变换，这样板面点云就转换到世界坐标系了，接着使用该世界坐标系下的点云进行后续的光线追踪（forwardRender）。

### TPS 影响函数

通过 `scripts/generate_tps_influence.py` 生成（<1s），替代已废弃的 MFS-Tikhonov（VSM）方案（极度欠定，见文末一句注）。

**生成方式**：对每个螺栓 b，设 h_b=1（其余为0），求解 TPS 系统：
$$A \cdot [c; d] = [\mathbf{e}_b; \mathbf{0}_3]$$
其中 $A = \begin{bmatrix} K & P \\ P^T & 0 \end{bmatrix}$，$K_{ij} = r_{ij}^2 \log(r_{ij}^2)$，$P = [\mathbf{1}, BX, BZ]$，对角加 Tikhonov 正则 $K_{ii} = \phi(0) + \lambda$（λ=1e-6）。

全板面响应 $φ_b(x,z) = Σ_j c_j·φ(r_j) + d₀ + d₁x + d₂z$ 即为影响函数。一阶导数按**归一化坐标**解析给出（供 shader 求法向）：
$$\partial φ_b/\partial u = \partial φ_b/\partial x \cdot W, \quad \partial φ_b/\partial v = \partial φ_b/\partial z \cdot L$$
与 `bolt_common.slang` 的切向量 `tu=(W, yu, 0)`、`tv=(0, yv, L)` 约定一致，故与网格分辨率无关。二阶导 `kxx/kzz/kxz` 仍生成但 C++ 管线不加载。

**自影响修正（关键 bug，已修复）**：
TPS 系统矩阵对角为 $K_{ii} = \phi(0) + \lambda$，但逐点核 `phi_kernel` 直接求值 $\phi(0)=r^2\log(r^2)|_{r\to0}\approx0$，**丢掉了 λ 项** → 螺栓自身位置得到 $c_i·\phi(0)\approx0$ 而非 $c_i·\lambda$，自影响被系统性压低到 **~0.53**（曾被误判为「25×25 粗网格所限」）。
修复（脚本 `generate_tps_influence.py:95-100`）：在每个螺栓最近网格点补回 `phi_kernel[j, self] += λ`。并统一核函数为 $r^2\log(r^2)$（此前误用 $r^2\log(r)$，与系统矩阵相差因子 2）。

**关键性质（修复后，32×32 实测）**：
- **单位分解**：$Σ_b φ_b(x,z) ≡ 1$，PV ≈ 1.3×10⁻⁶ — 保证物理正确的线性叠加
- **线性性**：TPS 对螺栓高度严格线性，$φ_b = ∂w/∂h_b$ 定义良好
- **自影响**：均值 **1.007**，范围 [0.93, 1.12]，34/35 螺栓 >0.95（修复前 ~0.53）
- **系统**：38×38（35 螺栓 + 3 多项式），条件数 ~4.2×10⁶

> **VSM（MFS-Tikhonov，已废弃）**：虚拟源点 + 边界配置，系统极度欠定（358 未知 / 198 方程），单位分解 PV≈14、自影响仅 0.13、生成需 ~120s SVD。已被 TPS 全面取代，不再展开。

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

### 面型验证结果（核函数修正后，2026-07-08）

| 条件 | RMS | R² | PV_ratio | shape_corr |
|------|:---:|:---:|:---:|:---:|
| 0° 无重力 | **2.45 mm** | **0.938** | 1.20 | 0.981 |
| 0° 重力 | 3.69 mm | 0.844 | 1.01 | 0.929 |
| 29.5° 重力 | 3.77 mm | 0.832 | 1.04 | 0.928 |
| 58.5° 重力 | 3.59 mm | 0.850 | 1.14 | 0.945 |

> **注**：上表为 25×25 网格验证结果。经上文「自影响修正」（自位置补回 λ + 核函数统一为 $r^2\log(r^2)$）后，self-influence 从 ~0.53 提升到 ~1.0，形变 RMS 减半。

### 光斑验证结果（29.5°, 天顶太阳）

| 指标 | TPS Proxy | FEA |
|------|:---:|:---:|
| 峰值能流 | 620 W/m² | 613 W/m² |
| 总能量 | 424,240 | 423,344 |
| S95 像素 | 1,492 px | 1,702 px |

### 废弃方法对比（历史）

| 方法 | RMS (mm) | R² | 形状相关 | 状态 |
|------|:---:|:---:|:---:|:---:|
| **TPS Direct（本项目）** | **2.45** | **0.94** | **0.98** | ✅ |
| TPS Direct (old kernel) | 4.83 | 0.94 | 0.98 | ❌ 已修复 |
| finite_difference | 4.60 | 0.25 | — | ❌ |
| baseline_tps | 7.20 | -0.82 | — | ❌ |
| global_tikhonov | 7.37 | -0.91 | — | ❌ |
| rayleigh_ritz | 173.1 | -1054 | — | ❌ |

### 优化结果 (North 300m)

| 配置 | 分辨率 | 初始 S95 | 最优 S95 | 改善 | 迭代 |
|------|:---:|:---:|:---:|:---:|:---:|
| TPS 零初始化 | 25×25 | ~228 m² | **~53 m²** | ~77% | — |
| TPS 零初始化（fluxPartial bug） | 32×32 | 227.5 m² | 144.8 m²（iter 40 后卡死） | 36% | 100 |
| **TPS 零初始化（修复后）** | **32×32** | 227.4 m² | **52.30 m²** | **77.0%** | 300 |

### 四面镜优化结果 (E/S/W/N 300m, 32×32, 300 轮, 零初始化)

| 镜 | 位置 (x,y,z) | 初始 S95 | 最优 S95 | 改善 | 最大行程 | 结果目录 |
|:---:|---|:---:|:---:|:---:|:---:|---|
| North | (0,0,−300) | 227.4 | **52.30** | 77.0% | 32.87mm | `results_vsm_mnvn_300iter/` |
| East | (300,0,0) | 214.6 | **67.47** | 68.6% | 32.71mm | `results_4mirror_300iter/` |
| South | (0,0,300) | 198.4 | **78.02** | 60.7% | 36.65mm | `results_4mirror_300iter/` |
| West | (−300,0,0) | 214.4 | **87.02** | 59.4% | 38.49mm | `results_4mirror_300iter/` |

- **位置已完整进入光追**：`main.cpp:84` 过滤 290–310m 环；每镜独立 `aimPoint`（由位置算）；宏观法向 = `computeHeliostatNormal(sunDir, heliostatPos, aimPoint)` 随位置变；世界坐标含 `heliostatPosition`；optimize 循环遍历所有过滤后的镜（`main.cpp:301`）。
- **E/W 不对称**（67.5 vs 87.0，初始却几乎相同）：太阳方向集 `data/36_sundir_fast.txt` 东西不对称 + 椭圆目标参数略异（East A=6.71e-4/C=+0.63e-4 vs West A=6.57e-4/C=−0.67e-4）。
- **West 行程最大**（38.5mm ≈ 9.6× 板厚），NLGEOM 效应预期最强。
- 配置：`configs/bolt_4mirror_swe.json` + `data/ellipse_swe_300m.txt`。

> **fluxPartial tile 数 bug（2026-07-09 已修复）**：前向 flux 累加缓冲 `m_fluxPartial`（`pipeline.cpp:319`）与 `shaders/forward.slang`（clearFlux/renderForward/finalizeFlux）硬编码「每像素 3 个 tile」，而 tile 数 = `ceil(gridSize²/256)`：25×25→3（凑巧正确），32×32→4（第 4 tile 越界，丢失镜面 x 方向后 8 列 ≈25% 口径并污染邻像素）。修复：引入编译期 `kTileCount=(totalSpp+255)/256`，缓冲与三处 shader 全部改为按 `kTileCount` 自适应。修复后 32×32 收敛到 52.30 m²，与 25×25 恢复 parity。

> **S95 数值仍偏高（调查中）**：文献表明理想椭圆面型北 300m S95≈43m²，当前零初始化即达 ~228m²。S95 计算涉及：`src/pipeline.cpp:1294`（computeS95Level）、`src/pipeline.cpp:1542`（pixelArea = 2πRH/pixels）、`shaders/loss.slang`（S95 sigmoid loss）。

---

## Python TPS 管线 (`proxy/tps_pipeline/`)

### tps_solver.py — 可微 TPS 求解器

```python
from tps_solver import TPSSolver
solver = TPSSolver(reg=1e-6)

# 正算：螺栓高度 → 曲面
c, d = solver.solve(h)                        # h(35,) → c(35,), d(3,)
w = solver.surface(c, d)                       # 25×25 曲面
w, dwdx, dwdz, nx, ny, nz = solver.surface_with_normals(c, d)

# 反传：dL/dw → dL/dh（通过 A_inv 链式法则）
dL_dc, dL_dd = solver.surface_deriv_coeff_grad(dL_dw)
dL_dh = solver.backward(dL_dc, dL_dd)
```

### validate_surface.py — 面型验证

对比 TPS 代理曲面与 FEA 参考数据，支持梯度检验与优化拟合。

### optimize_heliostat.py — 完整优化管线

TPS + 重力 + 简化光追 + S95 损失 + Adam 优化。

---

## 塔式定日镜物理可实现可微优化程序的管线架构

### 数据流

**核心公式**（板局部坐标系，无 cos(θ) 系数）：

$$w(\mathbf{r}) = UY_{\text{grav}}^{\text{FEA}}(\theta) + \sum_{b=1}^{N_b} h_b \cdot \phi_b^{\text{TPS}}(\mathbf{r})$$

原因：局部坐标系下螺栓沿板法向位移，$\phi_b$ 描述单位位移在此坐标系下的响应，故 $dy/dh = \phi$，无需 cos(θ) 因子。

**完整数据流**（螺栓模式，每个太阳方向独立执行正向+反向）：

```
1. 力学正向: boltForwardSurface()
   螺栓高度 h[35] + 影响函数 φ_b/∂φ_b [35×1024]
     + 重力 FEA bins (0°/30°/45°/60°/75°, 双线性插值)
     → yGrid, yuGrid, yvGrid, nGrid [各 32x32]
     └─ GPU: computeBoltSurface (bolt_forward.slang:18)
     └─ 重力插值: sampleGravityUY() (bolt_common.slang:62)

2. 光学正向: forwardRender()
   读取 yGrid/nGrid → 接收器像素光线 →
   2 层玻璃折射 (2 次随机扰动, TIR 回退) →
   Buie 太阳形状评估 → 能流累加
     → renderedFlux [157×50] (forward.slang:83)
     └─ 子阶段: clearFlux → renderForward → finalizeFlux

3. S95 损失计算:
   computeS95Level() [CPU, pipeline.cpp:1294]
     二分搜索 95% 能量对应的能流阈值
   clearFluxGradient() [GPU, loss.slang]
     清零 fluxGradient[157×50]
   computeS95Loss() [GPU, loss.slang:21]
     每像素: s = sigmoid(6·(flux/level - 1))
     dL/dflux = 6·s·(1-s)/level → fluxGradient

   [可选 MSE 损失] pipeline.cpp:1629-1641
     与理想椭圆面型光斑逐像素比较: dL/dflux = 2·(flux - ideal)/N

4. 光学反向: boltBackwardPass() (pipeline.cpp:841)
   阶段 0: clearSurfaceGradient [GPU]
     清零 surfaceGradient[1024×3]
   阶段 1: renderBackwardBolt (bolt_backward.slang:104)
     bwd_diff(computePixelEnergyBolt)(y, yu, yv, ..., dL)
       → dL/dy_p, dL/dyu_p, dL/dyv_p 逐网格点
     wave-reduce → gradPartial
   阶段 1b: reduceSurfaceGradients (bolt_backward.slang:184)
     跨 group 归约: Σ gradPartial → surfaceGradient[1024×3]
   阶段 2: projectBoltGradients (bolt_backward.slang:209)
     dL/dh_b = Σ_p [ dL/dy_p · φ_b(p)
                   + dL/dyu_p · ∂φ_b/∂u(p)
                   + dL/dyv_p · ∂φ_b/∂v(p) ]
     累加 (+=) → boltHeightGradient[35]

5. 参数更新: boltAdamStep() (bolt_optimizer.slang:25)
   m_b = β₁·m_b + (1-β₁)·g_b
   v_b = β₂·v_b + (1-β₂)·g_b²
   h_b -= lr · m̂/(√v̂ + ε)
```

**完整数据流（C++ 风格伪代码）**：

```cpp
// ═══════════════════════════════════════════════════════════════════════
// 常量与缓冲区
// ═══════════════════════════════════════════════════════════════════════
constexpr int NB    = 35;       // 螺栓数 (7×5)
constexpr int GS    = 32;       // 渲染网格分辨率
constexpr int NPIX  = 157 * 50; // 接收器像素数 (w×h)
constexpr int NGRAV = 5;        // 重力 bin 数 (0°/30°/45°/60°/75°)

// --- GPU 缓冲区 (StructuredBuffer / RWStructuredBuffer) ---
// 预计算静态数据 (Python 离线生成, 一次性上传)
StructuredBuffer<float> influencePhi   [NB * GS * GS];  // φ_b(p)   [35×1024]
StructuredBuffer<float> influencePhiU  [NB * GS * GS];  // ∂φ_b/∂u
StructuredBuffer<float> influencePhiV  [NB * GS * GS];  // ∂φ_b/∂v
StructuredBuffer<float> gravityBin     [NGRAV * GS * GS]; // UY^FEA(θ)

// 可优化参数 + Adam 状态
RWStructuredBuffer<float> boltHeights        [NB];       // h[35]
RWStructuredBuffer<float> boltHeightGradient [NB];       // dL/dh
RWStructuredBuffer<float> boltAdamM          [NB];       // 一阶矩
RWStructuredBuffer<float> boltAdamV          [NB];       // 二阶矩

// 中间结果 (力学正向 → 光学正向)
RWStructuredBuffer<float> yGrid    [GS * GS];       // 板面位移
RWStructuredBuffer<float> yuGrid   [GS * GS];       // ∂y/∂u
RWStructuredBuffer<float> yvGrid   [GS * GS];       // ∂y/∂v
RWStructuredBuffer<float4> nGrid   [GS * GS];       // 法向量 (含 padding)

// 光学正向输出
RWTexture2D<float> renderedFlux [NPIX];             // 能流图 [157×50]

// 反向传播中间量
RWTexture2D<float> fluxGradient    [NPIX];          // dL/dflux
RWStructuredBuffer<float> gradPartial [Ngroups * GS * GS * 3]; // wave-reduce 中间缓冲
RWStructuredBuffer<float> surfaceGradient [GS * GS * 3];       // [dL/dy, dL/dyu, dL/dyv]


// ═══════════════════════════════════════════════════════════════════════
// 阶段 0: 影响函数预计算 (Python 离线, scripts/generate_tps_influence.py)
// ═══════════════════════════════════════════════════════════════════════
//   对每个螺栓 b (0..NB-1):
//     h = e_b                          // one-hot: 仅 h[b]=1, 其余 0
//     [c; d] = A^{-1} · [h; 0,0,0]     // 求解 38×38 TPS 系统
//     φ_b(p)  = Σ_j c_j·r_jp²·log(r_jp²) + d₀ + d₁·x_p + d₂·z_p
//     ∂φ_b(p) = Σ_j c_j·∂φ/∂x|_{jp} · [W 或 L] + d_{1,2} · [W 或 L]
//   补自影响修正: phi_kernel[b, grid_idx(b)] += λ   (λ=1e-6)
//   输出 → influence_phi.bin, influence_phi_u.bin, influence_phi_v.bin
//   加载 → GPU StructuredBuffer binding 19/20/21


// ═══════════════════════════════════════════════════════════════════════
// 优化主循环 (pipeline.cpp:1530)
// ═══════════════════════════════════════════════════════════════════════
void optimize() {
    for (int iter = 0; iter < maxIter; iter++) {
        // 清零梯度累加器
        boltHeightGradient.upload(zeros(NB));

        for (auto& sunDir : trainDirs) {
            float cosTheta = computeCosTheta(sunDir, heliostatPos, aimPoint);
            boltForwardSurface(cosTheta);              // → 阶段 1
            forwardRender();                           // → 阶段 2
            auto flux = readFlux();                    // CPU 读回
            float s95Level = computeS95Level(flux);    // → 阶段 3 (CPU)
            if (s95Level > 0) {
                clearFluxGradient();                   // → 阶段 3a (GPU)
                computeS95Loss(s95Level);              // → 阶段 3b (GPU)
                boltBackwardPass();                    // → 阶段 4
            }
        }
        boltAdamStep(iter + 1);                        // → 阶段 5
    }
}


// ═══════════════════════════════════════════════════════════════════════
// 阶段 1: 力学正向 — boltForwardSurface()  [pipeline.cpp:713]
// ═══════════════════════════════════════════════════════════════════════
// GPU compute shader: computeBoltSurface  [bolt_forward.slang:18]
//   dispatch(1,1,1) — GS×GS 线程并行, 每线程处理一个网格点 (u,v)
void boltForwardSurface(float cosTheta) {
    // 1a. cosθ → 倾角 → 重力 bins 插值参数
    float angleDeg = acos(cosTheta) * 180/π;   // 板法向与竖直夹角
    auto [lo, hi, t] = findGravityBin(angleDeg); // 5 个 bin 间线性插值

    // 1b. GPU 并行: computeBoltSurface
    //     对每个网格点 p(u,v) ∈ [0,GS)×[0,GS):
    parallel_for (u in 0..GS, v in 0..GS) {
        uint idx = v * GS + u;

        // 重力分量: FEA 角度 bins 双线性插值
        float y = sampleGravityUY(idx, lo, hi, t);
        //   = lerp(gravityBin[lo][idx], gravityBin[hi][idx], t)
        //     其中 gravityBin[angle] 是零螺栓 FEA 解的局部 UY 场

        float yu = 0, yv = 0;

        // 螺栓影响函数线性叠加 (查表 + FMA)
        for (int b = 0; b < NB; b++) {
            float phi   = influencePhi [b * GS*GS + idx];  // φ_b(p)
            float phi_u = influencePhiU[b * GS*GS + idx];  // ∂φ_b/∂u
            float phi_v = influencePhiV[b * GS*GS + idx];  // ∂φ_b/∂v
            float h = boltHeights[b];
            y  += h * phi;
            yu += h * phi_u;
            yv += h * phi_v;
        }

        // 法向量: n = -normalize(tu × tv)
        //   tu = (W, yu, 0),  tv = (0, yv, L)
        float3 tu = float3(heliostatWidth,  yu, 0);
        float3 tv = float3(0,                yv, heliostatLength);
        float3 n  = -normalize(cross(tu, tv));

        yGrid [idx] = y;
        yuGrid[idx] = yu;
        yvGrid[idx] = yv;
        nGrid [idx] = float4(n, 0);
    }
    // 输出: yGrid, yuGrid, yvGrid, nGrid [各 GS×GS]  (GPU 持久缓冲)
}


// ═══════════════════════════════════════════════════════════════════════
// 阶段 2: 光学正向 — forwardRender()  [shaders/forward.slang]
// ═══════════════════════════════════════════════════════════════════════
void forwardRender() {
    // 2a. clearFlux:   renderedFlux[:] = 0
    // 2b. renderForward: 每像素发射总Spp根光线 → 累积能流
    //     for each pixel (px, py) ∈ [0,157)×[0,50):
    //       for each subpixel sample s ∈ [0, GS*GS):
    //         (u, v) = grid sample coords  (从 Sobol 序列 / Hammersley)
    //         插值 y, yu, yv, n  from yGrid/nGrid
    //         ray = traceRay(heliostat → receiver pixel)
    //           折射: 2 层玻璃 (每次随机扰动 ±0.5mrad, TIR 回退)
    //           太阳: Buie CSR=0.01 模型评估
    //           面型: 1 mrad 高斯斜率误差
    //         energy = computePixelEnergy(ray, sunDir, ...)
    //         atomicAdd(renderedFlux[px, py], energy)
    // 2c. finalizeFlux: renderedFlux /= totalSpp  (归一化)
    // 输出: renderedFlux [157×50]  (GPU texture, 每像素 W/m²)
}


// ═══════════════════════════════════════════════════════════════════════
// 阶段 3: S95 损失计算  [pipeline.cpp:1294 + shaders/loss.slang]
// ═══════════════════════════════════════════════════════════════════════

// 3a. CPU: 二分搜索 S95 阈值
float computeS95Level(vector<float>& flux) {
    float totalEnergy = Σ flux;             // 总能流
    float target      = 0.95 * totalEnergy; // 目标: 包含 95% 能量
    float lo = 0, hi = max(flux);
    while (hi - lo > 1e-6) {
        float mid = (lo + hi) / 2;
        float sum = Σ_{p: flux[p] >= mid} flux[p];
        if (sum >= target) lo = mid; else hi = mid;
    }
    return lo;  // S95 能流阈值
}

// 3b. GPU: clearFluxGradient  [loss.slang]
//      fluxGradient[:,:] = 0

// 3c. GPU: computeS95Loss  [loss.slang:21]
//      for each pixel p:
//        s = σ(6 · (flux[p] / s95Level - 1))     // sigmoid 平滑阶跃
//        fluxGradient[p] = 6 · s · (1-s) / s95Level   // dL/dflux

// [可选] MSE 损失 (pipeline.cpp:1556-1568):
//        fluxGradient[p] = 2 · (flux[p] - flux_ideal[p]) / Npix


// ═══════════════════════════════════════════════════════════════════════
// 阶段 4: 光学反向 — boltBackwardPass()  [pipeline.cpp:841]
// ═══════════════════════════════════════════════════════════════════════

// 4a. GPU: clearSurfaceGradient [bolt_backward.slang]
//      surfaceGradient[:] = 0   // [GS*GS * 3] 清零

// 4b. GPU: renderBackwardBolt  [bolt_backward.slang:104]
//      dispatch(Npix, kTileCount, 1) — 每像素每 tile 一个 workgroup
//      对每个 (px, py, tile):
//        for each subpixel sample s in tile:
//          重放正向光路 → 自动微分 (bwd_diff)
//            dL/dy_p  += ∂energy/∂y  · dL/dflux[px,py]
//            dL/dyu_p += ∂energy/∂yu · dL/dflux[px,py]
//            dL/dyv_p += ∂energy/∂yv · dL/dflux[px,py]
//        wave-reduce → gradPartial[groupIdx * GS*GS*3 + ...]

// 4c. GPU: reduceSurfaceGradients  [bolt_backward.slang:184]
//      dispatch(1,1,1) — 单 workgroup 跨所有 partial 归约
//      surfaceGradient[p][0..2] = Σ_groups gradPartial[g][p][0..2]

// 4d. GPU: projectBoltGradients  [bolt_backward.slang:209]
//      dispatch(ceil(NB/50), 1, 1) — 50 螺栓/group
//      对每个螺栓 b:
//        dL/dh_b = 0
//        for each grid point p ∈ [0, GS*GS):
//          dL/dh_b += surfaceGradient[p].dL_dy   * influencePhi [b][p]
//                   + surfaceGradient[p].dL_dyu  * influencePhiU[b][p]
//                   + surfaceGradient[p].dL_dyv  * influencePhiV[b][p]
//        boltHeightGradient[b] += dL/dh_b     // 注意: += 跨太阳方向累加
//  输出: boltHeightGradient[35]  (已累加所有太阳方向)


// ═══════════════════════════════════════════════════════════════════════
// 阶段 5: 参数更新 — boltAdamStep()  [bolt_optimizer.slang:25]
// ═══════════════════════════════════════════════════════════════════════
// GPU compute shader, dispatch(1,1,1)
void boltAdamStep(int iteration) {
    float lr = lerp(minLR, initLR, 1.0 - iteration / maxIter);  // 线性衰减

    for (int b = 0; b < NB; b++) {
        float g = boltHeightGradient[b];      // 已累加所有太阳方向

        // Adam 更新
        boltAdamM[b] = β1 * boltAdamM[b] + (1-β1) * g;       // m = β₁·m + (1-β₁)·g
        boltAdamV[b] = β2 * boltAdamV[b] + (1-β2) * g * g;   // v = β₂·v + (1-β₂)·g²

        float m_hat = boltAdamM[b] / (1 - β1^(iter+1));       // 偏差校正
        float v_hat = boltAdamV[b] / (1 - β2^(iter+1));

        boltHeights[b] -= lr * m_hat / (sqrt(v_hat) + ε);     // h -= lr · m̂/(√v̂ + ε)
    }
}


// ═══════════════════════════════════════════════════════════════════════
// 辅助: cosθ 计算 (用于重力角度插值)
// ═══════════════════════════════════════════════════════════════════════
float computeCosTheta(sunDir, heliostatPos, aimPoint) {
    float3 incident  = normalize(sunDir);         // 入射方向
    float3 reflected = normalize(aimPoint - heliostatPos);  // 反射方向
    float3 macroNormal = normalize(incident + reflected);   // 宏观法向
    return abs(macroNormal.y);                    // |n_y| = cos(倾角)
}
```


```cpp
for iter in 0..maxIter:
    boltHeightGradient.clear() // 清零梯度累加器
    fluxMap.clear() // 清零能流图缓存
    for sunDir in trainDirs[0..35]:
        updateUniforms(sunDir, heliostatPos, aimPoint) // 1a. 设置 GPU uniform：太阳方向、定日镜世界坐标、瞄准点
        cosTheta = computeTilt(sunDir, heliostatPos, aimPoint)  // 1b. 根据太阳位置与定日镜方位得出倾角
        boltForwardSurface(cosTheta) // 2. 力学正向：h[35] + 倾角 → 局部板面点云
        forwardRender() // 3. 光学正向：板面点云 → 圆柱接收器能流图
        s95Level = computeS95Level(flux) // 4. CPU：FluxMap上获取 S95 阈值
        if s95Level > 0:
            clearFluxGradient()
            computeS95Loss(s95Level)
            boltBackwardPass() // 5. 光学反向传播（全 GPU）：AD 重放光路 → 链式法则计算 → dL/dh_b

    boltHeightGradient[b] += dL/dh_b // 多太阳方向累加梯度
    boltAdamStep(iter) // 6. Adam优化器更新hb

```

**梯度链总结**（链式法则沿数据流反向传播）：

```
dL/dh_b = Σ_{sun} Σ_{p} [ ∂L/∂flux · (∂flux/∂y · ∂y/∂h_b
                                       + ∂flux/∂yu · ∂yu/∂h_b
                                       + ∂flux/∂yv · ∂yv/∂h_b) ]
其中 ∂y/∂h_b = φ_b(p),  ∂yu/∂h_b = ∂φ_b/∂u,  ∂yv/∂h_b = ∂φ_b/∂v
```

**GPU dispatch 总览**（每太阳方向 × 每迭代）：

| Dispatch | Shader | Grid | 说明 |
|----------|--------|------|------|
| `(1,1,1)` | `computeBoltSurface` | GS² threads | 力学正向 |
| `(1,1,1)` | `clearFlux` | NPIX threads | 清零能流 |
| `(ceil(NPIX/256),1,1)` | `renderForward` | NPIX×tile threads | 光追正向 |
| `(1,1,1)` | `finalizeFlux` | NPIX threads | 归一化 |
| `(1,1,1)` | `clearFluxGradient` | NPIX threads | 清零 dL/dflux |
| `(1,1,1)` | `computeS95Loss` | NPIX threads | S95 sigmoid 损失 |
| `(1,1,1)` | `clearSurfaceGradient` | GS²×3 threads | 清零 surface grad |
| `(NPIX, kTileCount, 1)` | `renderBackwardBolt` | ~7850 groups | 光追反向 + wave-reduce |
| `(1,1,1)` | `reduceSurfaceGradients` | 1 group | 跨 group 归约 |
| `(ceil(NB/50),1,1)` | `projectBoltGradients` | NB threads | 投影到螺栓梯度 |
| `(1,1,1)` | `boltAdamStep` | NB threads | Adam 参数更新 |

### 关键源文件

| 文件 | 功能 |
|------|------|
| `src/pipeline.cpp` | 优化循环 (`optimize`:1452)、S95 计算 (`computeS95Level`:1294)、梯度反传 (`boltBackwardPass`:841)、Adam (`boltAdamStep`:888) |
| `src/main.cpp` | 入口：`--dump-flux`, `--check-grad` |
| `src/config.cpp` | JSON 配置解析 |
| `shaders/bolt_forward.slang` | 曲面计算 `computeBoltSurface` (影响函数 + 重力) |
| `shaders/bolt_backward.slang` | 两阶段梯度反传 (`renderBackwardBolt` → `reduceSurfaceGradients` → `projectBoltGradients`) |
| `shaders/bolt_common.slang` | 影响函数求值 `boltSurfaceAtGrid`、重力插值 `sampleGravityUY` |
| `shaders/forward.slang` | 光线追踪 (`renderForward`)、Bézier 曲面 (`computeBezierSurface`)、能流清零/合并 |
| `shaders/loss.slang` | S95 sigmoid 损失 (`computeS95Loss`)、fluxGradient 清零 (`clearFluxGradient`)、S95 像素计数 |
| `shaders/backward.slang` | Bézier 模式光学反向传播 |
| `shaders/bolt_optimizer.slang` | 螺栓 Adam 优化器 (`adamUpdateBolt`) |
| `shaders/optimizer.slang` | Bézier 模式 Adam 优化器 (`adamUpdate`) |

### S95 计算

`src/pipeline.cpp:1294` — `computeS95Level()`：二分搜索找到 95% 能量对应的能流阈值。
`src/pipeline.cpp:1542` — `pixelArea = 2πRH / totalPixels = 0.1601 m²/pixel`（圆柱接收器）。
`shaders/loss.slang` — sigmoid 平滑 S95 损失：`s = σ(6·(flux/level - 1))`。

### 螺栓坐标

7×5 网格，边距 8%：
- BU = [0.08, 0.22, 0.36, 0.50, 0.64, 0.78, 0.92]（7 列）
- BV = [0.08, 0.29, 0.50, 0.71, 0.92]（5 行）
- BX = (u-0.5)×W, BZ = (v-0.5)×L

### 螺栓后处理

```
h_pipe_final = h_opt - max(h_opt) - 0.5mm    (管线约定, 全部 ≤ -0.5mm)
h_phys       = -h_pipe_final                   (物理约定, 全部 ≥ +0.5mm)
h_stroke     = h_phys - min(h_phys)            (实际螺栓伸出量, 最短=0)
```

S95 不变。物理上等效于将螺栓安装基座沿负法向统一后移。

---

## 验证管线

### 影响函数生成与核函数修正（2026-07-08）

`scripts/generate_tps_influence.py` 生成 6 个 `.bin` 文件供 C++ 管线使用。

**关键修正**：原代码 `phi_kernel = r²·log(r)` 与 TPS 系统矩阵 `tps_kernel(r²) = r²·log(r²)` 不一致（因子 2）。已修正为统一使用 `r²·log(r²)`，self-influence 从 0.53 → 0.97，形变 RMS 减半。

```bash
python scripts/generate_tps_influence.py --output data_vsm_mnvn_tik32
```

### 形变验证

对比 TPS 代理曲面与 FEA 点云，验证代理模型的物理精度。覆盖 4 个条件（0°/29.5°/58.5° 倾角，含/不含重力）。

**数据流**：

```
data_vsm_mnvn_tik32/                   results_vsm_mnvn_300iter/
├── influence_phi.bin [35×32×32]       ├── North_300m_STROKE_bolts.txt (35 个 stroke)
├── gravity_{0,30,45,60,75}deg.bin     ├── node_dump_0deg_{ON,OFF}.csv (FEA, NLGEOM on/off)
                                       └── node_dump_0deg_{grav,nograv}.csv (历史)
       ↓                                      ↓
  w_proxy = gravity_θ + Σ h_b · φ_b      u_grid = load_fea → 投影到板法向 → 32×32 插值
       ↓                                      ↓
                  compare: RMS, R², PV_ratio, shape_corr
                              ↓
                      deformation.png (4×3 面板)
```

**坐标约定**：板绕 **X 轴**旋转。平躺板（0°）板法向=全局 Y，法向位移=UY。倾斜板投影公式：
```
u_local = UY·cos(θ) + UZ·sin(θ)     （+ 号取决于 ANSYS 模型中板的正方向）
Z_SCALE = L / (max(Z_global) - min(Z_global))
```

**关键脚本**：`scripts/validate_fixed.py` — 一体化形变+光斑验证，输出至 `validation_fixed/`。

### 光斑验证（C++ GPU 管线）

使用 C++ Vulkan 光追管线对比 TPS 代理曲面与 FEA 曲面在圆柱接收器上的能流分布。

**数据流**：

```
w_proxy(x,z) / u_fea(x,z)  [25×25]
       ↓
  导出为 surface_*.txt (x z uy 格式)
       ↓
  bezier_opt.exe --dump-flux --surface-file <path> --config <cfg>
       ↓  (Buie 太阳, 玻璃折射, MC Sobol 采样, 1 mrad 斜率误差)
  flux.npy [50×157 float32] → 居中 → Gaussian 滤波 (σ=1.5)
       ↓
  红蓝渐变 colormap (蓝=低, 白=中, 红=高)
  S95 轮廓线 (绿色, 从原始数据计算)
  方位角标注 [-180°, 180°]
       ↓
  flux_proxy_295deg.png / flux_fea_295deg.png
```

**天顶太阳配置**（North 300m 定日镜）：
- 太阳方向: `[0, 1, 0]`，镜面倾角: **29.5°**
- 接收器: 圆柱 R=10m H=20m, 157×50 px
- 定日镜→接收器: `[0, 0, 300]` → `[0, 180, 0]`

**光斑结果评判**：对比峰值能流 (W/m²)、总能量、S95 像素数。形状相关 >0.92 即视为代理模型光学等价。

### NLGEOM 大挠曲验证（2026-07-09）

代理模型是**线性叠加**（gravity + Σ h_b·φ_b）。真实 4mm 薄板在大挠曲下有几何非线性（膜刚化），代理模型不含。用 Mechanical 的 NLGEOM on/off 双解量化其影响。

#### 实验一：带螺栓面型对比（0°，优化后 33mm 行程）

`scripts/validate_nlgeom_0deg.py` → `validation_nlgeom_0deg/`。对比 proxy = gravity_0° + Σ h·φ 与 FEA-ON（NLGEOM）/ FEA-OFF（线性），均含重力。去均值内部 RMS（裁 2 圈边界插值伪影）：

| 对比 | RMS | 含义 |
|------|:---:|------|
| proxy vs FEA-OFF | 1.87 mm | 作为线性模型的保真度 |
| proxy vs FEA-ON | 1.53 mm | 对真实面型的总误差 |
| FEA-ON vs FEA-OFF | 1.29 mm | 纯 NLGEOM 效应 |

- 螺栓是**位移边界条件** → 螺栓节点处 ON≡OFF；NLGEOM 只在螺栓间自由跨起作用（膜应力抬升重力沉降的谷底）。
- 带 33mm 行程时 NLGEOM 仅使 PV 降 6.5%（38.2→35.7mm）；`corr(ON−OFF, 重力形状)=−0.85`，效应集中在重力沉降区。

#### 实验二：纯重力 NLGEOM + gravity 基线选择

`scripts/analyze_nlgeom_gravity.py` → `validation_nlgeom_gravity/`。零螺栓纯重力（`train_data/zero_heights_{ON,OFF}/`），隔离几何非线性对重力沉降本身的影响。

| 倾角 | PV_ON(真实) | PV_OFF(线性) | OFF/ON | 去均值内部 RMS |
|:---:|:---:|:---:|:---:|:---:|
| 0° | 16.8 | 24.4 | **1.45** | 0.92 mm |
| 30° | 13.0 | 18.4 | 1.41 | 0.61 mm |
| 45° | 8.6 | 9.5 | 1.10 | 0.13 mm |
| 60° | 4.2 | 4.4 | 1.04 | 0.03 mm |
| 75° | 1.0 | 1.0 | 1.01 | 0.001 mm |

- **低倾角膜刚化极强**：0° 线性理论高估沉降 **46%**（24.4 vs 16.8mm = 6× 板厚，深陷大挠曲区）；随倾角升高重力法向分量减小、退回线性区，≥45° 可忽略。
- 但 PV 差主要是活塞/边缘；**去均值内部形状差仅 ~0.9mm@0°**（光学相关量）。

**gravity 基线用 ON 还是 OFF？** proxy_ON/OFF 对比真实 FEA-ON（0°，33mm 螺栓）：

| 对比 | RMS_int |
|------|:---:|
| proxy_OFF vs FEA-OFF（叠加校验 = TPS 误差地板） | 1.44 mm |
| **proxy_ON vs FEA-ON（对现实）** | **1.73 mm** ✅ |
| proxy_OFF vs FEA-ON | 1.89 mm |

> **结论：gravity 用 ON（NLGEOM）bins（当前管线正确，保持不变）。** 理由：(1) 更接近现实（1.73 < 1.89）；(2) OFF 的 24.6mm 沉降是线性虚构、物理不可实现，小行程时高估 46%，优化器从 h=0 起步全程都需正确基线；(3) 去均值后纯重力 NLGEOM(0.9mm)≈带螺栓 NLGEOM(1.3mm)，ON 顺带抓住大部分。gravity 与 h 无关 → 破坏严格叠加但不污染梯度。剩余 ~1.3mm 螺栓驱动 NLGEOM 是**线性螺栓项固有局限**，与 gravity 选择无关。⚠️ PV 是误导指标（被钉死在行程处的最大螺栓主导），须用去均值内部 RMS。

### 稠密重力 bin 如何优化 proxy（2026-07-09）

#### 问题

形变验证中 **R² 卡在 ~0.9**，但形状相关（shape corr）却始终 ~0.95+，两者差 ~0.1。ellipse 小凸起工况（`train_data/ellipse_heights/`）12/35/52° 的 R² 只有 0.90/0.90/0.87。光斑形状与 FEA 一致（法向指向对），但 S95 光斑偏小——**小光斑可能是假象**。

#### 原因分析流程（`scripts/analyze_r2_gap.py`）

1. **R² 分解**：对去均值场，$R^2 = 2rk - k^2 = r^2 - (k-r)^2$，其中 $r$=shape corr（Pearson，**尺度无关**），$k=\mathrm{SD_{proxy}}/\mathrm{SD_{fea}}$（幅度比）。**R² 同时惩罚形状 r 与幅度 k，shape corr 只看形状** → 只要 k≠1，R² 必低于 shape corr。逐案验证 R² 与 2rk−k² 完全相等。
2. **测法向**：`slopeCorr = 0.93–0.96`（法向指向吻合 → 光斑形状对），但 `slopeRatio ≈ 0.77–0.82 < 1`（法向幅度偏小 ~20% → 光斑扩散小 → **S95 小一圈**）。这个 **k<1 正是拉低 R² 的元凶**。
3. **排除 TPS 岭回归 λ**：扫 λ ∈ [1e-9, 1e-1]（8 个数量级），自影响、North 幅度 k、螺栓项 PV **几乎不变**。因自影响修正 `phi_kernel[self]+=λ` 把 λ 又加回，重建本质是精确插值。**φ 与 λ 都干净**。
4. **定位到重力**：幅度欠预测只在**重力主导**工况（ellipse k=0.76–0.89）；**螺栓主导**的 North 0°（螺栓=位移边界条件、且在已知 bin 角度）k=0.98、R²=0.99。且重力项走 `sampleGravityUY` 的 `lerp`，**根本不经过 TPS 系统**。→ 根因是**重力沉降随倾角非线性，而 bin 只在 5 个角度已知、做线性 lerp**（凸曲线弦在下方 → 系统性低估中间角度幅度，低角度最重）。
5. **A/B 判决**：用稠密 bin（含 12/35/52° 精确角度，无插值）替换稀疏 bin → 12/35° R² 0.90→**0.98**，幅度 k 0.78→~1.0。**根因确认。**

#### 修复

重力 bin 从 5 个（0/30/45/60/75）加密到 **10 个（0/12/22/30/35/45/52/60/67/75）**：
- `scripts/train_residual/precompute_gravity_bins.py --angles 0 12 22 30 35 45 52 60 67 75`
- `shaders/bolt_common.slang`：`sampleGravityUY` 5→10 bin（bindings 31–40，`kGravityAngles[10]`）
- `src/pipeline.cpp` / `pipeline.h`：`m_gravityBins[10]`、加载循环、descriptor layout/writes（38 binds）、`boltForwardSurface` 角度查找表
- **只动 `.bin` 数据 + bin 数**，不改 φ、不改优化逻辑；bin 间距 ≤15° 使 lerp 残余可忽略

#### 结果

| 角度 | R²(5-bin) | R²(dense) | slopeCorr(5-bin→dense) | PV proxy/FEA(dense) |
|:---:|:---:|:---:|:---:|:---:|
| 12° | 0.905 | **0.985** | 0.957 → **0.994** | 16.53/16.59 |
| 35° | 0.907 | **0.998** | 0.959 → **0.9995** | 12.11/12.15 |
| 52° | 0.887 | **0.962** | 0.931 → **0.996** | 6.91/6.84 |

（内部去均值 R²，12/35/52° 用精确 bin；`scripts/analyze_ellipse_52.py` 独立复核一致）

**R² 全面 ≥0.96、slopeCorr ≥0.994（法向几乎完美对齐）。** 稠密 bin 把幅度(k)与法向幅度同时修复。曾以为 52° 卡在 ~0.92，实为两个人为假象叠加：(1) `validate_ellipse_deform.py` 的 `KNOWN` 角度列表未更新，52° 仍在 45↔60 插值而非用精确 52° bin；(2) R² 用了「整场去均值后裁边」而非标准「内部去均值」（piston 无关）。两者修正后 52°=0.962。残余是 hybrid 帧 cosθ 不一致（全局 uy 帧螺栓过预测 k=1.11 vs 局部 δ 帧重力欠预测 k=0.68，倾角越大越明显），属已接受的建模约定，非 bin 密度/TPS/λ 问题。

### North 300m 倾斜工况验证（29.5°/58.5°，稠密 bin，NLGEOM-ON FEA）

用 10-bin 重优化的 North STROKE 螺栓，对比 29.5°/58.5° 的 FEA（`node_dump_{295,585}deg.csv`）。proxy=`gravity_interp+Σh·φ`（无 cosθ），FEA 投影到板局部法向 `δ=uy·cosθ+uz·sinθ`。脚本 `validate_north_tilt.py`（形变）+ `validate_north_flux.py`（光斑，太阳方向经 computeCosTheta 反解得到目标倾角）。

| 倾角 | 形变 R² | shapeCorr | slopeCorr | k(PV) | fluxCorr | S95px proxy/FEA |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 29.5° | 0.982 | 0.991 | 0.883 | 1.088 | **0.9989** | 1490 / **1633** |
| 58.5° | 0.981 | 0.990 | 0.844 | 1.151 | **0.9980** | 1469 / **1650** |

- **形变**：R²=0.98、shapeCorr=0.99 优秀；slopeCorr 0.84–0.88（33mm 螺栓 + NLGEOM 造尖锐法向，不及 ellipse 的 0.996）；k=1.09–1.15 表明 proxy 在局部帧 **过预测 PV 9–15% = 缺失的螺栓驱动 NLGEOM 膜刚化**（倾角越高越强）。
- **光斑**：fluxCorr ≥0.998、峰值/总能差 ≤5%——**光斑形状与 FEA 几乎一致**（远场对 mm 级曲率不敏感，法向指向对了就够）。
- **但 S95 光斑 proxy 比 FEA 小 ~9–11%**（1490 vs 1633、1469 vs 1650）。**这精确印证「小光斑是假象」**：即便 fluxCorr=0.998，真实 FEA 的 95% 能量包络仍比 proxy 大约一成——proxy 的更紧光斑（更光滑法向、无 NLGEOM 尾部散射）系统性低估了真实光斑尺寸，优化得到的 S95 偏乐观。

```
bezier_opt/
├── src/pipeline.cpp              # C++ 管线（优化循环、梯度、Adam）
├── src/main.cpp                  # 入口（--check-grad, --dump-flux）
├── shaders/                      # Slang GPU shader (.slang + .spv)
├── scripts/
│   ├── generate_tps_influence.py    # TPS 影响函数生成（r²log(r²) 核函数）
│   ├── validate_nlgeom_0deg.py      # 实验一：带螺栓 NLGEOM 面型对比
│   ├── analyze_nlgeom_gravity.py    # 实验二：纯重力 NLGEOM + gravity 基线选择
│   ├── validate_fixed.py            # 一体化形变+光斑验证
│   ├── analyze_300iter.py           # 300 轮优化结果分析
│   └── train_residual/
│       ├── precompute_gravity_bins.py  # 插值重力生成器（argparse, 默认 32×32/ON）
│       └── validate_interpolation.py   # 角度插值验证
├── proxy/
│   ├── tps_pipeline/                # Python TPS 求解器 + 优化器
│   └── validation_utils.py          # 共享 FEA 对比工具
├── data/                         # 太阳方向、椭圆目标、bolt_init
├── data_vsm_mnvn_tik32/           # TPS 影响数据 + FEA 重力 bins (32×32)
│   ├── influence_phi.bin           # φ_b(p) [35×32×32]
│   ├── influence_phi_u/v.bin       # 一阶导数
│   ├── gravity_{0,30,45,60,75}deg.bin  # 各角度 FEA 重力 UY (NLGEOM-ON)
│   └── gravity_angles.json         # 重力角度索引
├── train_data/
│   └── zero_heights_{ON,OFF}/       # 零螺栓纯重力 FEA 点云（NLGEOM on/off）
├── configs/                      # JSON 配置（bolt_vsm_mnvn_300iter, validate_flux）
├── docs/                         # 设计文档 + 调试报告
├── results_vsm_mnvn_300iter/     # 当前优化输出（S95=52.30）+ 带螺栓 FEA 点云
├── validation_nlgeom_0deg/         # 实验一结果（形变对比图 + metrics）
└── validation_nlgeom_gravity/      # 实验二结果（纯重力 NLGEOM + 选择判据）
```

---

## 性能分析 (RTX 4070 SUPER, 32×32 稠密 10-bin, North 300m, 300 iter)

### 计算规模

| 指标 | 数值 |
|---|---|
| 像素 | 7,850 (157×50) |
| 每像素 SPP | 1,024 (32² grid) |
| 每 forward pass 光线 | **8.04 M** |
| 每 iter 光线 (forward, 36 sun) | 289.4 M |
| 每 iter 总光线 (fwd + backward, 36 sun) | **~0.58 B** |
| 300 iter 总光线 | **~174 B** |

### 耗时

| 指标 | 数值 |
|---|---|
| 每 iter 平均 (36 sun) | 5.42s (warmup 6.30s, steady **5.26s**) |
| 每 sun 方向 | **~0.15s** |
| 单 forward pass 光线吞吐 | **~55 M rays/s** |
| total (300 iter) | 1,324s (**~22 min**) |
| warmup | 前 5 iter +20% (shader 编译/GPU 升温) |

### GPU dispatch (每 iter)

| 阶段 | 组数 | 线程/组 | 说明 |
|---|---|---|---|
| boltForwardSurface | 1 | 1,024 | 查表叠加 35 螺栓 |
| forwardRender | **31,400** | 256 | 光追: 双折射 + Buie 太阳 + wave-reduce |
| boltBackward Stage 1 | 31,400 | 256 | 自微分光追 + 组内归约 |
| reduceSurfaceGradients | 12 | 256 | 跨组归约 → 1024×3 |
| projectBoltGradients | 1 | 35 | 投影梯度到螺栓 |
| Adam | 1 | 35 | — |
| **总计/iter** | **~1.13 M dispatches** | | |

### GPU 显存

| 缓冲 | 大小 | 用途 |
|---|---|---|
| Sobol pool (2²⁶) | **268 MB** | MC 采样随机数 (6 floats/ray, pool 覆盖 1.4× 需量) |
| gradPartial | **386 MB** | 反向中间: 4 tiles × 7850 px × 1024 grid × 3 ch × 4B |
| influence phi+phiU+phiV | 420 KB | 预计算, 35×1024×3 |
| gravity bins | 40 KB | 10 角度 × 1024 |
| 其他 (surface, flux, Adam...) | <10 MB | — |
| **总计** | **~650 MB** | |

### 加速可能

**瓶颈**: forwardRender (~55%) + boltBackward (~35%) 占每 iter 的 ~90%。每条光线含 2 层玻璃折射 (2 次随机扰动, TIR 回退) + Buie 太阳形 + 距离衰减——几何光学部分几乎不可约。

| 方向 | 预期收益 | 难度 | 说明 |
|---|:---:|:---:|---|
| **减少 SPP** | ++ | 低 | 32²=1024 光线/pixel, 25²=625 省 ~40% — 但可能回归收敛质量, 需实测 |
| **gradPartial 减容** | + | 中 | 386 MB 是最大单缓冲; 改用 fp16 半精度可减半; 或用 tile-batch 逐 tile 归约避免全量分配 |
| **多 sun 并行** | +++ | 中 | 当前 36 sun 串行; GPU 利用率不足 (单 sun 只需 ~0.15s). 将 sun 方向合并到 batch 维度, forward 派发时按 sun 索引分流 → 减少 36× 的 dispatch overhead, 预期加速 1.5–2× |
| **Sobol pool 优化** | + | 低 | 2²⁶=67M 可缩到 2²⁴=16M; 当前 6 floats/ray × 8M rays = 48M, pool 仅 1.4× 覆盖; 换 LCG/tiny-ptr hash 可销池 |
| **forward 截止优化** | + | 低 | 大量像素 (init 即 3850/7850≈49% 非零) 但在边缘区接收器 dc≤0 时可 early-out; `InterlockedOr` 的 rayValidity mask 已有, 但 forward 阶段未用于跳过死像素——反向已利用 |
| **光线包 (wavefront)** | ++ | 高 | 当前 wave-reduce 在线程组内做, 跨组归约另起 12 组; 可用 indirect dispatch + atomic 累加器替代 31,400 组 partial → 直接累加到 surfaceGradient, 省掉整个 Stage 1b 和 gradPartial 缓冲 |
| **双精度 → 单精度** | 0 | — | 已全 fp32 |

**总结**: 最大瓶颈在 36 sun 串行派发 (GPU 吃不饱) + gradPartial 386MB (最大缓冲)。多 sun 并行 + 直接累加器归约可合并 **砍掉 gradPartial 缓冲并消除 dispatch overhead**, 预计总优化时间 22min → **8–10min**。减少 SPP 是独立的快速收益, 但需权衡收敛质量。

---

## 参数速查

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
| 学习率 (零初始) | 2×10⁻⁴ |
| Adam β₁, β₂ | 0.9, 0.999 |

## 后续方向

| 优先级 | 方向 | 说明 | 难度 |
|:---:|------|------|:---:|
| P0 | 排查 S95 数值偏高（零初始 ~228 vs 文献理想椭圆 ~43 m²） | 涉及 `computeS95Level`(pipeline.cpp:1294)、`pixelArea`(1542)、sigmoid loss(loss.slang) | 中 |
| P1 | 螺栓驱动 NLGEOM 修正（行程相关影响函数 / 非线性残差项） | 消除剩余 ~1.3mm 面型误差（线性螺栓项固有局限） | 高 |
| P1 | gravity bins 溯源统一 | 现役 tik32 bins 与 `zero_heights_ON` 重算差 ~1.8mm（来源为重命名前的 zero_heights）；用 `precompute_gravity_bins.py` 重生成并重跑验证 S95 | 低 |
| P2 | 32×32 多角度端到端 S95 验证 | NLGEOM 影响与 gravity=ON 已确认，做最终物理正确性确认 | 中 |
| P2 | C++ shader 直接 TPS（替代 .bin 预计算） | 消除中间步骤，支持任意分辨率 | 高 |

> **已完成（2026-07-09）**：fluxPartial tile 数 bug 修复（32×32 从卡死 145 → 收敛 52.30 m²，与 25×25 恢复 parity）；TPS 自影响修正（~0.53→~1.0）；NLGEOM 影响量化 + gravity=ON 确认。
