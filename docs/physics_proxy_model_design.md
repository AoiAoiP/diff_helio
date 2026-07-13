# 定日镜物理代理模型：从 Kirchhoff 板方程到 MFS 数值方法

## 1. 问题陈述

### 1.1 工程背景

塔式光热电站中，每面定日镜（$12.84 \times 9.45 \times 0.004$ m 玻璃板）由钢桁架上 $7 \times 5 = 35$ 个可调螺栓支撑。螺栓高度调节量 $\Delta y_b$ 决定镜面在重力与安装应力下的最终形状 $w(x,z)$。优化目标：最小化接收器上 S95 光斑面积（包含 95% 能量的面积）。

### 1.2 双层耦合问题

- **力学层**：螺栓位移 $\Delta y_b$ 通过 Kirchhoff 板方程决定镜面形状 $w(x,z)$
- **光学层**：$w(x,z)$ 通过光线追踪（Snell 折射 + Buie 太阳模型）决定接收器能流分布

### 1.3 代理模型的线性叠加假设

所有代理模型共享相同的前向结构（小挠度线弹性叠加）：

$$w(\mathbf{r}) = w_{\text{grav}}(\mathbf{r}) + \sum_{b=1}^{35} \Delta Y_b \cdot \varphi_b(\mathbf{r})$$

其中 $\varphi_b(\mathbf{r})$ 是螺栓 $b$ 的**影响函数**——当螺栓 $b$ 位移 1mm、其他螺栓固定为 0 时，点 $\mathbf{r}$ 处的镜面位移。差异仅在于 $\varphi_b$ 的生成方式。

---

## 2. 物理基础：Kirchhoff 板方程

### 2.1 控制方程

薄板小挠度弯曲由 Kirchhoff 板方程描述（四阶椭圆型 PDE）：

$$\boxed{D \nabla^4 w(x, z) = q(x, z) \quad \text{在域内} \quad \Omega = \left[-\frac{W}{2}, \frac{W}{2}\right] \times \left[-\frac{L}{2}, \frac{L}{2}\right]}$$

其中 $D = \dfrac{E h^3}{12(1-\nu^2)}$ 为板弯曲刚度（$E=70$ GPa, $h=4$ mm, $\nu=0.22$ → $D \approx 392$ N·m）。

### 2.2 自由边界条件

镜面四条边无任何支撑——这是**自由边**（free edge）条件。自由边需同时满足两个条件：

**法向弯矩为零**（$M_n = 0$）：

$$M_n = -D\left(\frac{\partial^2 w}{\partial n^2} + \nu\frac{\partial^2 w}{\partial t^2}\right) = 0 \quad \text{在} \quad \partial\Omega$$

**等效剪力为零**（$V_n = 0$，Kirchhoff 边界条件）：

$$V_n = -D\left[\frac{\partial^3 w}{\partial n^3} + (2-\nu)\frac{\partial^3 w}{\partial n \partial t^2}\right] = 0 \quad \text{在} \quad \partial\Omega$$

其中 $n$ 为边界外法向，$t$ 为边界切向。**仅 $M_n=0$ 不足以唯一确定板解——缺少 $V_n=0$ 会导致边缘出现虚假鞍形翘曲**。

### 2.3 螺栓约束

在 35 个螺栓位置 $\mathbf{r}_b$ 处，挠度被约束为指定值：

$$w(\mathbf{r}_b) = \Delta Y_b \quad b = 1, \ldots, 35$$

### 2.3A 为什么线性叠加代理模型能描述板方程

代理模型的核心假设——镜面 = 重力下垂 + 螺栓影响的线性叠加：

$$w(\mathbf{r}) = w_{\text{grav}}(\mathbf{r}) + \sum_{b=1}^{35} \Delta Y_b \cdot \varphi_b(\mathbf{r})$$

**这一假设成立的根本原因是 Kirchhoff 板方程在小挠度下的线性性。**

**证明**：

Kirchhoff 板方程是**线性偏微分方程**（双调和算子 $\nabla^4$ 是线性算子）：

$$D\nabla^4(c_1 w_1 + c_2 w_2) = c_1 D\nabla^4 w_1 + c_2 D\nabla^4 w_2$$

自由边边界条件同样是线性的（$M_n$ 和 $V_n$ 算子也是线性的）。

