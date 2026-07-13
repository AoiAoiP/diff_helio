# 理想面型到螺栓高度的反求：数学原理与算法流程

## 1. 问题陈述

**给定**：一块 $W \times L$ 的矩形玻璃镜面，由 $N_b = 35$ 个螺栓支撑。螺栓影响函数 $\varphi_b(\mathbf{r})$ 已知（由 MFS 求解器离线计算）。目标镜面形状 $\mathbf{w}_{\text{target}} \in \mathbb{R}^{M}$ 已知（$M$ 为离散网格点数）。

**求**：螺栓高度 $\mathbf{h} = [\Delta Y_1, \ldots, \Delta Y_{35}]^T$，使构造的镜面尽可能接近目标面型。

## 2. 数学原理

### 2.1 前向模型

镜面在点 $\mathbf{r}_p$ 处的位移是重力下垂与螺栓贡献的线性叠加：

$$w(\mathbf{r}_p) = w_{\text{grav}}(\mathbf{r}_p) + \sum_{b=1}^{35} \Delta Y_b \cdot \varphi_b(\mathbf{r}_p)$$

写成矩阵形式：

$$\mathbf{w} = \mathbf{w}_{\text{grav}} + \boldsymbol{\Phi}^T \mathbf{h}$$

其中：
- $\mathbf{w} \in \mathbb{R}^{M}$：渲染网格上 $M$ 个点的镜面位移
- $\mathbf{w}_{\text{grav}} \in \mathbb{R}^{M}$：重力下垂（预计算，固定值）
- $\boldsymbol{\Phi} \in \mathbb{R}^{35 \times M}$：影响函数矩阵，第 $b$ 行是 $\varphi_b$ 在 $M$ 个点上取值
- $\mathbf{h} \in \mathbb{R}^{35}$：螺栓高度向量

### 2.2 反问题

给定目标面型 $\mathbf{w}_{\text{target}}$，反求螺栓高度使前向模型输出尽可能接近目标：

$$\mathbf{h}^* = \arg\min_{\mathbf{h} \in \mathbb{R}^{35}} \left\| \boldsymbol{\Phi}^T \mathbf{h} - (\mathbf{w}_{\text{target}} - \mathbf{w}_{\text{grav}}) \right\|_2^2$$

这是一个**超定线性最小二乘问题**（$M = 625 \gg 35 = N_b$）。

### 2.3 正规方程解

令 $\mathbf{t} = \mathbf{w}_{\text{target}} - \mathbf{w}_{\text{grav}}$（目标螺栓贡献），$\mathbf{A} = \boldsymbol{\Phi}^T \in \mathbb{R}^{M \times 35}$。

$$\mathbf{h}^* = (\mathbf{A}^T \mathbf{A})^{-1} \mathbf{A}^T \mathbf{t} = (\boldsymbol{\Phi}\boldsymbol{\Phi}^T)^{-1} \boldsymbol{\Phi} \mathbf{t}$$

其中 $\boldsymbol{\Phi}\boldsymbol{\Phi}^T \in \mathbb{R}^{35 \times 35}$ 是螺栓之间的**交叉影响 Gram 矩阵**：

$$(\boldsymbol{\Phi}\boldsymbol{\Phi}^T)_{ij} = \sum_{p=1}^{M} \varphi_i(\mathbf{r}_p) \cdot \varphi_j(\mathbf{r}_p)$$

这个矩阵的条件数决定了反问题的适定性。对角线元素 $\sum_p \varphi_b^2(\mathbf{r}_p)$ 是螺栓 $b$ 的"自影响平方和"——值越大，该螺栓对表面的控制力越强。

### 2.4 物理意义

$\mathbf{A}^T \mathbf{A}$ 的第 $i$ 行第 $j$ 列是影响函数 $\varphi_i$ 和 $\varphi_j$ 在网格上的内积：

$$\langle \varphi_i, \varphi_j \rangle = \int_\Omega \varphi_i(\mathbf{r}) \varphi_j(\mathbf{r}) \, d\mathbf{r}$$

这度量了螺栓 $i$ 和 $j$ 对表面形状控制的"冗余度"。内积大 → 两个螺栓的影响高度重叠 → 它们的调节效果可以互相替代 → Gram 矩阵条件数变差 → 反问题更不稳定。

MFS+BC 25×25 的 Gram 矩阵条件数约为 $10^3$——远优于 Gaussian RBF 的 $6.4 \times 10^7$。

## 3. 算法流程

### 3.1 离线阶段（一次计算）

```
输入: 目标面型 w_target[M], 影响函数 phi[N_b × M], 重力 w_grav[M]
输出: 螺栓高度 h[N_b]

步骤:
  1. 计算目标螺栓贡献: t = w_target - w_grav
  2. 构建矩阵 A = phi.T         [M × N_b]
  3. 求解正规方程: h = (A^T A)^{-1} A^T t
     或直接调用 lstsq(A, t)
  4. 输出 h
```

