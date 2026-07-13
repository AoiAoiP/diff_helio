# 力学端数据流：从螺栓高度到镜面形状

## 0. 总览

```
OFFLINE (一次, ~120s)
  ┌─────────────────────────────────────────────┐
  │ 板方程 + BC → MFS系统矩阵 → φ_b[35×25×25]   │
  │ 保存为 7 个 .bin 文件 (~515 KB)              │
  └─────────────────────────────────────────────┘
         │
         ▼
ONLINE (每轮迭代, ~1.2ms GPU)
  ┌─────────────────────────────────────────────────┐
  │ h[35] → Σ h_b·φ_b → w[625] → 法线 → 光学渲染   │
  └─────────────────────────────────────────────────┘
```

---

## 1. 代理模型分类

两种代理模型共享相同的在线数据流，差异仅在离线阶段的 φ_b 生成方式。

| 特性 | TPS | VSM (Virtual Source Method) |
|------|-----|------|
| **全称** | Thin-Plate Spline | Virtual Source Method |
| **PDE** | ∇⁴w = 0 (无限大板) | ∇⁴w = 0，M_n = V_n = 0 (自由边) |
| **源点布局** | 35 螺栓位置 | 35 螺栓 + 320 域外 + 3 多项式 |
| **系统规模** | 38×38 (满秩) | 358×358 (正则化) |
| **求解方法** | LU 分解 (精确) | SVD + Tikhonov λ=10⁻⁵ |
| **自影响** | ~1.000 (精确) | 0.918 (正则化折中) |
| **边界 BC** | 无 | M_n=0, V_n=0 (Kirchhoff 自由边) |
| **数据目录** | `data_tps25/` | `data_vsm_tik25/` |

---

## 2. TPS 离线数据生成

### 2.1 数学原理

TPS 核是双调和方程 ∇⁴w = 0 在**无限大平面**上的基本解：

$$\phi_{\text{TPS}}(r) = r^2 \log(r^2)$$

解的形式：

$$w(\mathbf{r}) = \sum_{b=1}^{35} c_b \cdot \phi_{\text{TPS}}(\|\mathbf{r} - \mathbf{r}_b\|) + p_0 + p_1 x + p_2 z$$

### 2.2 系统组装与求解

对每个螺栓 k ∈ [0..34]，求解 38×38 线性系统：

$$\begin{bmatrix} \Phi & \mathbf{1} & \mathbf{x} & \mathbf{z} \\ \mathbf{1}^T & 0 & 0 & 0 \\ \mathbf{x}^T & 0 & 0 & 0 \\ \mathbf{z}^T & 0 & 0 & 0 \end{bmatrix} \begin{bmatrix} \mathbf{c} \\ p_0 \\ p_1 \\ p_2 \end{bmatrix} = \begin{bmatrix} \mathbf{e}_k \\ 0 \\ 0 \\ 0 \end{bmatrix}$$

其中 $\Phi_{ij} = \phi_{\text{TPS}}(\|\mathbf{r}_i - \mathbf{r}_j\|)$，$\mathbf{e}_k$ 为第 k 个标准基向量。

**特点**：38×38 满秩矩阵，LU 分解直接求解，自影响精确为 1.0。

### 2.3 网格求值

对每个螺栓 b ∈ [0..34]，在 25×25 = 625 个网格点 (u, v) 上求值：

$$u_i, v_j = \frac{i}{24}, \frac{j}{24} \quad (i,j = 0..24)$$

物理坐标：$x = (u - 0.5) \cdot 12.84$ m，$z = (v - 0.5) \cdot 9.45$ m

$$\varphi_b(u,v) = \sum_{j=0}^{34} c_{b,j} \cdot \phi_{\text{TPS}}(r_j) + p_{0,b} + p_{1,b} \cdot x + p_{2,b} \cdot z$$

其中 $r_j^2 = (x - x_j^{\text{bolt}})^2 + (z - z_j^{\text{bolt}})^2$。

### 2.4 导数计算

光学管线还需要 φ 的一阶和二阶导数（用于法线计算和曲率 loss）：

