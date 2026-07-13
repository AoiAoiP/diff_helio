# 可微渲染中分支不连续性问题：四篇核心论文算法详解

**编写日期**: 2026-06-02  
**背景**: bezier_opt 项目中 Slang `bwd_diff` 对玻璃光学路径（2层折射+反射）求导时出现 8/16 控制点梯度符号错误。简化 nor1=nor2 后改善至 1/16，但仍未完全解决。本文分析四篇相关论文的算法，探讨解决方案。

---

## 论文 1: Aδ — 不连续程序的自动微分 (SIGGRAPH 2022)

**标题**: Aδ: Autodiff for Discontinuous Programs — Applied to Shaders  
**作者**: Yuting Yang, Connelly Barnes, Andrew Adams, Adam Finkelstein  
**机构**: Princeton University, Adobe Research  
**DOI**: 10.1145/3528223.3530125

### 核心问题

标准 AD 假设函数连续。当遇到 `if/else` 分支时，只对**被采取的分支**求导，忽略了**分支边界处的 Dirac delta 贡献**。这导致包含大量分支的渲染程序（着色器）梯度错误。

### 核心创新

**预滤波盒式核 (Prefiltered Box Kernel)**：不去精确采样不连续点（测度为零），而是在采样轴上用一个 1D 盒式核对函数做预滤波，使不连续处的梯度变为可计算的有限值。

### 数学原理

对于一个不连续函数 `f(x, θ) = H(g(x, θ))`（其中 H 是阶跃函数）：

```
经典 AD: ∂f/∂θ = 0  （错误——忽略了断点处的 Dirac delta）

预滤波后: f̂ = ∫ f(x, θ) · K(x - x') dx  （K 是盒式核）
         ∂f̂/∂θ = (1/2ε) · ∂g/∂θ  （当 |g| < ε 时）
```

**关键洞察**: 用盒式核（分段常数）进行预滤波后，梯度计算简化为**检查不连续点是否在核范围内**，不需要解析求逆或递归搜索断点位置。

### 算法流程

```
Algorithm: Aδ Gradient for Discontinuous Programs
===================================================

Input:  程序 f(x, θ), 采样轴 x, 参数 θ, 核半宽 ε
Output: ∂f̂/∂θ (预滤波梯度近似)

Step 1: 识别 Dirac 参数
  对程序进行静态分析，找出所有出现在阶跃函数 H(g(x,θ))
  参数位置中的变量 → 标记为 Dirac 参数

Step 2: 沿采样轴配对采样
  对采样轴上的每对相邻样本 (x_i, x_{i+1}):
    计算 f(x_i) 和 f(x_{i+1})
    若 f(x_i) ≠ f(x_{i+1}):  # 两个样本间存在不连续

Step 3: 预滤波梯度计算
  对每个参数 θ_j:
    若 θ_j 是 Dirac 参数:
      # 使用预滤波梯度规则
      ∂f̂/∂θ_j = (1/2ε) · ∂g/∂θ_j  if |g| < ε else 0
    若 θ_j 不是 Dirac 参数:
      # 回退到标准 AD
      ∂f̂/∂θ_j = 标准 AD 梯度

Step 4: 多轴组合
  若存在多个采样轴:
    对每个轴独立执行 Step 2-3
    最终梯度 = 各轴梯度的加权平均

Step 5: 生成梯度程序
  将上述规则编译为目标后端代码 (TensorFlow/PyTorch/Halide/GLSL)
```

### 三项假设

| 假设 | 含义 | 如何满足 |
|------|------|---------|
| A1 | 每对相邻样本间最多一个不连续点 | 足够高的采样频率 |
| A2 | 样本对的函数值和偏导数可估计样本间任意位置的梯度 | 局部 Lipschitz 连续 |
| A3 | 大多数不连续点可投影到采样轴 | 选择合适的采样轴 |

### 时间复杂度

**O(1)** 相对于参数维度——无论有多少参数，只需沿采样轴采样一次。有限差分的复杂度是 O(n)。

---

## 论文 2: Smoothing Methods for AD Across Conditional Branches (IEEE Access 2023)

**标题**: Smoothing Methods for Automatic Differentiation Across Conditional Branches  
**作者**: Justin N. Kreikemeyer, Philipp Andelfinger  
**DOI**: 10.1109/ACCESS.2023.3342136

### 核心问题

程序的**条件分支**（`if/else`、`switch`）在分支边界处产生不连续性。标准 AD 只能看到被采取分支的局部梯度，看不到"如果走另一条分支会怎样"的信息。这导致：
- 梯度偏差（bias）
- 无法跨分支优化