因此板弯曲问题是**线性边值问题**。根据线性 PDE 的叠加原理，总解可分解为：

$$w_{\text{total}} = w_{\text{homogeneous}} + w_{\text{particular}}$$

1. **特解 $w_{\text{grav}}$**：满足非齐次载荷 $D\nabla^4 w_{\text{grav}} = q$（重力），螺栓处齐次约束 $w_{\text{grav}}(\mathbf{r}_b) = 0$

2. **齐次解**：满足 $D\nabla^4 w = 0$（无载荷），螺栓处 $w(\mathbf{r}_b) = \Delta Y_b$

对于齐次解，由于 PDE 和 BC 都是线性的，**螺栓约束也可以线性分解**。定义**影响函数**（Green 函数）$\varphi_b(\mathbf{r})$ 为以下子问题的解：

$$D\nabla^4 \varphi_b = 0 \quad \text{在} \quad \Omega, \quad M_n=V_n=0 \quad \text{在} \quad \partial\Omega, \quad \varphi_b(\mathbf{r}_i) = \delta_{ib}$$

其中 $\delta_{ib}$ 是 Kronecker delta（仅螺栓 $b$ 处为 1，其余为 0）。

由叠加原理，任意螺栓位移组合的解为：

$$\boxed{w(\mathbf{r}) = w_{\text{grav}}(\mathbf{r}) + \sum_{b=1}^{35} \Delta Y_b \cdot \varphi_b(\mathbf{r})}$$

**关键前提**：所有操作在线弹性小挠度范围内（$\nabla w \ll 1$, $w \ll h$）。当挠度超过厚度（$w > 4$mm）时，膜应力（几何非线性）开始贡献——这也是 MFS 与 FEA（NLGEOM ON）之间存在 ~2mm RMS 偏差的根本原因之一。

### 2.4 物理参数

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 镜面宽度 | $W$ | 12.84 | m |
| 镜面长度 | $L$ | 9.45 | m |
| 玻璃厚度 | $h$ | 0.004 | m |
| 杨氏模量 | $E$ | $7 \times 10^{10}$ | Pa |
| 泊松比 | $\nu$ | 0.22 | — |
| 板弯曲刚度 | $D$ | $\sim 392$ | N·m |
| 螺栓数量 (7×5) | $N_b$ | 35 | — |
| 螺栓归一化边距 | — | 0.08 | — |

---

## 3. 从 PDE 到数值方法：MFS 的数学推导

### 3.1 从板方程到基本解：TPS 核的推导

#### 3.1.1 双调和方程与极坐标

考虑无载荷的齐次 Kirchhoff 板方程（$q=0$）：

$$D\nabla^4 w(x, z) = 0$$

在极坐标 $(r, \theta)$ 下，双调和算子 $\nabla^4$ 展开为：

$$\nabla^4 = \left(\frac{\partial^2}{\partial r^2} + \frac{1}{r}\frac{\partial}{\partial r} + \frac{1}{r^2}\frac{\partial^2}{\partial \theta^2}\right)^2$$

#### 3.1.2 径向对称基本解的求解

寻找径向对称解 $w(r)$，满足 $\nabla^4 w = 0$（除原点外）。极坐标下简化：

$$\nabla^4 w(r) = \left(\frac{d^2}{dr^2} + \frac{1}{r}\frac{d}{dr}\right)^2 w = 0$$

这是一个常微分方程。设 $u(r) = \nabla^2 w = w'' + \frac{1}{r}w'$，则 $\nabla^4 w = \nabla^2 u = u'' + \frac{1}{r}u' = 0$。

**第一步**：解 $\nabla^2 u = 0$（这是 Laplace 方程在极坐标下的径向形式）：

$$u'' + \frac{1}{r}u' = 0 \quad \Rightarrow \quad \frac{d}{dr}(r u') = 0 \quad \Rightarrow \quad r u' = C_1 \quad \Rightarrow \quad u(r) = C_1 \ln r + C_2$$

**第二步**：解 $\nabla^2 w = u = C_1 \ln r + C_2$：

$$w'' + \frac{1}{r}w' = C_1 \ln r + C_2$$

乘以 $r$：$r w'' + w' = C_1 r \ln r + C_2 r$，即 $\frac{d}{dr}(r w') = C_1 r \ln r + C_2 r$。