| 导数 | 解析式 | 管线用途 |
|------|--------|---------|
| $\partial\varphi/\partial u$ | $\partial\varphi/\partial x \cdot W$ | 表面法线 |
| $\partial\varphi/\partial v$ | $\partial\varphi/\partial z \cdot L$ | 表面法线 |
| $\partial^2\varphi/\partial u^2$ | $\partial^2\varphi/\partial x^2 \cdot W^2$ | 曲率 loss |
| $\partial^2\varphi/\partial v^2$ | $\partial^2\varphi/\partial z^2 \cdot L^2$ | 曲率 loss |
| $\partial^2\varphi/\partial u\partial v$ | $\partial^2\varphi/\partial x\partial z \cdot WL$ | 曲率 loss |

TPS 核的解析导数：
- $\partial\phi/\partial x = 2x(1 + \log r^2)$
- $\partial^2\phi/\partial x^2 = 2\log r^2 + 4x^2/r^2 + 2$

### 2.5 输出文件

| 文件 | 维度 | 字节 | 内容 |
|------|:---:|:---:|------|
| `influence_phi.bin` | 35×25×25 | 85 KB | φ_b(p) |
| `influence_phi_u.bin` | 35×25×25 | 85 KB | ∂φ_b/∂u |
| `influence_phi_v.bin` | 35×25×25 | 85 KB | ∂φ_b/∂v |
| `influence_kxx.bin` | 35×25×25 | 85 KB | ∂²φ_b/∂u² |
| `influence_kzz.bin` | 35×25×25 | 85 KB | ∂²φ_b/∂v² |
| `influence_kxz.bin` | 35×25×25 | 85 KB | ∂²φ_b/∂u∂v |
| `gravity_y.bin` | 25×25 | 2.4 KB | 重力下垂 w_grav(p) |
| **总计** | — | **~515 KB** | |

---

## 3. VSM (Virtual Source Method) 离线数据生成

### 3.1 数学原理

VSM 将 PDE 的解表示为 TPS 基本解的线性组合，源点放置在**域外**以避免奇异性：

$$w(\mathbf{r}) = \sum_{j=1}^{355} c_j \cdot \phi_{\text{TPS}}(\|\mathbf{r} - \mathbf{r}_j^{\text{src}}\|) + p_0 + p_1 x + p_2 z$$

**源点分类**：
- **螺栓源点** (35 个)：直接放在螺栓位置
- **域外源点** (320 个)：矩形域外 δ=2m 处，每边 80 个
- **多项式项** (3 个)：p₀, p₁x, p₂z（保证解的唯一性）

### 3.2 系统组装

构建 358×358 线性系统 **A**：

| 行范围 | 数量 | 约束类型 | 物理含义 |
|--------|:---:|------|------|
| 0..34 | 35 | $w(\mathbf{r}_i) = \delta_{ib}$ | 螺栓位移约束 |
| 35..194 | 160 | $M_n = 0$ | 边界法向弯矩为零 |
| 195..354 | 160 | $V_n = 0$ | 边界等效剪力为零 |
| 355..357 | 3 | $\Sigma c_j=0$, $\Sigma c_j x_j=0$, $\Sigma c_j z_j=0$ | 正则化 |

**算子详情**：

**弯矩算子** $\mathcal{M}_n[\phi] = -D(\partial^2\phi/\partial n^2 + \nu \cdot \partial^2\phi/\partial t^2)$：

$$A_{ij}^{\text{M}_n} = \mathcal{M}_n[\phi_{\text{TPS}}](\mathbf{r}_i^{\text{bc}} - \mathbf{r}_j^{\text{src}})$$

**等效剪力算子** $\mathcal{V}_n[\phi] = -[\partial^3\phi/\partial n^3 + (2-\nu)\partial^3\phi/\partial n\partial t^2]$：

$$A_{ij}^{\text{V}_n} = \mathcal{V}_n[\phi_{\text{TPS}}](\mathbf{r}_i^{\text{bc}} - \mathbf{r}_j^{\text{src}})$$

两个算子均涉及 TPS 核在边界配置点处的二阶和三阶解析导数。

### 3.3 SVD 求解与 Tikhonov 正则化

**SVD 分解**：$\mathbf{A} = \mathbf{U} \boldsymbol{\Sigma} \mathbf{V}^T$，其中 $\boldsymbol{\Sigma} = \text{diag}(\sigma_1, \ldots, \sigma_{358})$

