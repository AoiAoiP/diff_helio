# B-spline + FEM 代理模型：从控制点到定日镜表面

## 0. 历史回顾：我们为什么选择这条路径

### 0.1 问题起源

定日镜场中，每面镜子通过 $35$ 个可调螺栓（$7 \times 5$）支撑在钢桁架上。螺栓高度调节量 $\Delta y_b$ 决定了镜面在重力与安装应力下的最终形状。我们需要找到一组螺栓高度，使反射光斑在接收器上的 S95 面积最小。

这是一个**双层耦合问题**：

- **力学层**：螺栓位移 $\Delta y_b$ 通过一块 $4$mm 厚的玻璃板（自由边界，Kirchhoff 板方程 $D\nabla^4 w = 0$）决定镜面形状 $w(x,z)$
- **光学层**：镜面形状 $w(x,z)$ 通过太阳光线追踪（折射、反射、太阳形状卷积）决定接收器上的能流分布

### 0.2 第一阶段：Bezier CP 优化（2026-05）

最初的设计用 $4 \times 4 = 16$ 个 Bezier 控制点直接参数化镜面高度：

$$w(u, v) = \sum_{i=0}^{3} \sum_{j=0}^{3} B_i(u) B_j(v) \cdot \text{CP}_{ij}$$

其中 $B_i$ 为三次 Bernstein 基函数。

**结果**：S95 从初始 $\sim 232$ m² 降至 $\sim 42-66$ m²（仅依赖椭圆初始猜测），但 $16$ 个 CP 无法表达比椭圆更复杂的局部面型调整。这是参数化的表达能力上限（CLAUDEL 曰："Bezier 椭圆面型已近最优"）。

### 0.3 第二阶段：螺栓直接优化 + Gaussian RBF（2026-06-04）

引入螺栓参数化：用 $35$ 个独立螺栓高度替代 $16$ 个 Bezier CP。镜面 = 重力下垂 + 螺栓影响函数的线性叠加：

$$w(p) = w_{\text{grav}}(p) + \sum_{b=1}^{35} \Delta Y_b \cdot \phi_b(p)$$

影响函数 $\phi_b(p)$ 的物理意义：当螺栓 $b$ 位移 $1$mm、其他螺栓固定为 $0$ 时，点 $p$ 处的镜面位移。

第一版使用 Gaussian RBF 作为影响函数（无物理依据的工程代理）：

$$\phi_b(u,v) = \exp\!\left(-\frac{(u-u_b)^2 W^2 + (v-v_b)^2 L^2}{2\sigma^2}\right), \quad \sigma = 0.15 \times \text{对角线}$$

设计了两阶段梯度架构：
- **阶段 1（光学）**：$\partial \mathcal{L}/\partial y_p$ → 通过可微光线追踪反向传播
- **阶段 2（力学）**：$\partial \mathcal{L}/\partial h_b = \sum_p [\partial \mathcal{L}/\partial y_p \cdot \phi_b(p) + \cdots]$

**结果**：S95 从 $232$ 降至 $50-65$ m²（$150$ iter, $36$ 太阳方向），光学性能优异，但暴露出严重的物理问题：

| 问题 | 表现 | 根因 |
|------|------|------|
| 螺栓符号全负 | $0/35$ 正 | $\phi_b \geq 0$ 始终，凹面必须全部缩回螺栓 |
| 螺栓行程超大 | PV = $1288$mm | 宽核函数导致 $28\times$ 位移放大 |
| 条件数极差 | $\kappa = 6.4 \times 10^7$ | 相邻螺栓影响高度重叠（$67\%$） |
| 物理上不存在 | — | $\sum h_b \phi_b$ 不满足任何板方程 |

### 0.4 探索期：六种求解器的对比（2026-06-05 至 06-08）

意识到 Gaussian 的物理缺陷后，系统性地测试了多种板求解器来生成物理正确的影响函数：

