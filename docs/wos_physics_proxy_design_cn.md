# Grid-Free WoS 物理代理模型：设计与实现

## 1. 动机

当前 MFS+BC 在 36 方向训练中达到 S95=47.7 m²。Bezier 基线为 42.6 m²。约 5 m² 的差距来自：

- 缺少 $V_n=0$（等效剪力）自由边条件
- 25×25 面积平均的精度损失
- 缺失角点效应（Kirchhoff 角点条件）

Walk on Spheres（WoS）天然处理**全套自由边 BC**（$M_n=0$，$V_n=0$），分辨率仅受纹理尺寸限制——无网格、无基函数截断、无边界配置点。

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    离线阶段（一次，~30 分钟 GPU）              │
│                                                             │
│  35 螺栓 → WoS 双调和求解器 → φᵢ(256×192) → 面积平均 → φᵢ(25×25) │
│                                                             │
│  输出：7 个 .bin 文件（与当前 GPU 管线完全兼容）                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    在线阶段（每轮，<1s）                       │
│                                                             │
│  ΔY(35) → w = w_grav + Σ ΔYᵢ·φᵢ → 渲染 → ∂L/∂ΔY            │
│                                                             │
│  GPU 管线零改动。梯度投影完全不变。                             │
└─────────────────────────────────────────────────────────────┘
```

## 3. 物理基础

### 3.1 控制方程

$$D\nabla^4 w = 0 \quad \text{在域内} \quad \Omega = \left[-\frac{W}{2},\frac{W}{2}\right] \times \left[-\frac{L}{2},\frac{L}{2}\right]$$

$$M_n = 0, \quad V_n = 0 \quad \text{在自由边界} \quad \partial\Omega$$

$$w(\mathbf{r}_b) = \delta_{ib} \quad \text{在螺栓点} \quad b = 1,\ldots,35$$

### 3.2 双 Poisson 分解（Almansi 分解）

双调和方程 $\nabla^4 w = 0$ 可分解为两个**耦合的 Poisson 方程**：

$$\boxed{\begin{cases} \Delta M = 0, & M_n = 0 \quad \text{在自由边界} \\ \Delta w = -M/D, & w = \delta_{ib} \quad \text{在螺栓}, \quad V_n = 0 \quad \text{在自由边界} \end{cases}}$$

其中 $M = M_{xx} + M_{zz} = -D(1+\nu)\nabla^2 w$ 是弯矩迹（moment trace）。

这是 WoS 可处理双调和问题的关键——**将四阶 PDE 分解为两个可分别用 WoS 求解的二阶 Poisson 方程**。

### 3.3 WoS 求解 Poisson 方程

对于 Poisson 方程 $\Delta u = -f$ 在 $\Omega$ 中，Dirichlet BC $u = g$ 在 $\partial\Omega$ 上：

解在点 $\mathbf{x}$ 处的值等于沿 Brownian 路径的期望：

$$u(\mathbf{x}) = \mathbb{E}\left[ g(\mathbf{x}_\tau) + \int_0^\tau f(\mathbf{x}_t) \, dt \right]$$

**Walk on Spheres 算法：**

```
u = 0
pos = x
while 未到达边界:
    r = 到边界的距离(pos)           // 最大内切球半径
    pos = 球面上的随机均匀点(pos, r)   // 采样 ∂B(pos, r)
    u += f(pos) * r² / (2 * dim)     // dim=2: Green 函数贡献 = f * r²/4