### 核心创新

提出两种互补方法：
1. **Smooth Interpretation (SI)**: 用概率化语义替代确定性分支
2. **DiscoGrad (DGO)**: 蒙特卡洛梯度估计器，不需 SI 的高斯假设

### 方法一: Smooth Interpretation (SI)

**核心思想**: 将每个分支条件替换为随机变量，使程序本身变得可微。

```
原程序:                    平滑后:
if (x > 0):                p = σ(x / τ)     # sigmoid 概率
  y = f(x)                 y_smooth = p·f(x) + (1-p)·g(x)
else:                      # τ 控制平滑程度
  y = g(x)
```

梯度: `∂y/∂x = σ'(x/τ)/τ · (f(x) - g(x)) + σ(x/τ)·f'(x) + (1-σ(x/τ))·g'(x)`

当 τ → 0: 恢复原始程序；τ 越大: 越平滑。

### 方法二: DiscoGrad (DGO)

**核心思想**: 不修改原始程序，而是在分支边界处用蒙特卡洛估计梯度。

```
Algorithm: DiscoGrad (DGO)
============================

Step 1: 前向执行
  对给定参数 θ，执行原始程序
  记录: 被采取的分支路径、中间值

Step 2: 分支边界检测
  对每个分支条件 c(x, θ):
    计算 ∂c/∂θ  # 条件对参数的敏感度
    若 |c| < δ:  # 近分支边界
      标记为边界样本

Step 3: 边界梯度估计
  对每个边界样本:
    # 扰动参数，检查分支是否翻转
    θ⁺ = θ + Δθ  (沿 ∂c/∂θ 方向)
    y⁺ = f(θ⁺)    # 可能走不同分支
    y⁻ = f(θ⁻)    # 另一侧
    Δy = y⁺ - y⁻  # 跨分支差异
    
    ∂y/∂θ += Δy · K(c/δ) / Δθ  # K 是核函数

Step 4: 与标准 AD 组合
  总梯度 = AD(连续路径) + DGO(边界贡献)
```

### SI vs DGO 对比

| | SI | DGO |
|---|-----|-----|
| 程序修改 | 需要（概率化分支）| 不需要 |
| 假设 | 高斯核平滑 | 无分布假设 |
| 精度 | τ→0 时精确 | 蒙特卡洛无偏 |
| 计算开销 | 低（单次前向+反向）| 中（需额外边界采样）|

---

## 论文 3: Projective Sampling for Differentiable Rendering (SIGGRAPH Asia 2023)

**标题**: Projective Sampling for Differentiable Rendering of Geometry  
**作者**: Ziyi Zhang, Nicolas Roussel, Wenzel Jakob  
**机构**: EPFL  
**DOI**: 10.1145/3618385

### 核心问题

可微渲染中，**物体轮廓处的可见性突变**产生 Dirac delta 梯度。标准 AD 只对可见区域求导（内部项），丢失了边界项。现有的边界采样方法效率低——盲目搜索边界，不按贡献比例采样。

### 核心创新

**投影采样 (Projective Sampling)**：将前向渲染的 interior 采样点**投影到最近的轮廓边界**上，用这些投影点作为微分阶段的采样分布。这自然实现了**按贡献比例的重要性采样**——渲染中有贡献的像素附近边界贡献也大。

### 数学原理

可微渲染的 Reynolds 传输定理：

```
dI/dθ = ∫_interior ∂f(x,θ)/∂θ dx  +  ∫_boundary Δf · v·n dσ
         └── 内部项（AD 能处理）──┘    └── 边界项（AD 看不到！）──┘
```

其中 Δf = f_outside - f_inside（跨边界的着色差异），v 是边界移动速度，n 是边界法向。

**简化公式**：边界项 = ∫ (f_outside - f_inside) · (∂p/∂θ · n) dσ

### 算法流程

```
Algorithm: Projective Sampling
================================

Forward Pass (前向渲染 — 执行一次):
  1. 常规路径追踪 → N 个 interior 采样点 {x_i}
  2. 对每个 x_i:
     a. 搜索最近的 silhouette 边界点 b_i
        - 三角网格: 检测相邻三角面的可见性
        - 隐式曲面 (SDF): 沿 SDF 梯度方向搜索零值面
        - Bézier 曲线纤维: 解析计算边界参数
     b. 计算投影权重 w_i = 1/dist(x_i, b_i)  # 近边界权重大
  3. 输出: {(b_i, w_i)} — 投影边界点 + 权重

Differential Pass (梯度计算):
  4. 对每个投影边界点 b_i:
     a. 采样边界两侧: 计算 f_outside(b_i) 和 f_inside(b_i)
     b. 计算几何导数: ∂p(b_i)/∂θ (边界位置对参数敏感度)
     c. 计算法向: n(b_i)
  5. 边界贡献 = Σ_i w_i · (f_outside - f_inside) · ∂p/∂θ · n
  6. 内部贡献 = 标准 AD: Σ_j ∂f(x_j)/∂θ

组合:
  7. 总梯度 = AD(内部) + Projective Sampling(边界)
```