积分得：$r w' = C_1\left(\frac{r^2}{2}\ln r - \frac{r^2}{4}\right) + C_2 \frac{r^2}{2} + C_3$

再积分：

$$w(r) = \frac{C_1}{4} r^2(\ln r - 1) + \frac{C_2}{4} r^2 + C_3 \ln r + C_4$$

#### 3.1.3 提取基本解（Green 函数）

四个线性无关的基本解族：

| 解族 | 形式 | 物理含义 | 在 MFS 中的角色 |
|------|------|---------|--------------|
| $r^2 \ln r$ | **TPS 核** | 单位点载荷在无限大板上的挠度 | **核心基函数** |
| $r^2$ | 常数曲率 | 纯弯曲模式 | 被多项式项 $p_0+p_1x+p_2z$ 吸收 |
| $\ln r$ | 调和函数 | 无旋场分量 | 不满足远场衰减，不独立使用 |
| $1$ | 刚体位移 | 零应变模式 | 被多项式项吸收 |

其中 $r^2 \ln r$ 是**唯一在原点和无穷远均行为良好的解**（$\lim_{r\to 0} r^2\ln r = 0$，远场曲率衰减 $\sim 1/r^2$）。它满足：

$$\nabla^4 (r^2 \ln r) = 8\pi \delta(\mathbf{r})$$

即在原点处产生单位集中载荷——这正是 Green 函数的定义。

**最终形式**（添加多项式项保证唯一性）：

$$\phi_{\text{TPS}}(r) = r^2 \log(r^2)$$

> **缩放因子说明**：$\nabla^4(r^2 \ln r) = 8\pi \delta$ 中的 $8\pi$ 被 MFS 的系数 $c_j$ 吸收，无需在基函数中显式处理。TPS 核的形式 $r^2 \log(r^2)$（使用 $\log(r^2)$ 而非 $\ln r$）在数值上等价于 $2r^2 \ln r$，系数差异同样被 $c_j$ 吸收。

### 3.2 已废止：Gaussian RBF 经验代理

> **历史注记**：Gaussian RBF 是早期方案，因物理定性错误已被废止。此处简述其思路和失败原因，作为 TPS/MFS 物理模型的对照。

**基本思路**：用 Gaussian 径向基函数替代物理影响函数：

$$\varphi_b(\mathbf{r}) = \exp\!\left(-\frac{\|\mathbf{r} - \mathbf{r}_b\|^2}{2\sigma^2}\right), \quad \sigma = 2.4\text{m}$$

**失败原因**：

1. **不满足任何 PDE**：$\nabla^4(\exp(-r^2/2\sigma^2)) \neq 0$——Gaussian 核不是板方程的解，构造的面型物理上不可制造
2. **全域非负**：$\varphi_b \geq 0$ 意味着凹面型必须全部使用负螺栓高度（向下拉）——这与物理直觉（顶起螺栓产生凹面）完全相反
3. **条件数爆炸**：相邻螺栓重叠 67%，影响矩阵条件数 $\kappa = 6.4 \times 10^7$，导致螺栓高度被放大 28 倍（面型 PV=50mm → 螺栓行程=1288mm）
4. **无 Poisson 效应**：Gaussian 核没有负值叶瓣，无法表达板弯曲时"一处顶起、周围翘起"的 Poisson 效应

Gaussian RBF 唯一成功之处在于其空间频率（$\sigma=2.4$m）恰好匹配粗渲染网格的奈奎斯特频率。这是巧合，不是物理。

### 3.3 Method of Fundamental Solutions (MFS)

MFS 的核心思想：将 PDE 的解表示为基本解的线性组合，源点放置在域外以避免奇异性。

对于 $N_s$ 个 TPS 源点 $\mathbf{r}_j^{\text{src}}$，解的形式为：

$$w(\mathbf{r}) = \sum_{j=1}^{N_s} c_j \cdot \phi_{\text{TPS}}(\|\mathbf{r} - \mathbf{r}_j^{\text{src}}\|) + p_0 + p_1 x + p_2 z$$

其中：
- $c_j$：TPS 源强系数（$N_s$ 个未知数）
- $p_0 + p_1 x + p_2 z$：线性多项式项，保证解的唯一性（吸收 TPS 核的零空间）
- 总未知数：$N_s + 3$