**关键数值**：
- $\sigma_{\max} = 46950$，$\sigma_{\min} \approx 8 \times 10^{-13}$
- SVD 有效秩 ≈ 158/358（仅 44% 的奇异值独立）
- 直接使用 `rcond=1e-8` 硬截断会损失螺栓约束精度

**Tikhonov 正则化伪逆**：

$$\mathbf{A}^+_\lambda = \mathbf{V} \cdot \text{diag}\!\left(\frac{\sigma_i}{\sigma_i^2 + \lambda^2}\right) \cdot \mathbf{U}^T$$

$\lambda = 10^{-5}$ 在螺栓约束满足（自影响 0.918）和边界条件满足（$\max|V_n| < 0.005$）之间取得最优平衡。

**影响函数系数**（35 次求解，每次 RHS = $\mathbf{e}_b$）：

$$\mathbf{C} = \mathbf{A}^+_\lambda \cdot \mathbf{I}_{358 \times 35} \quad\in \mathbb{R}^{358 \times 35}$$

### 3.4 网格求值

与 TPS 相同（第 2.3 节），但源点集合不同——包含 320 个域外源点：

$$\varphi_b(\mathbf{r}) = \sum_{j=0}^{354} C_{j,b} \cdot \phi_{\text{TPS}}(\|\mathbf{r} - \mathbf{r}_j^{\text{src}}\|) + C_{355,b} + C_{356,b} \cdot x + C_{357,b} \cdot z$$

### 3.5 验证指标

| 指标 | TPS | VSM | 理想值 |
|------|:---:|:---:|:---:|
| 自影响（精确位置） | ~1.000 | 0.918 | 1.000 |
| $\max\|M_n\|$ (边界) | 0.126 | 0.007 | 0 |
| $\max\|V_n\|$ (边界) | N/A | 0.004 | 0 |
| RMS vs FEA (纯螺栓) | 1.67mm | 2.03mm | 0 |
| $R^2$ vs FEA | 0.972 | 0.959 | 1.000 |

### 3.6 源点密度分析

| 每边配置点 | 总源点 | 有效秩 | 自影响 | $\max\|V_n\|$ | 评价 |
|:---:|:---:|:---:|:---:|:---:|------|
| 20 | 195 | 170 | 0.981 | 0.122 | $V_n$ 不足 |
| 30 | 275 | 161 | 0.931 | 0.021 | 勉强可用 |
| **40** | **355** | **158** | **0.918** | **0.004** | **甜点** |
| 60 | 515 | 138 | 0.901 | 0.002 | 过度配置 |
| 80 | 675 | 124 | 0.880 | 0.003 | 秩亏恶化 |

---

## 4. 在线数据流（TPS 和 VSM 共享）

### 4.1 GPU Buffer 布局

```
Descriptor Set 0 (所有 binding 为 float32 StructuredBuffer):

 Binding  名称             维度         字节    访问
 ───────────────────────────────────────────────────
 17       boltHeights       [35]         140 B   R/W (Adam)
 18       boltHeightGradient [35]        140 B   R/W (累加)
 19       influencePhi      [35×625]     85 KB  RO
 20       influencePhiU     [35×625]     85 KB  RO
 21       influencePhiV     [35×625]     85 KB  RO
 22       gravityY          [625]        2.4 KB RO
 23       yuGrid            [625]        2.4 KB RW
 24       yvGrid            [625]        2.4 KB RW
 25       surfaceGradient   [625×3]      7.3 KB RW
 26-28    influenceKxx/zz/xz [35×625]    85 KB各 RO

总计: ~530 KB GPU 显存
```

### 4.2 每轮迭代 (50 iter, ~45s/iter)

```
Step 1: 表面构造 (GPU, 1次 dispatch)
  computeBoltSurface [25×25 threads]
    对每个网格点 p = (gridU, gridV):
      w   = gravityY[p]
      w_u = 0; w_v = 0
      for b in 0..34:
        idx = b*625 + gridV*25 + gridU
        w   += boltHeights[b] * influencePhi[idx]
        w_u += boltHeights[b] * influencePhiU[idx]
        w_v += boltHeights[b] * influencePhiV[idx]
      法线 = -normalize(cross((W,w_u,0), (0,w_v,L)))
    输出: yGrid[625], yuGrid[625], yvGrid[625], nGrid[2500]

Step 2: 光学渲染 (GPU, ×36 sun directions)
  for each sun direction:
    a. 前向: 光线追踪 → flux[7850] (157×50 pixels)
    b. S95: 二分搜索 95% 阈值
    c. Loss: L_S95 = Σ sigmoid(6·(flux[p]/level - 1))
    d. 反向: bwd_diff → surfaceGradient[1875] = {dL/dy_p, dL/dyu_p, dL/dyv_p}
    e. 投影: boltHeightGradient[b] += Σ_p (dL/dy_p·φ_b + dL/dyu_p·φ_u + dL/dyv_p·φ_v)

Step 3: 参数更新 (GPU, 1次 dispatch)
  boltAdamStep: Adam optimizer on boltHeights[35]
```