| 求解器 | 物理原理 | 边界条件 | S95 | 失败原因 |
|--------|---------|---------|-----|---------|
| **TPS** | $\phi(r)=r^2\log(r^2)$，$\nabla^4 w=0$ 的基础解 | 无限大板（无边界） | $107$ m² | $12 \times 12$ 网格无法分辨尖锐核函数 |
| **FEM FD** | 直接离散 $\nabla^4 w=0$，$13$ 点双调和 stencil | 简支边（$w=0, M_n=0$） | $177$ m² | BC 定性错误（自由边 ≠ 简支边） |
| **FEM Navier** | 双正弦级数 Green 函数 | 简支矩形板 | N/A | 柔度矩阵条件数 $2.7 \times 10^7$，求逆失败 |
| **MFS** | TPS 源 + 边界配置点 | 自由边（$M_n=0$ 配置） | $140$ m² | $12 \times 12$ 网格下 BC 精度不足 |
| **WoS** | Monte Carlo 球面游走 | 自由边（天然支持） | 未完成 | 双调和耦合需 $O(N^2)$ 计算量，GPU 实现复杂 |
| **FreeFEM** | 有限元法（Morley 元） | 自由边（天然支持） | — | 依赖外部工具，与 GPU 管线集成复杂 |

**关键发现**（来自多 LLM 咨询共识）：

> 问题本质不是"选哪个核函数"，而是**连续 PDE 解与粗采样网格之间的尺度失配**。

Gaussian RBF 成功并非因为它物理正确，而仅仅因为其空间频率恰好匹配 $12 \times 12$ 渲染网格的分辨率。任何一个物理正确的核函数（TPS、MFS、FEM）在被粗网格"欠采样"后都会丢失关键特征。

### 0.5 突破：细网格 + 面积平均（2026-06-08）

解决方案来自一个类比——**图形学中的超采样抗锯齿（MSAA）**：

- 在细网格（$132 \times 96$）上高精度求解板方程
- 将细网格结果面积平均到渲染网格（$12 \times 12$）
- 平均后的 $\varphi_b^{\text{eff}}$ 就是正确的"有效算子"——它描述了在每个渲染格内镜面平均位移如何响应螺栓调节

$$\varphi_b^{\text{eff}}(P) = \frac{1}{|\text{cell}_P|} \iint_{\text{cell}_P} \varphi_b^{\text{fine}}(x, z) \, dx \, dz$$

这种面积平均在物理上是正确的：渲染器需要的是每个 $12 \times 12$ 格内的平均表面高度，而非某个采样点的精确值。

同时引入 B-spline 降维（$25$ CPs → $35$ bolts）：

- 三次 B-spline 基函数将 $35$ 个独立的螺栓高度约束为 $25$ 个 CP 的光滑函数
- 条件数从 $6.4 \times 10^7$ 降至 $60$
- B-spline 平滑在 CPU 侧完成，GPU 渲染管线零改动

**最终结果**：S95 $49-54$ m²，PV $33$mm，匹配或超越 Gaussian 基线，但拥有正确的物理基础。

### 0.6 关于物理正则 Loss 的再思考

在 Gaussian 时代，Type A（能量守恒）/ Type B（坡度）/ Type C（曲率）物理正则 loss 是**必需的**——没有它们，纯 S95 优化会收敛到物理上不可能的面型（改善仅 $12.6\%$，有 Type C 后达 $67\%$）。

但在 B-spline + MFS 框架下，物理约束的模式发生了根本变化：

| 约束类型 | Gaussian RBF | B-spline+MFS |
|----------|-------------|-------------|
| **构成性物理** | $\phi_b$ 是经验核，$\sum h_b\phi_b$ 可表达非物理解 | $\phi_b$ 是板方程解，$\sum h_b\phi_b$ 自动满足 $\nabla^4 w=0$ |
| **规制性物理** | Type A/B/C 通过 loss 项"注入"物理 | 构成性物理已保证面型合规，规制性物理冗余 |

**消融实验证实**：移除 Type C curvature loss 后，S95 仅从 $48.8$ 降至 $49.3$ m²（差异 $<1\%$，在渲染噪声范围内）。Type C 在 Gaussian 时代贡献 $54\%$ 的改善，在 B-spline+MFS 时代贡献 $<1\%$。

### 0.7 路径选择：为什么不用 FreeFEM 或 WoS

**FreeFEM**（有限元法，Morley 非协调 $C^1$ 元）：

- 优点：天然支持自由边 BC，数学上最严格
- 放弃原因：(1) 依赖外部 FEM 工具链，与现有 GPU 管线集成复杂；(2) 需要将 FEM 网格解导出为 GPU 纹理，数据转换链路长；(3) scikit-fem 原型尝试失败——Morley 元的双线性形式实现过于复杂

**WoS/PRB**（Walk on Spheres，球面游走法）：