### 3.4 源点布局

源点分为两类：

1. **螺栓源点**（$N_b = 35$ 个）：直接放置在螺栓位置，驱动螺栓处的指定位移
2. **域外源点**（$N_{\text{extra}}$ 个）：放置在矩形域外部（距离边界 $\delta = 1.5\sim2.0$ m），为边界条件提供额外的自由度

$$N_s = N_b + 4 \times N_{\text{extra}}$$

### 3.5 约束方程

**（1）螺栓位移约束**（$N_b$ 个方程）：

$$w(\mathbf{r}_i) = \sum_{j=1}^{N_s} c_j \cdot \phi_{\text{TPS}}(\|\mathbf{r}_i - \mathbf{r}_j^{\text{src}}\|) + p_0 + p_1 x_i + p_2 z_i = \delta_{ib}$$

（对影响函数 $\varphi_b$，只有螺栓 $b$ 处 $w=1$，其他螺栓处 $w=0$）

**（2）边界弯矩约束 $M_n = 0$**（$N_{\text{bc}}$ 个方程，在边界配置点上施加）：

$$M_n(\mathbf{r}_k^{\text{bc}}) = \sum_{j=1}^{N_s} c_j \cdot \mathcal{M}_n[\phi_{\text{TPS}}](\mathbf{r}_k^{\text{bc}} - \mathbf{r}_j^{\text{src}}) = 0$$

其中 $\mathcal{M}_n$ 是弯矩算子：$\mathcal{M}_n[\phi] = -D\left(\frac{\partial^2 \phi}{\partial n^2} + \nu\frac{\partial^2 \phi}{\partial t^2}\right)$，作用于 TPS 核的二阶导数：

$$\frac{\partial^2\phi}{\partial x^2} = 2\log(r^2) + \frac{4x^2}{r^2} + 2, \quad \frac{\partial^2\phi}{\partial z^2} = 2\log(r^2) + \frac{4z^2}{r^2} + 2, \quad \frac{\partial^2\phi}{\partial x\partial z} = \frac{4xz}{r^2}$$

**（3）边界等效剪力约束 $V_n = 0$**（$N_{\text{bc}}$ 个方程）：

$$V_n(\mathbf{r}_k^{\text{bc}}) = \sum_{j=1}^{N_s} c_j \cdot \mathcal{V}_n[\phi_{\text{TPS}}](\mathbf{r}_k^{\text{bc}} - \mathbf{r}_j^{\text{src}}) = 0$$

其中 $\mathcal{V}_n$ 涉及 TPS 核的三阶导数（Kirchhoff 等效剪力算子）：

$$\mathcal{V}_n[\phi] = -\left[\frac{\partial^3 \phi}{\partial n^3} + (2-\nu)\frac{\partial^3 \phi}{\partial n \partial t^2}\right]$$

三阶导数有解析表达（通过 TPS 核求导可得）。

**（4）正则化条件**（3 个方程）：

$$\sum_{j=1}^{N_s} c_j = 0, \quad \sum_{j=1}^{N_s} c_j x_j^{\text{src}} = 0, \quad \sum_{j=1}^{N_s} c_j z_j^{\text{src}} = 0$$

这三个条件消除 TPS 源强系数的线性相关性，保证解的唯一性。

### 3.6 线性方程组

将所有约束组装为线性系统：

$$\mathbf{A} \mathbf{x} = \mathbf{b}$$

其中：
- $\mathbf{x} = [c_1, \ldots, c_{N_s}, p_0, p_1, p_2]^T$（$N_s + 3$ 个未知数）
- $\mathbf{b} = [\delta_{1b}, \ldots, \delta_{N_b b}, 0, \ldots, 0]^T$（对螺栓 $b$ 的影响函数求解）
- $\mathbf{A}$ 的行结构：

| 行范围 | 内容 | 数量 |
|--------|------|------|
| $0 \ldots N_b-1$ | 螺栓位移约束（TPS + 多项式） | $N_b$ |
| $N_b \ldots N_b+N_{\text{bc}}-1$ | $M_n=0$ 约束（弯矩算子） | $N_{\text{bc}}$ |
| $N_b+N_{\text{bc}} \ldots N_b+2N_{\text{bc}}-1$ | $V_n=0$ 约束（剪力算子） | $N_{\text{bc}}$ |
| 最后 3 行 | 正则化 ($\Sigma c_j=0$, $\Sigma c_j x_j=0$, $\Sigma c_j z_j=0$) | 3 |