u += g(边界点)                         // 边界贡献
返回 u  (对 N 次游走取平均以确保精度)
```

### 3.4 矩形板的距离查询（解析式）

对于矩形板 $\Omega = [-W/2, W/2] \times [-L/2, L/2]$，任意点 $\mathbf{x} = (x, z)$ 到边界的距离是**解析的**：

$$d(\mathbf{x}) = \min\left(\frac{W}{2} - |x|,\; \frac{L}{2} - |z|\right)$$

这是一个极关键的属性：无需网格、无需 BVH、无需最近点查询——**仅需 4 次浮点比较**。这是 WoS 在矩形域上极高效的根本原因。

### 3.5 球面均匀采样

在 2D 中，圆上的均匀采样极为简单：

$$\theta \sim \mathcal{U}(0, 2\pi), \quad x_{\text{new}} = x + r\cos\theta, \quad z_{\text{new}} = z + r\sin\theta$$

### 3.6 自由边 Kirchhoff BC 的 WoS 处理

**Layer 1（弯矩场）**：$\Delta M = 0$，$M_n = 0$ 在边界上。

$M_n=0$ 是**齐次 Neumann BC**。对于 Poisson 方程的 Neumann BC，WoS 需要反射处理：游走到边界时，以边界法向为轴做镜面反射，继续在域内游走（而非终止）。

**Layer 2（挠度场）**：$\Delta w = -M/D$，$w = \delta_{ib}$ 在螺栓处，$V_n = 0$ 在自由边上。

$V_n=0$ 是 Kirchhoff 等效剪力为零的条件。在双 Poisson 分解框架下，这转化为 $w$ 的 Robin 型边界条件。WoS 通过修正边界 Green 函数来处理。

## 4. 实现设计

### 4.1 双调和 WoS 算法

```
函数 wos_influence(评估点 x_eval, 螺栓编号 bolt_idx):
    w = 0
    对每次游走 walk = 1 到 N_walks:
        // 层 1：在 x_eval 处求解 M
        M_val = wos_layer1_moment(x_eval, bolt_idx)
        
        // 层 2：用 M_val 作为源项求解 Δw = -M/D
        w += wos_layer2_deflection(x_eval, M_val, bolt_idx)
    
    返回 w / N_walks


函数 wos_layer1_moment(x, bolt_idx):
    // ΔM = 0，在自由边上 M_n = 0
    // 螺栓点产生 Delta 函数矩源
    pos = x; M = 0
    当 未到达边界(pos):
        r = 到边界的距离(pos)
        pos = 球面采样(pos, r)
    边界处理:
        M += boundary_M_contribution(pos, bolt_idx)  // Neumann 反射
    返回 M


函数 wos_layer2_deflection(x, M_field, bolt_idx):
    // Δw = -M/D，螺栓处 w = δ_{i,b}
    pos = x; w = 0
    当 未到达边界(pos):
        r = 到边界的距离(pos)
        w += M_field(pos) * r² / 4     // dim=2 的 Green 函数
        pos = 球面采样(pos, r)
    边界处理:
        w += boundary_w_contribution(pos)  // Robin 条件
    螺栓处理:
        如果 pos 接近螺栓 bolt_idx:
            w += 1.0  // Delta 函数
    返回 w