- 优点：天然支持任意边界条件，可通过 PRB 技术实现可微分
- 搁置原因：Poisson 原型已验证（误差 $<2\%$），但双调和耦合需要 $2$ 层嵌套游走 → 计算量 $O(N^2)$；GPU kernel 实现（球面采样、距离查询、Green 函数评估）复杂度高；属于长期方向，非近期可交付

**MFS + 细网格**被选中是因为它提供了最优的**实现复杂度 / 物理正确性**比值：$30$ 秒离线计算 + 零 GPU 改动 + S95 匹配 Gaussian。

---

## 1. 问题设定

定日镜子镜面由 $N_b = 35$ 个螺栓（$7 \times 5$ 布局）支撑。每个螺栓的高度调节量 $\Delta y_b$ 通过一块自由边界 Kirchhoff 薄板影响整个镜面。我们的目标是用 $N_c = 25$ 个 B-spline 控制点（$5 \times 5$）参数化所有螺栓高度，构建一个高效、物理正确、可微分的代理模型。

## 2. 物理基础：Kirchhoff 板方程

镜面弯曲服从自由边 Kirchhoff 板方程：

$$D \nabla^4 w(x, z) = 0 \quad \text{在域内} \quad \Omega = [-W/2, W/2] \times [-L/2, L/2]$$

$$M_n = 0, \quad V_n = 0 \quad \text{在自由边界} \quad \partial\Omega$$

$$w(x_b, z_b) = \Delta y_b \quad \text{在螺栓点} \quad b = 1, \ldots, 35$$

其中 $D = \frac{E h^3}{12(1-\nu^2)}$ 为板弯曲刚度，$M_n$ 为边界法向弯矩，$V_n$ 为等效剪力。

## 3. 离线阶段：有效影响函数生成

### 3.1 MFS 基本解法

双调和方程 $\nabla^4 w = 0$ 的基本解为 TPS（Thin-Plate Spline）核：

$$\phi_{\text{TPS}}(r) = r^2 \log(r^2)$$

将解表示为 $N_s = 115$ 个源点处 TPS 核的线性组合（$35$ 个螺栓点 $+$ $80$ 个域外源点），外加 $3$ 个多项式项：

$$w(x, z) = \sum_{s=1}^{115} c_s \, \phi_{\text{TPS}}\!\left(\sqrt{(x - x_s)^2 + (z - z_s)^2}\right) + p_0 + p_1 x + p_2 z$$

未知数：$\mathbf{c} = [c_1, \ldots, c_{115}, p_0, p_1, p_2]^T \in \mathbb{R}^{118}$

### 3.2 约束系统

构建 $158 \times 118$ 的系统矩阵 $\mathbf{A}$：

**(a) 螺栓位移约束**（$35$ 个方程）：
$$A_{b,j} = \phi_{\text{TPS}}\!\left(\sqrt{(x_b - x_j)^2 + (z_b - z_j)^2}\right), \quad j = 1,\ldots,115$$
$$A_{b,116} = 1, \quad A_{b,117} = x_b, \quad A_{b,118} = z_b$$

**(b) 自由边界弯矩约束**（$120$ 个方程，每条边 $30$ 个配置点）：
$$M_n = \frac{\partial^2 w}{\partial n^2} + \nu \frac{\partial^2 w}{\partial t^2} = 0 \quad \text{在} \quad \partial\Omega$$

其中 $n$ 为边界法向，$t$ 为边界切向，$\nu = 0.22$ 为泊松比。

**(c) 正则化条件**（$3$ 个方程，消除多项式冗余）：
$$\sum_{s=1}^{115} c_s = 0, \quad \sum_{s=1}^{115} c_s x_s = 0, \quad \sum_{s=1}^{115} c_s z_s = 0$$

### 3.3 求解与评估

通过 SVD 截断伪逆求解 $\mathbf{A} \mathbf{C} = \mathbf{I}_{35}$（对 $35$ 个螺栓分别施加单位位移）：

$$\mathbf{C} = \mathbf{V} \mathbf{S}^{-1} \mathbf{U}^T \mathbf{I}_{35} \in \mathbb{R}^{118 \times 35}$$

在细网格 $\mathcal{G}_{\text{fine}}$（$132 \times 96$）上评估每个螺栓的影响函数：