总方程数 $N_{\text{eqn}} = N_b + 2N_{\text{bc}} + 3$

### 3.7 SVD 求解与 Tikhonov 正则化

对每个螺栓 $b$，求解 $\mathbf{A}\mathbf{x} = \mathbf{e}_b$（$\mathbf{e}_b$ 在第 $b$ 个位置为 1，其余为 0）。

**SVD 分解**：$\mathbf{A} = \mathbf{U} \boldsymbol{\Sigma} \mathbf{V}^T$

**Tikhonov 正则化伪逆**：

$$\mathbf{A}^+_{\lambda} = \mathbf{V} \cdot \text{diag}\!\left(\frac{\sigma_i}{\sigma_i^2 + \lambda^2}\right) \cdot \mathbf{U}^T$$

**为什么需要 Tikhonov 而非 SVD 硬截断？**

原始的 SVD 硬截断（`rcond=1e-8`）将 $\sigma_i < \text{rcond} \cdot \sigma_{\max}$ 的奇异值直接置零。在 MFS (M_n+V_n) 系统中，这砍掉了 200/358 个奇异值。螺栓约束方程（35 行）的矩阵系数量级远小于 $V_n$ 约束（160 行，三阶导数），在 SVD 中被系统性地牺牲。结果是：边界条件近乎完美（$V_n\approx 0.004$），但螺栓约束的自影响暴跌至 0.13——优化无法使用。

Tikhonov 正则化 $s_i/(s_i^2+\lambda^2)$ 对所有奇异值施加**连续衰减**（而非硬截断），通过调节 $\lambda$ 在螺栓约束满足和边界条件满足之间寻找平衡。**2026-06-11 实验**确定 $\lambda = 10^{-5}$ 为最优值。

### 3.8 三种模型的约束配置

| 模型 | 方程数 | 未知数 | $M_n=0$ | $V_n=0$ | 正则化 | 边界物理 |
|------|--------|--------|---------|---------|--------|---------|
| **TPS**（无限大板） | $N_b+3$ | $N_b+3$ | ✗ | ✗ | ✓ | 无边界 |
| **MFS (M_n only)** | 198 | 138 | ✓ (160点) | ✗ | ✓ | 一半（缺 $V_n$） |
| **MFS (M_n+V_n)** | 358 | 358 | ✓ (160点) | ✓ (160点) | ✓ | **全 Kirchhoff** |

---

## 4. 代理模型验证指标

在评估物理代理模型时，仅靠 RMS vs FEA 不够。需要一组**力学诊断指标**来识别错误的具体来源。

### 4.1 自影响（Self-Influence）

$$\text{SI}_b = \varphi_b(\mathbf{r}_b)$$

**物理含义**：当螺栓 $b$ 位移 1mm、其他螺栓固定为 0 时，螺栓 $b$ 自身处的板挠度。

**理想值**：$\text{SI}_b \approx 1.0$（精确满足螺栓约束）。

**两个测量位置**：

| 测量方式 | 含义 | 用途 |
|---------|------|------|
| **网格自影响** | 在最接近螺栓位置的渲染网格点上评估 $\varphi_b$ | 反映优化器在网格上"看到"的梯度 |
| **精确自影响** | 在螺栓的精确物理位置上评估 $\varphi_b$ | 反映螺栓约束的数学满足程度 |

网格自影响 < 1.0 不一定是缺陷——如果网格点不完全对齐螺栓位置，测量值自然偏低。**真正重要的是精确自影响**，因为优化器的梯度计算使用精确的 $\varphi_b(\mathbf{r}_b)$。

**与优化的关系**：$\frac{\partial w}{\partial (\Delta Y_b)}(\mathbf{r}_b) = \varphi_b(\mathbf{r}_b) = \text{SI}_b$。自影响 < 1 意味着梯度衰减——优化器需要更大的步长来产生相同的面型变化。

### 4.2 Maxwell-Betti 互易性

$$\varphi_i(\mathbf{r}_j) = \varphi_j(\mathbf{r}_i) \quad \forall i,j$$