### 支持的几何表示

| 表示 | 边界检测方法 |
|------|------------|
| 三角网格 | 相邻面可见性差异检测 |
| 隐式曲面 (SDF) | 沿 SDF 梯度搜索零值面 |
| **Bézier 曲线纤维** | **解析计算边界参数** |

### 优势

- **不需修改前向渲染**：完全解耦
- **自动重要性采样**：前向采样分布 ≈ 梯度贡献分布
- **方差低**：投影点自然集中在贡献大的边界位置

---

## 论文 4: Differentiable Rendering of Neural SDFs through Reparameterization (SIGGRAPH Asia 2022)

**标题**: Differentiable Rendering of Neural SDFs through Reparameterization  
**作者**: Sai Bangaru, Gharbi, Luan, Li, Sunkavalli, Hasan, Bi, Xu, Bernstein, Durand  
**机构**: MIT, Adobe, Google  
**DOI**: 10.1145/3550469.3555397

### 核心问题

基于三角形网格的可微渲染已有成熟的边界处理方法（重参数化、边界采样），但**神经隐式曲面 (Neural SDF)** 缺乏显式的边界参数化——无法直接应用这些方法。标准 AD 在隐式曲面的轮廓处产生错误梯度。

### 核心创新

**轮廓感知重参数化 (Silhouette-Aware Reparameterization)**：在球体追踪 (sphere tracing) 的求积点上构造**连续扭曲函数 (warping function)**，将遮挡不连续性从被积函数中移除，使 AD 能产生正确的几何梯度。

### 数学原理

隐式曲面渲染的被积函数在物体轮廓处有阶跃不连续：

```
传统路径: I(θ) = ∫ L(x) · V(x, θ) · G(x, θ) dx
                                    ↑
                    可见性函数 V 在轮廓处不连续

重参数化后: I(θ) = ∫ L(x̃(θ)) · G̃(x̃(θ), θ) · |∂x̃/∂x| dx
              ↑ 坐标变换使被积函数连续
```

### 算法流程

```
Algorithm: Silhouette-Aware Reparameterization
================================================

Step 1: 球体追踪采样
  对每条光线:
    沿光线方向进行球体追踪
    记录 SDF 求积点序列 {p_k} 和对应的 SDF 值 {s_k}

Step 2: 轮廓检测
  对每个求积点 p_k:
    若 SDF(p_k) < δ_threshold:  # 近表面
      计算表面法向 n = ∇SDF(p_k)
      计算光线方向与法向的夹角
      若 |dot(ray_dir, n)| < ε:  # 近轮廓（grazing angle）
        标记为轮廓邻域点

Step 3: 构造扭曲函数
  对每个轮廓邻域点:
    按采样轴（图像平面方向）构造局部扭曲:
      x̃ = x + w · max(0, δ - |x - x_boundary|)
      其中 w 指向最近的轮廓边界，δ 是扭曲范围

Step 4: 被积函数重参数化
  对每个求积点应用扭曲:
    Ĩ(θ) = Σ_k L(x̃_k) · V(x̃_k, θ) · G̃(x̃_k, θ)
    经过扭曲后，V(x̃_k, θ) 对 θ 连续  # 关键性质

Step 5: AD 求导
  对重参数化后的 Ĩ(θ) 直接使用 AD:
    ∂Ĩ/∂θ = Σ_k AD(L(x̃_k) · G̃(x̃_k, θ))
    # 不需要额外的边界采样！
```

### 关键性质

- **不需显式表示边界**：通过扭曲函数隐式处理
- **与球体追踪兼容**：直接嵌入现有渲染流程
- **AD 即插即用**：重参数化后标准 AD 就产生正确梯度

---

## 四篇论文方法对比