$$\varphi_b^{\text{fine}}(x_p, z_p) = \sum_{s=1}^{115} C_{s,b} \, \phi_{\text{TPS}}(r_{sp}) + C_{116,b} + C_{117,b} \, x_p + C_{118,b} \, z_p$$

### 3.4 面积平均：从细网格到渲染网格

**核心创新**。渲染网格只有 $12 \times 12$（$144$ 个点），直接评估会丢失板弯曲的精细特征。面积平均产生"有效算子"：

$$\varphi_b^{\text{eff}}(P) = \frac{1}{|\text{cell}_P|} \iint_{\text{cell}_P} \varphi_b^{\text{fine}}(x, z) \, dx \, dz$$

离散实现：每个渲染格 $P$ 覆盖 $11 \times 8$ 个细网格单元，取均值：

$$\varphi_b^{\text{eff}}[i, j] = \frac{1}{88} \sum_{p \in \text{cell}_{ij}} \varphi_b^{\text{fine}}[p]$$

## 4. B-spline 维度降阶

### 4.1 三次 B-spline 基函数

在 $[0,1]$ 上定义 Clamped 三次 B-spline（$5$ 个控制点，$\text{degree}=3$）：

$$\text{knots} = [0, 0, 0, 0, 0.5, 1, 1, 1, 1]$$

基函数 $\{N_i(u)\}_{i=0}^{4}$ 满足 Cox-de Boor 递推和单位分解 $\sum_i N_i(u) = 1$。

### 4.2 CP → 螺栓映射矩阵

二维 B-spline 表面由 $5 \times 5 = 25$ 个控制点 $c_{ij}$ 定义：

$$h(u, v) = \sum_{i=0}^{4} \sum_{j=0}^{4} N_i(u) \, N_j(v) \, c_{ij}$$

在 $35$ 个螺栓位置 $(u_b, v_b)$ 处评估，得到映射矩阵 $\mathbf{T} \in \mathbb{R}^{35 \times 25}$：

$$\mathbf{T}_{b, \, i + 5j} = N_i(u_b) \, N_j(v_b)$$

螺栓高度向量：
$$\mathbf{h} = \mathbf{T} \mathbf{c}, \quad \mathbf{h} \in \mathbb{R}^{35}, \quad \mathbf{c} \in \mathbb{R}^{25}$$

条件数 $\kappa(\mathbf{T}) = 60$，远优于直接螺栓优化的 Hessian 条件数（$6.4 \times 10^7$）。

## 5. 在线阶段：GPU 表面构造

### 5.1 表面叠加

渲染网格上每个点 $p$（$k = \text{gridV} \times 12 + \text{gridU}$）：

$$y[k] = y_{\text{grav}}[k] + \sum_{b=0}^{34} h_b \cdot \varphi_b^{\text{eff}}[k]$$

$$\frac{\partial y}{\partial u}[k] = \sum_{b=0}^{34} h_b \cdot \frac{\partial \varphi_b^{\text{eff}}}{\partial u}[k]$$

$$\frac{\partial y}{\partial v}[k] = \sum_{b=0}^{34} h_b \cdot \frac{\partial \varphi_b^{\text{eff}}}{\partial v}[k]$$

### 5.2 法线计算

$$\mathbf{t}_u = \begin{bmatrix} W \\ \partial y/\partial u \\ 0 \end{bmatrix}, \quad \mathbf{t}_v = \begin{bmatrix} 0 \\ \partial y/\partial v \\ L \end{bmatrix}$$

$$\mathbf{n} = -\frac{\mathbf{t}_u \times \mathbf{t}_v}{\|\mathbf{t}_u \times \mathbf{t}_v\|}$$

其中 $W = 12.84\text{m}, L = 9.45\text{m}$。

### 5.3 重力下垂

$$y_{\text{grav}}(u, v) = -0.002 \times 4 \times \left[(u - 0.5)^2 + (v - 0.5)^2\right] \, [\text{m}]$$

## 6. 优化循环

### 6.1 前向传播

$$\mathbf{h} = \mathbf{T} \mathbf{c} \quad \text{(CPU, T 为 } 35 \times 25 \text{ 矩阵)}$$
$$\mathbf{y} = \mathbf{y}_{\text{grav}} + \boldsymbol{\Phi}^T \mathbf{h} \quad \text{(GPU, } \boldsymbol{\Phi} \in \mathbb{R}^{35 \times 144} \text{ 纹理查表)}$$
$$\text{flux} = \text{RayTrace}(\mathbf{y}, \mathbf{n}) \quad \text{(GPU, forward.slang)}$$
$$\mathcal{L}_{\text{S95}} = \sum_{p} \sigma\!\left(6 \cdot \left(\frac{\text{flux}_p}{\text{S95Level}} - 1\right)\right) \quad \text{(S95 sigmoid loss)}$$