线弹性系统的柔度矩阵必须对称——这是能量守恒（Maxwell-Betti 互等定理）的推论。所有基于对称核（TPS）的方法自动满足（RMS 不对称度 $<10^{-6}$）。

### 4.3 边界条件残差

在 200 个非配置采样点上评估 $M_n$ 和 $V_n$：

$$\max|M_n|_{\partial\Omega}, \quad \max|V_n|_{\partial\Omega}$$

| 方法 | $\max\|M_n\|$ | $\max\|V_n\|$ | BC 完备性 |
|------|--------------|--------------|--------------|
| TPS（无限板） | 0.126 | N/A | 无边界条件 |
| MFS ($M_n$ only) | 0.0001 | **1.724** | 仅 $M_n=0$ |
| MFS ($M_n+V_n$) Tikhonov | 0.0073 | **0.117** | 全 Kirchhoff |

$V_n$ 残差从 1.724 降至 0.117（降低 93%），但仍高于 SVD 硬截断版的 0.004。这是 Tikhonov 正则化在自影响和边界条件之间的折中。

### 4.4 RMS vs FEA（纯螺栓物理）

在去除重力后（两边都仅含螺栓贡献 $w = \sum \Delta Y_b \cdot \varphi_b$），逐点对比 MFS 预测面型与 FEA 参考面型：

$$\text{RMS} = \sqrt{\frac{1}{N_{\text{pts}}}\sum_{p} \left(w_{\text{MFS}}(\mathbf{r}_p) - w_{\text{FEA}}(\mathbf{r}_p)\right)^2}$$

$$R^2 = 1 - \frac{\sum_p (w_{\text{MFS}} - w_{\text{FEA}})^2}{\sum_p (w_{\text{FEA}} - \bar{w}_{\text{FEA}})^2}$$

这是最全面的验证指标——量化代理模型与高保真 FEA 参考之间的系统性偏差。

---

## 5. 三种方法对比实验（25×25，2026-06-11）

### 5.1 实验设置

| 参数 | 值 |
|------|-----|
| 网格分辨率 | 25×25 |
| 螺栓高度 | 来自 `example_bolts.txt`（PV=36mm, 35/35 正值） |
| 重力 | 双侧去除（FEA 通过插值减重力，MFS 仅计算 $\sum h_b\varphi_b$） |
| FEA 参考 | Ansys SHELL181, NLGEOM ON, 35 个 UY 指定位移 |
| MFS (M_n+V_n) | Tikhonov $\lambda = 10^{-5}$ |
| 去均值 | 所有场在对比前减均值（消除刚体位移） |

### 5.2 总体结果

| 方法 | RMS (mm) | $R^2$ | PV (mm) | 网格自影响 | 精确自影响 | BC |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| FEA（参考） | — | 1.000 | 37.7 | — | — | NLGEOM |
| **TPS**（无限大板） | **1.67** | **0.972** | 37.3 | 0.13 | ~1.00 | 无 |
| MFS ($M_n$ only) | 13.29 | −0.76 | 52.7 | 0.97 | ~1.00 | $M_n=0$ |
| MFS ($M_n+V_n$) Tik | 2.03 | 0.959 | 46.9 | 0.13 | **0.918** | $M_n=V_n=0$ |

### 5.3 惊人发现：TPS 最优！

**TPS（无限大板基本解，无任何边界条件）以 RMS=1.67mm、$R^2=0.972$ 位列第一**，优于添加了全 Kirchhoff BC 的 MFS($M_n+V_n$)（RMS=2.03mm）。

**原因分析**：

1. **FEA 的 NLGEOM 效应**：Ansys FEA 开启了大挠度（NLGEOM ON），引入了膜应力 stiffening。膜的拉伸刚度在边缘附近产生额外约束，使板的实际行为**介于自由边和无限板之间**。TPS 的无限大板假设碰巧比纯自由边 Kirchhoff 更接近 NLGEOM 解。

2. **MFS 的边界条件可能过强**：在 25×25 的粗网格上，TPS 源点的边界配置不够密集，施加 $M_n=V_n=0$ 时产生的边缘效应（鞍形翘曲、边缘下陷）比 NLGEOM FEA 的实际边缘行为更剧烈。