**实现（Python）**：
```python
import numpy as np

# 加载影响函数 phi[35, 25, 25] 和重力 grav[25, 25]
phi = np.fromfile('data_bs_fem25/influence_phi.bin', dtype=np.float32)
phi = phi.reshape(35, 25, 25)
grav = np.fromfile('data_bs_fem25/gravity_y.bin', dtype=np.float32)
grav = grav.reshape(25, 25)

# 计算椭圆目标面型
u = np.linspace(0, 1, 25); v = np.linspace(0, 1, 25)
U, V = np.meshgrid(u, v)
X = (U - 0.5) * 12.84; Z = (V - 0.5) * 9.45
w_target = A_ellip * X**2 + B_ellip * Z**2  # 椭圆面型

# 反求螺栓高度
Phi = phi.reshape(35, -1)        # [35 × 625]
target = (w_target - grav).ravel()  # [625]
h = np.linalg.lstsq(Phi.T, target, rcond=None)[0]  # [35]

print(f'螺栓高度: [{h.min()*1e3:.0f}, {h.max()*1e3:.0f}] mm')
print(f'拟合RMS: {np.sqrt(np.mean((Phi.T @ h - target)**2))*1e3:.1f} mm')
```

### 3.2 在线阶段（GPU 渲染管线）

反求得到的 $\mathbf{h}$ 直接上传到 GPU，触发表面构造：

```
h[35] ──CPU upload──→ boltHeights GPU buffer
          ↓
   boltForwardSurface()  ← shaders/bolt_forward.slang
          ↓
   w(p) = w_grav(p) + Σ h_b · φ_b(p)   ← 144或625个网格点
          ↓
   forwardRender()  ← 光线追踪
          ↓
   readFlux() → computeS95Level() → 输出 S95
```

## 4. 以椭圆面型为例

### 4.1 椭圆面型定义

定日镜的理想面型是一个离轴椭球面，在局部坐标系中近似为：

$$w_{\text{ellip}}(x, z) = A x^2 + B z^2 + C xz$$

其中 $A, B, C$ 由定日镜相对于接收器的位置确定（见 `data/ellipse.txt`）。

对 North 300m 定日镜：$A = 6.91 \times 10^{-4}$, $B = 7.71 \times 10^{-4}$, $C \approx 0$。

### 4.2 反求结果

| 量 | 值 |
|----|-----|
| 螺栓高度范围 | $[0.1, 36.1]$ mm |
| PV | $36$ mm |
| 正值螺栓 | $35/35$ |
| 拟合 RMS 残留 | $0.5$ mm |
| 构造面型 bowl | $+43$ mm（凹面） |
| 36 方向 S95 | $47.9$ m² |
| Bezier 理想 S95 | $\sim 43$ m² |

### 4.3 残留分析

拟合 RMS 0.5mm 的来源：
- 35 个螺栓的自由度限制（Bezier 用 16 个 CP，螺栓用 35 个更灵活的点约束）
- 影响函数的有限支撑（每个 $\varphi_b$ 在远处趋于零，边缘区域拟合能力弱）
- 面积平均伪影（细网格→渲染网格的降采样损失）

## 5. 反求 vs 迭代优化

| 维度 | 最小二乘反求 | 迭代 S95 优化 |
|------|------------|-------------|
| 输入 | 目标面型（面型空间） | S95 loss（光学空间） |
| 计算量 | 单次 $O(N_b^2 M)$ ≈ 毫秒 | $N_{\text{iter}} \times N_{\text{sun}}$ 次光线追踪 ≈ 小时 |
| 输出质量 | 精确逼近目标面型 | Sigmoid loss 引导的面型 |
| 何时用 | 已知理想面型 | 目标面型未知，或需多目标权衡 |

**关键洞察**：当目标面型已知时，反求直接给出螺栓高度——不需要迭代优化。仅在目标面型不确定（例如需要直接在 S95 空间搜索，或从零初始猜测自主收敛）时，迭代优化才提供额外价值。

## 6. 代码位置

| 步骤 | 位置 |
|------|------|
| 椭圆参数定义 | `data/ellipse.txt` |
| 影响函数加载 | `data_bs_fem25/influence_phi.bin` |
| 最小二乘反求 | `compute_bspline_fem.py` init generation 段 |
| 螺栓高度加载 | `src/pipeline.cpp:1023-1038` |
| 表面构造 | `shaders/bolt_forward.slang` (`computeBoltSurface`) |
| GPU 前向渲染 | `shaders/forward.slang` (`renderForward`) |