### 6.2 反向传播

**光学梯度**（GPU, bolt_backward.slang）：
$$\frac{\partial \mathcal{L}}{\partial h_b} = \sum_{p} \left[ \frac{\partial \mathcal{L}}{\partial y_p} \cdot \varphi_b(p) + \frac{\partial \mathcal{L}}{\partial y u_p} \cdot \frac{\partial \varphi_b}{\partial u}(p) + \frac{\partial \mathcal{L}}{\partial y v_p} \cdot \frac{\partial \varphi_b}{\partial v}(p) \right]$$

**CP 梯度投影**（CPU）：
$$\frac{\partial \mathcal{L}}{\partial \mathbf{c}} = \mathbf{T}^T \frac{\partial \mathcal{L}}{\partial \mathbf{h}}$$

展开：$\frac{\partial \mathcal{L}}{\partial c_{ij}} = \sum_{b=0}^{34} T_{b, i+5j} \cdot \frac{\partial \mathcal{L}}{\partial h_b}$

### 6.3 Adam 更新

在 CPU 上对 $25$ 个 CP 变量执行标准 Adam：

$$m_{ij}^{(t+1)} = \beta_1 m_{ij}^{(t)} + (1 - \beta_1) \frac{\partial \mathcal{L}}{\partial c_{ij}}$$
$$v_{ij}^{(t+1)} = \beta_2 v_{ij}^{(t)} + (1 - \beta_2) \left(\frac{\partial \mathcal{L}}{\partial c_{ij}}\right)^2$$
$$c_{ij}^{(t+1)} = c_{ij}^{(t)} - \eta \cdot \frac{m_{ij}^{(t+1)} / (1 - \beta_1^{t+1})}{\sqrt{v_{ij}^{(t+1)} / (1 - \beta_2^{t+1})} + \varepsilon}$$

## 7. 完整链路总结

```
离线 (一次, ~30s):
  MFS 求解器 → C[118×35] → φ_b^{fine}(132×96) → 面积平均 → φ_b^{eff}(12×12)
  B-spline 基函数 → T[35×25], κ(T)=60

在线 (每轮, ~0.5s):
  c(25) ──T@c──→ h(35) ──Σh_b φ_b──→ y(144) ──光线追踪──→ flux(7850)
    ↑                │                                        │
    │                │                                        │
    └──T^T @ dL/dh── dL/dh_b ←──φ_b 投影──── dL/dy_p ←── S95Loss
       (CPU)            (GPU bolt_backward)        (GPU render_backward)
```

### 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| $W \times L$ | $12.84 \times 9.45$ m | 镜面尺寸 |
| $N_b$ | $35$ | 螺栓数 ($7 \times 5$) |
| $N_c$ | $25$ | CP 数 ($5 \times 5$) |
| $\kappa(\mathbf{T})$ | $60$ | B-spline 条件数 |
| $\nu$ | $0.22$ | 玻璃泊松比 |
| $\eta$ | $5 \times 10^{-4}$ | 学习率 |
| $\beta_1, \beta_2$ | $0.9, 0.999$ | Adam 参数 |

### 代码位置

| 组件 | 文件:行 |
|------|--------|
| MFS 求解器 | `scripts/compute_bspline_fem.py:FreeEdgeMFSSolver` |
| 面积平均 | `scripts/compute_bspline_fem.py:area_average()` |
| B-spline 基函数 | `scripts/compute_bspline_fem.py:build_bspline_basis_1d()` |
| CP→螺栓映射 | `src/pipeline.cpp:cpToBoltHeights()` |
| 表面叠加 | `shaders/bolt_common.slang:54-79` (boltSurfaceAtGrid) |
| 法线计算 | `shaders/bolt_common.slang:75-78` |
| 光学反向传播 | `shaders/bolt_backward.slang` (全文件) |
| 梯度投影 | `src/pipeline.cpp:boltGradToCpGrad()` |
| CP Adam | `src/pipeline.cpp:cpAdamStep()` |