```

### 4.2 复杂度估计

对于 $256 \times 192$ 纹理 × 35 螺栓：

| 步骤 | 计算量 |
|------|--------|
| 纹理像素/螺栓 | $256 \times 192 = 49,152$ |
| 总像素 | $49,152 \times 35 = 1.72$M |
| 每次游走的步数 | $\sim 100$（步进距离 $\sim 0.1$m，板尺寸 $\sim 12$m） |
| 每像素游走次数 | $\sim 10,000$（$<1\%$ 统计误差） |
| 每步操作 | $\sim 10$（距离查询、球面采样、场评估） |
| **总操作数** | $\approx 1.7\times10^6 \times 10^4 \times 100 \times 10 \approx 1.7\times10^{13}$ |
| **GPU 耗时估算** | $\sim 10$ GFLOPS → $\sim 1,700$s ≈ **30 分钟** |

### 4.3 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 纹理分辨率 | $256 \times 192$ | 维持 $12.84:9.45$ 纵横比，面积平均到 $25\times25$ |
| 每像素游走数 | 从 $100$ 开始测试 | 监控统计误差收敛 |
| 边界停止距离 | $\varepsilon = 0.01$m | 远小于螺栓间距 $1.8$m |
| 螺栓模型 | 点约束（Dirac delta） | 与 MFS 一致，简化对比验证 |

### 4.4 验证策略

**阶段 1 — Poisson WoS 验证**（先确定 WoS 基本正确）：
- 求解 $\Delta u = 0$ 在矩形上，$u = g$ 在边界上
- 与解析解对比（分离变量法）
- 验证收敛阶 $O(1/\sqrt{N_{\text{walks}}})$

**阶段 2 — 双调和 WoS 验证**：
- 求解 $D\nabla^4 w = 0$，自由边，点载荷
- 与 MFS 解对比（应有类似的响应模式，但边缘更准确）
- 检查 $V_n \approx 0$ 在边界上

**阶段 3 — 全纹理生成**：
- 生成所有 35 个 $\varphi_b$ 纹理
- 验证自影响 $\phi_i(\mathbf{r}_i) \approx 1.0$
- 与 MFS $\varphi_b$ 逐像素对比
- 导出 .bin 文件

## 5. GPU 实现草图（Slang Compute Shader）

```hlsl
// wos_influence.slang — 每像素每螺栓一个线程
[numthreads(16, 16, 1)]
void computeWoSInfluence(uint3 tid : SV_DispatchThreadID) {
    uint boltIdx = tid.z;      // 0..34
    uint px = tid.x, py = tid.y;
    
    float2 evalPos = textureToWorld(px, py);
    
    float w = 0.0;
    uint seed = hash(px, py, boltIdx);
    
    for (uint walk = 0; walk < N_WALKS; walk++) {
        // 层 1 + 层 2 联合游走
        w += walkBiharmonic(evalPos, boltIdx, seed);
        seed = nextRandom(seed);
    }
    w /= float(N_WALKS);
    
    influencePhi[boltIdx * TEX_W * TEX_H + py * TEX_W + px] = w;
}
```

## 6. MFS 与 WoS 对比

| 维度 | MFS+BC（当前） | WoS（拟议） |
|------|---------------|-----------|
| BC 完备性 | 仅 $M_n=0$（缺 $V_n=0$） | 全 Kirchhoff（$M_n=0 + V_n=0$） |
| 精度极限 | 受基函数数量限制（138 个未知数） | 受游走次数限制（统计精度） |
| 离线耗时 | $\sim 30$s（Python SVD） | $\sim 30$min（GPU Monte Carlo） |
| 网格依赖 | 面积平均伪影 | 统计噪声（平滑） |
| 可扩展性 | 仅矩形 | **任意形状** |
| 角点效应 | 缺失 | **自然捕获** |
| 在线阶段 | $w = \sum h_b \phi_b$（不变） | $w = \sum h_b \phi_b$（不变） |

## 7. 实施计划

### Phase 1：Poisson WoS 验证（~2 天）
- Python 原型：在矩形上实现 WoS 求解 $\Delta u = 0$
- 与分离变量解析解对比验证
- 收敛测试：$N_{\text{walks}}$ 与误差的关系
- Slang GPU kernel 原型

### Phase 2：双调和 WoS（~3 天）
- 实现双 Poisson 分解 WoS
- 生成单个 $\varphi_i$ 验证
- 与 MFS 解在同一评估网格上对比
- 边缘 $V_n \approx 0$ 数值验证

### Phase 3：全纹理生成与管线集成（~1 天）
- 生成全部 $35$ 个 $\varphi_i$ 在 $256\times192$ 上
- 面积平均到 $25\times25$ 渲染网格
- 导出 .bin 文件
- 运行优化，对比 S95

## 8. 预期成果

用正确的 $V_n=0$ BC 且无基函数近似：
- 自影响 $\phi_i(\mathbf{r}_i)$ 应更接近 $1.0$（预期 $>0.95$）
- 边缘鞍形效应（$\pm 9$mm）应大幅减少
- S95 应向 Bezier 基线 $42.6$ m² 逼近
- 螺栓符号模式应更具物理直观性

## 参考文献

- Yilmazer et al. (2024): "Differentiable Walk on Spheres"
- Sawhney & Crane (2020): "Monte Carlo Geometry Processing"
- Muller (1956): "Some continuous Monte Carlo methods for the Dirichlet problem"
- Sabelfeld (1991): "Monte Carlo Methods for Boundary Value Problems"