3. **MFS 的基函数截断**：用有限个 TPS 源点逼近自由边 Green 函数存在固有误差，而纯 TPS 方法精确满足 $\nabla^4 w=0$（无截断）。

**这并不意味着应该放弃边界条件**。随着网格加密（25×25 → 32×32 → 132×96+面积平均），MFS 的边界物理优势会逐渐显现。TPS 在粗网格上的优势可能来自"误差抵消"——无 BC 的误差方向恰好与 NLGEOM 效应方向一致。

### 5.4 逐行 RMS

| Z 位置 | TPS | MFS($M_n$) | MFS($M_n+V_n$) |
|--------|:---:|:---:|:---:|
| 边缘 ($\pm 4725$mm) | 2.8 | 17.5 | 3.39 mm |
| 1/4 ($\pm 2362$mm) | 1.2 | 13.0 | **0.70** mm |
| 中心 (0mm) | 1.9 | 12.5 | 2.84 mm |

**MFS($M_n+V_n$) 在板内部（Z=±2362mm）的 RMS 仅 0.70mm**——这是三个方法中最好的内部精度。边缘误差（3.39mm）是其主要瓶颈。

### 5.5 中心截面形状

```
        EdgeL    Q1   Center    Q3   EdgeR
FEA      -3.2  11.0   -17.2   11.0   -3.2
TPS      -2.3   8.0   -17.0    8.0   -2.3    ← 边缘最好
MFS_Mn   -4.1 -12.0   -16.4  -12.0   -4.1    ← Q1/Q3 定性错误
MFS_MnVn -9.4   7.8   -17.0    7.8   -9.4    ← 中心最好，边缘最差
```

- **中心挠度**：三种方法都接近 −17.0mm（FEA: −17.2mm）
- **Q1/Q3**：MFS($M_n$) 的 −12.0mm 完全错误（FEA: +11.0mm）——板弯曲方向反了。MFS($M_n+V_n$) 的 +7.8mm 方向正确，量值偏低。
- **边缘**：TPS 的 −2.3mm 最接近 FEA 的 −3.2mm。MFS($M_n+V_n$) 的 −9.4mm 边缘下陷过深。

---

## 6. 关键 Bug 修复历史

### 6.1 Bug 1：SVD 硬截断 → Tikhonov 正则化

- **症状**：MFS($M_n+V_n$) 自影响 = 0.13，优化无法使用
- **根因**：SVD `rcond=1e-8` 硬截断砍掉 200/358 个奇异值。螺栓约束（35 行，系数量级 $\sim 10^2$）被 $V_n$ 约束（160 行，三阶导数量级 $\sim 10^6$）系统性淹没
- **修复**：Tikhonov 正则化 $s_i/(s_i^2+\lambda^2)$ 替代硬截断，$\lambda=10^{-5}$ 为最优值
- **效果**：精确自影响从 0.13 恢复至 0.918（梯度保留 92%），RMS 维持 2.03mm

### 6.2 Bug 2：pt_idx 列优先混乱

- **症状**：网格自影响测量值不稳定，phi_grid 和直接计算不一致
- **根因**：`pt_idx = gi*gs + gj`（列优先）与 `w.reshape(gs,gs)`（行优先/C-order）不匹配。对角螺栓（gi=gj）碰巧一致，非对角螺栓读错网格点
- **修复**：统一使用行优先 `pt_idx = gj*gs + gi`
- **影响**：不影响物理模型本身（MFS 求解使用精确位置），仅影响网格上的诊断测量

### 6.3 经验教训

1. **在精确位置测量自影响**：网格点不完全对齐螺栓位置时，网格自影响天然偏低，不代表梯度真的衰减
2. **SVD 截断不适合多尺度系统**：当约束方程的量级跨越数个数量级时（螺栓 vs 三阶导数），硬截断会系统性牺牲小量级方程。Tikhonov 是更好的选择
3. **验证指标要区分"物理错误"和"测量伪影"**

---

## 7. 分辨率分析

### 7.1 25×25 vs 32×32

| 指标 | 25×25 | 32×32 |
|------|:---:|:---:|
| MFS($M_n+V_n$) RMS | 2.03 mm | 2.06 mm |
| MFS($M_n+V_n$) $R^2$ | 0.959 | 0.958 |
| MFS($M_n$) RMS | 13.29 mm | 13.21 mm |