| | Aδ (2022) | Smoothing (2023) | Projective Sampling (2023) | SDF Reparam (2022) |
|---|---|---|---|---|
| **处理方式** | 预滤波盒式核 | 平滑替换 / 蒙特卡洛 | 投影到边界 | 坐标重参数化 |
| **是否改程序** | 否（编译器处理）| SI: 是 / DGO: 否 | 否 | 是 |
| **通用性** | 高（任意 DSL 程序）| 极高（任意程序）| 中（渲染专用）| 低（SDF 专用）|
| **复杂度** | O(1) vs 参数维度 | O(1) / O(边界数) | O(边界数) | O(1) |
| **精度保证** | 一阶正确性证明 | 蒙特卡洛无偏 | 渐近无偏 | 可微保证 |
| **对 Slang 兼容性** | ⭐⭐⭐ 类似思路 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ |

---

## 对我们项目 (bezier_opt) 的启示

### 问题本质

我们的 `computePixelEnergy` 包含以下不连续分支：

```hlsl
// 分支 1: 全内反射边界
d2 = (kEnter > 0) ? refract(...) : (0,0,0);      

// 分支 2: 玻璃内部传播
if (length(d2) > kEpsilon) { ... }                

// 分支 3: 第二表面全内反射
if (kExit > 0) { outRG = refract(...); }          

// 分支 4: 全反射 fallback
if (length(outRG) <= kEpsilon) outRG = reflect(...); 

// 分支 5: 太阳形状双区模型
if (sunTheta <= 0.00465) { ... }                  // 内区
else if (sunTheta <= 0.0436) { ... }              // 外区
```

Slang 的 `bwd_diff` 使用 **primal tracing**（记录正向执行路径，反向沿相同路径传播梯度）。当参数扰动导致分支条件翻转时（例如 `kEnter` 从正变负），标准 AD 无法捕获"跨分支"的梯度贡献。

### 启示 1: 平滑替代 (来自 Aδ + Smoothing Methods)

**最可实施的方案**。用平滑函数替换硬分支：

```hlsl
// 原代码
d2 = (kEnter > 0) ? normalize(etaE*dir - ...) : float3(0,0,0);

// 平滑替代
float weight = 1.0 / (1.0 + exp(-kEnter * 1000.0));  // sigmoid
float3 d2_refract = normalize(etaE * dir - (etaE*ndi + sqrt(max(kEnter,0)))*nor1);
float3 d2 = weight * d2_refract;  // 平滑过渡
```

**优点**：实现简单，兼容 Slang 现有 AD  
**缺点**：引入近似误差，需要调平滑参数

### 启示 2: 跨分支梯度补偿 (来自 Aδ + DiscoGrad)

对近边界的采样点，显式计算"如果分支翻转"的梯度贡献：

```hlsl
// 对每个采样点
float grad_AD = bwd_diff(computePixelEnergy)(...);  // 标准 AD

// 边界检测
if (abs(kEnter) < threshold) {
    // 计算分支翻转的能量差异
    float E_TIR = 0.0f;  // 全内反射情况
    float E_refract = computePixelEnergy_with_refraction(...);
    float delta_E = E_refract - E_TIR;
    // 边界梯度补偿
    grad_AD += delta_E * d(kEnter)/d(controlY) * kernel(kEnter/threshold);
}
```

**优点**：精确处理分支边界  
**缺点**：需要在 Slang 中手动实现，增加计算量

### 启示 3: 采样轴设计 (来自 Aδ)

Aδ 的核心假设是大多数不连续点可以投影到少数采样轴。在我们的场景中：
- **太阳方向轴**：太阳形状的两个区域（内区/外区）的分支
- **入射角轴**：全内反射的分支

可以沿这些"自然轴"添加额外的前向采样点，用有限差分估计跨分支梯度。

### 启示 4: 保持折射的必要性 (来自 RMCRT 论文)

RMCRT 论文 (Lin et al. 2022) 的结论：

| 指标 | 折射 vs 纯反射 |
|------|---------------|
| 最大通量 (MaxRF) | 降低 25~80% |
| 总能量 | 降低 1~50% |
| S95 面积 | 增加 50~200% |

**折射对通量分布有不可忽略的影响**。简单反射不能替代折射。我们的 forward 和 backward 必须一致地包含折射。

### 推荐实施路径

| 优先级 | 方案 | 预期效果 |
|--------|------|---------|
| **P0** | 平滑替代 (sigmoid/softplus 替换硬分支) | 消除 8/16 符号错误 |
| **P1** | DGO 风格边界补偿（对近 TIR 点） | 处理极端入射角 |
| **P2** | 采样轴增强（沿关键轴增加稀疏采样） | 覆盖多分支场景 |

**最简起步**: 修改 `computePixelEnergy` 和 `renderForward`，用 `softplus(kEnter)/softplus(kExit)` 替代 `kEnter > 0 ?` 和 `kExit > 0 ?` 硬分支。这只需要几行改动，理论上能解决大部分梯度符号错误问题。