### 4.3 数据维度速查

| 数据 | 符号 | 维度 | 每个元素 |
|------|------|:---:|------|
| 螺栓高度 | $h_b$ | 35 | float32 |
| 影响函数 | $\varphi_b(p)$ | 35×625 | float32 |
| 表面高度 | $w(p)$ | 625 | float32 |
| 表面斜率 | $\partial w/\partial u, \partial w/\partial v$ | 625×2 | float32 |
| 表面法线 | $\mathbf{n}(p)$ | 625×4 | float32 |
| 光通量 | flux(pixel) | 7850 | float32 |
| 光学梯度 | $\partial L/\partial y_p$ | 625 | float32 |
| 螺栓梯度 | $\partial L/\partial h_b$ | 35 | float32 |

---

## 5. 重力处理

### 当前方案

$$w_{\text{total}}(\mathbf{r}) = w_{\text{grav}}(\mathbf{r}) + \sum_{b=1}^{35} \Delta Y_b \cdot \varphi_b(\mathbf{r})$$

重力场 $w_{\text{grav}}$ 通过有限差分 (FD) 在 200×150 细网格上求解双调和方程，面积平均到 25×25 渲染网格：

$$w_{\text{grav}} = \text{AreaAverage}_{25\times25}\left( \text{FD\_solve}(\nabla^4 w = q/D,\; w(\mathbf{r}_b)=0,\; \text{200×150}) \right)$$

**参数**：$q = \rho g h = 98.1$ N/m²，$D = 392$ N·m，PV≈23.6mm

### 未来方向

重力解可精确表示为特解 + VSM 影响函数的线性组合：

$$w_{\text{grav}}(\mathbf{r}) = w_p(\mathbf{r}) - \sum_{b=1}^{35} w_p(\mathbf{r}_b) \cdot \varphi_b^{\text{exact}}(\mathbf{r})$$

其中 $w_p(r) = \frac{q}{64D} r^4$。当前限制是 VSM 的 Tikhonov 正则化使自影响仅为 0.918，无法精确抵消特解（角点达 16m）。使用精确 φ_b（无正则化）可完全求解。

---

## 6. 后处理：刚性平移

由于 $\Sigma_{b} \varphi_b(\mathbf{r}) \approx 1.0$ 处处成立（PV≈0.001mm），等量偏移所有螺栓 = 刚性平移镜面：

$$w'(\mathbf{r}) = \sum_b (h_b + c) \varphi_b(\mathbf{r}) = w(\mathbf{r}) + c$$

后处理流程（使所有螺栓在物理约定中为正）：

```
h_opt (管线约定, 含负值)
  → h_pipe = h_opt - max(h_opt) - 0.5mm  (全部 ≤ -0.5mm)
  → h_phys = -h_pipe                       (全部 ≥ +0.5mm, 指向接收器)
  → S95 不变
```

---

## 7. 代码位置

| 步骤 | 文件 |
|------|------|
| TPS 生成 | `scripts/generate_influence_data.py` (TPS 部分) |
| VSM 生成 | `scripts/generate_influence_data.py` (VSM 部分) |
| VSM Tikhonov | `scripts/fix_mfs_tikhonov.py` |
| FEA 对比 | `scripts/compare_three_methods.py` |
| 表面构造 | `shaders/bolt_common.slang:54-79` |
| 前向渲染 | `shaders/forward.slang` |
| 光学反向 | `shaders/bolt_backward.slang:104-183` |
| 力学投影 | `shaders/bolt_backward.slang:208-223` |
| 优化循环 | `src/pipeline.cpp:1319-1405` |

---

*文档日期：2026-06-11*