**分辨率从 25×25 提高到 32×32 几乎不影响 RMS**。这说明当前的物理误差（~2mm）不是网格分辨率不足，而是 MFS 基函数截断和 Tikhonov 折中的固有限制。

### 7.2 何时需要更高分辨率

- **TPS 核的尖峰采样**：TPS 核 $\phi(r)=r^2\log(r^2)$ 在 $r \to 0$ 处有奇异性（二阶导数发散）。粗网格无法分辨螺栓附近的应力集中
- **边界层**：自由边的边界效应发生在 $\sim 0.5$m 范围内，需更密网格来解析
- **细网格 + 面积平均**是更好的策略：在细网格（132×96）上求解，面积平均到渲染网格（25×25），同时保留物理精度和计算效率

---

## 8. 当前状态与推荐路线

### 8.1 推荐方案

| 优先级 | 方案 | 优势 | 适用场景 |
|--------|------|------|---------|
| **首选** | TPS（无限大板） | RMS=1.67mm, 无 BC 伪影 | 快速原型、与 NLGEOM FEA 接近 |
| 高精度 | MFS($M_n+V_n$) Tikhonov | 全 Kirchhoff BC, 内部 RMS<1mm | 需要严格自由边物理时 |
| 遗留 | MFS($M_n$ only) | 自影响 0.97, 但 RMS=13.3mm | **不推荐**——物理定性错误 |

### 8.2 物理正确性 vs NLGEOM 效应

MFS($M_n+V_n$) 施加的纯 Kirchhoff 自由边 BC（线性小挠度）**系统性偏离** Ansys NLGEOM（大挠度 + 膜应力 stiffening）。TPS（无 BC）在粗网格上意外地更接近 NLGEOM 解——这是误差抵消，不是物理优越。

**随着网格加密和 FEA 精度提高，MFS 的边界物理优势将逐步显现。** 但在当前 25×25 到 32×32 的分辨率范围内，TPS 是更好的工程选择。

### 8.3 后续方向

| 方向 | 收益 | 难度 | 方法 |
|------|------|------|------|
| 细网格 MFS (132×96) + 面积平均 | 消除粗网格采样误差 | 中 | 参照 `compute_bspline_fem.py` |
| MFS 源点自适应密度 | 改善边缘 BC 精度 | 中 | 边界附近加密源点 |
| TPS+MFS 混合 | 继承 TPS 优势 + 边缘 BC 修正 | 低 | 先用 TPS，再在边界附近叠加 MFS 修正 |
| WoS Grid-Free | 全套 BC 无基函数截断 | 高 | 双调和 WoS GPU 实现 |
| 线性 vs NLGEOM 定量 | 量化非线性贡献 | 低 | FEA 线性 vs 非线性对比 |

### 8.4 NN 底线

不到万不得已（所有解析方法穷尽后仍无法达到目标精度），不使用神经网络。理由：外推安全性、物理可解释性、数据匮乏（35 个螺栓无法生成足够训练数据）、零样本泛化（镜面尺寸或螺栓布局改变时需重新训练）。

---

## 附录 A：代码位置

| 组件 | 文件 |
|------|------|
| TPS 求解器 | `scripts/compare_three_methods.py` |
| MFS ($M_n$ only) | `scripts/compute_bspline_fem.py:FreeEdgeMFSSolver` |
| MFS ($M_n+V_n$) | `scripts/compare_three_methods.py` |
| Tikhonov 正则化 | `scripts/fix_mfs_tikhonov.py` |
| 三项对比实验 | `scripts/compare_three_methods.py` |
| 可视化 | `scripts/plot_final_comparison.py`, `scripts/terminal_viz.py` |
| 对比图 | `docs/three_method_comparison.png` |
| 数据 | `docs/three_method_results.npz` |

## 附录 B：相关文档

- `docs/fea_gravity_extraction_plan.md` — FEA 纯重力提取方案
- `docs/wos_physics_proxy_design.md` — Grid-Free WoS 设计
- `docs/bolt_inversion_from_ideal_surface.md` — 理想面型反求螺栓
- `CLAUDE.md` — 项目总览

---

*文档版本：2026-06-11 | 整合了 `mechanics_proxy_dilemma_analysis.md` 的内容并删除原文件*
