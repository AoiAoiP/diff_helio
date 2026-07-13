# 定日镜面物理可实现性 — 实验设计方案

## 目标

证明使用可微优化方法（differentiable optimization）获得的定日镜螺栓高度配置，在物理上是可实现的——即优化结果可以通过真实螺栓执行器实现，且代理模型预测的镜面形状和光学性能与物理实际一致。

## 当前状态

| 组件 | 状态 | 可信度 |
|------|:---:|:---:|
| VSM 螺栓影响函数（Tikhonov λ=10⁻⁵） | ✅ 已验证 | 螺栓独立 RMS=0.04mm |
| FEA-Direct 重力模型（角度插值） | ✅ 已验证 | 已知 bin RMS=0.049mm |
| 代理模型总精度 | ✅ 已验证 | 平均 RMS=0.14mm |
| 光学可微渲染管线 | ✅ 可用 | S95 110→56 m² |
| **GPU 重力插值集成** | ❌ 未完成 | 仍使用旧单 bin |
| **优化结果 FEA 验证** | ❌ 未做 | 最关键的缺失环节 |
| 力学基础验证 (A2/A3/A4) | ⬜ 待执行 | 叠加/互易/单位分解 |
| 梯度正确性 (C1/D1) | ⬜ 待执行 | 导数 + 螺栓梯度 FD |

## 实验体系总览

```
Phase 0: 力学代理基础验证 (A2, A3, A4, B1, C1)     ← 确认代理模型的数学基础
Phase 1: GPU 管线完善 + 梯度验证 (D1)                ← 完成软件基础设施
Phase 2: 端到端优化 + FEA 黄金标准验证 (E1, E2)      ← 🔑 核心实验
Phase 3: 物理可实现性约束 (F1, F2, F3)               ← 制造约束
Phase 4: 全工况鲁棒性 (G1, G2)                       ← 运行可靠性
```

---

## Phase 0: 力学代理基础验证

**目标**: 确认 VSM Tikhonov 代理模型的数学基础没有隐藏缺陷。

这些实验大多只需要 Python（不需要 FEA），可以立即执行。

### A2: 叠加原理线性性验证 [FEA required]

**问题**: 多个螺栓同时作用是否等于单螺栓作用的线性叠加？

**方法**:
1. 选择 3 组螺栓组合：{bolt 0, bolt 17}（角+心），{bolt 0, bolt 1, bolt 2}（边），{随机 5 螺栓}
2. 分别运行各单螺栓 FEA + 组合 FEA
3. 比较：$\text{FEA}(h_1, h_2) \stackrel{?}{=} \text{FEA}(h_1, 0) + \text{FEA}(0, h_2)$

**判定标准**: 残差 RMS < 0.01mm（远小于代理模型误差 0.14mm）

**文件**: `test_experiment/A2_superposition/` — APDL 模板和脚本已就绪

---

### A3: Maxwell-Betti 互易性 [纯 Python]

**问题**: $\phi_a(r_b) \stackrel{?}{=} \phi_b(r_a)$？即 A 点单位位移在 B 点产生的影响是否等于 B 点在 A 点的影响？

**方法**:
```python
# 对 VSM 影响矩阵做互易性检查
Phi = load_influence_matrix()  # [35, 625]
for a, b in itertools.combinations(range(35), 2):
    err = abs(Phi[a, grid_idx(b)] - Phi[b, grid_idx(a)])
```

**判定标准**: 最大互易性误差 < 1e-6（理论上应精确满足——Kirchhoff 板是自伴算子）

**文件**: `test_experiment/A3_reciprocity/check_reciprocity.py`

---

### A4: 刚体模态 / 单位分解 [纯 Python]

**问题**: $\sum_b \phi_b(x,z) \stackrel{?}{\approx} 1.0$？即所有螺栓同时顶升 1mm 是否等价于刚体平移？

**方法**:
```python
unity = sum(phi_b for all b)  # 每个 grid 点
pv = unity.max() - unity.min()
```

**判定标准**: PV < 0.01mm（CLAUDE.md 已记录 PV≈0.001mm）

**文件**: `test_experiment/A4_partition_of_unity/check_pou.py`

---

### B1: 重力单独响应对比 [纯 Python + 已有 FEA 数据]

**问题**: FEA-Direct 重力代理模型在**新角度**上的插值精度是否足够？

**方法**:
1. 已有数据：0°/30°/45°/60°/75° 的 FEA 零螺栓解
2. 生成 15°/22.5°/37.5°/52.5°/67.5° 的代理模型预测（线性插值）
3. 与已有的 8 角度验证数据对比（training_plan.md §9.4 已覆盖 12°/35°/52°）

**判定标准**: 所有插值点 RMS < 0.5mm（training_plan 已显示 0.28mm 平均）

**新增内容**: 建议增加 15° FEA 验证点（当前插值测试仅 3 个角度），确保插值在低角度区域也准确。

**文件**: `test_experiment/B1_gravity_only/` + `scripts/train_residual/validate_interpolation.py`

---

### C1: φ_u, φ_v 导数验证 [纯 Python]

**问题**: VSM 影响函数的**一阶导数**（φ_u, φ_v）是否与有限差分一致？这直接影响梯度计算中 `dL/dyu` 和 `dL/dyv` 的正确性。

**方法**:
```python
# 对每个螺栓的 phi，在 25×25 网格上比较解析导数 vs 中心差分
for b in range(35):
    phi_u_analytic = influencePhiU[b]
    phi_u_fd = (phi[b, :, 2:] - phi[b, :, :-2]) / (2 * dx)
```

**判定标准**: 相对误差 < 1%（在网格分辨率限制下）

**文件**: `test_experiment/C1_phi_derivatives/check_derivatives.py`

---

## Phase 1: GPU 管线完善 + 梯度验证

### GPU-G: 多角度重力插值 GPU 集成 [C++ GPU]

**问题**: 当前 GPU 管线仍使用旧版单 `gravity_y.bin`。training_plan §9.7 已详细设计了改动方案但未实现。

**改动清单**（按 training_plan §9.7）:

| 组件 | 改动 | 代码位置 |
|------|------|---------|
| `pipeline.cpp` | 加载 5 个 gravity bin → 5 个 GPU buffer (bindings 31-35) | `createBoltBuffers()` |
| `pipeline.cpp` | 根据当前太阳方向计算 θ → lo/hi/t → push constants | `updateUniforms()` |
| `bolt_common.slang` | 5 个 buffer 声明 + `sampleGravityUY(idx, lo, hi, t)` 函数 | 新增 ~30 行 |
| `bolt_forward.slang` | `sampleGravityUY()` 替代 `gravityBase[idx] * gravityScale` | 1 行改动 |
| `bolt_backward.slang` | **无需改动**（重力不参与梯度） | — |
| `config.h` / `config.cpp` | 新增 `gravityAngleFile` 路径配置 | JSON 解析 |

**验证方法**:
1. 加载已知角度（0°/30°/45°/60°/75°），GPU 输出应与对应 bin 完全一致（diff=0）
2. 加载插值角度（如 15°），GPU 输出应与 Python 验证脚本一致
3. 固定 0° 角度运行完整 forward pass，确认 flux 输出与旧代码一致

**判定标准**: 已知角度像素级一致（max diff < 1e-6），插值角度与 Python 参考一致

---

### D1: 螺栓梯度有限差分验证 [C++ GPU]

**问题**: 自动微分（AD）计算的螺栓梯度 $\partial L/\partial h_b$ 是否与有限差分（FD）一致？这是整个可微优化管线最关键的可靠性保证。

**方法**:
1. 加载已有的 `--check-grad` 模式（`pipeline.cpp:verifyBoltGradients()`）
2. 选取 2 个代表性太阳方向（低角度 15° + 高角度 60°）
3. 对全部 35 个螺栓做中心差分：$(L(h+\epsilon) - L(h-\epsilon)) / 2\epsilon$
4. 计算：符号一致率、余弦相似度、量级比率、每个螺栓的相对误差

**当前 `verifyBoltGradients()` 已存在**，但需要：
- 集成新的重力插值模型
- 扩展到多个太阳方向
- 增加不同螺栓配置下的测试（zero init, elliptic init, random init）

**判定标准**:
| 指标 | 阈值 | 说明 |
|------|:---:|------|
| 符号一致率 | > 90% | 梯度方向正确 |
| 余弦相似度 | > 0.95 | 梯度向量方向精确 |
| 量级比率 | 0.5–2.0 | 步长合适 |
| 中位相对误差 | < 20% | 个别螺栓可容忍较大相对误差 |

**已知问题**: `differentiable_rendering_discontinuity_analysis.md` 指出 2 层玻璃光学的 TIR 分支导致约 1/16 梯度符号错误。D1 需要量化此问题在 35 螺栓参数化下的严重程度。

**文件**: `test_experiment/D1_gradient_fd/run_gradient_check.sh`

---

## Phase 2: 端到端优化 + FEA 黄金标准验证 🔑

这是**整个项目最关键的实验**——证明可微优化管线输出的螺栓配置在物理上确实产生预期的镜面形状和光学性能。

### E1: 优化结果的 FEA 确认 [C++ optimization + FEA]

**问题**: 优化器找到的螺栓高度配置，在真实物理（FEA）中产生的镜面变形是否与代理模型预测一致？

**实验设计**:

```
Step 1: 运行优化（使用完整代理模型）
  - 配置: bolt_vsm_mnvn_50iter.json + 新重力插值
  - 定日镜: 选 2 个代表性位置（如 East_300m + North_300m）
  - 太阳方向: 36 方向训练集
  - 初始化: zero init + elliptic init 各跑一次
  - 输出: h_opt[35]（优化后的螺栓高度）

Step 2: 代理模型预测
  - 对每个训练太阳方向，用代理模型计算:
    w_proxy(x,z,θ) = UY_grav^FEA(x,z,θ) + cos(θ) * Σ h_b * φ_b^VSM(x,z)
  - 计算代理模型 S95_proxy

Step 3: FEA 黄金标准求解
  - 将 h_opt 作为螺栓位移载荷输入 Ansys
  - 对 3-5 个代表性太阳方向（0°, 30°, 45°, 60°）分别求解
  - 导出 node_dump → 插值到 25×25 网格

Step 4: 对比
  - 形状对比: w_proxy vs w_fea → RMS, PV, R²
  - 光学对比（如可行）: 将 w_fea 作为镜面形状重新渲染 → S95_fea vs S95_proxy
```

**判定标准**（分层）:

| 层级 | 指标 | 阈值 | 含义 |
|:---:|------|:---:|------|
| **形状** | RMS(w_proxy, w_fea) | < 0.5mm | 形状预测准确 |
| **形状** | R²(w_proxy, w_fea) | > 0.95 | 空间模式正确 |
| **光学** | |S95_proxy - S95_fea| / S95_fea | < 10% | 光学预测准确 |
| **光学** | S95_fea < S95_ellipse | 确认 | 优化有效果 |

**执行计划**:
1. 先完成 Phase 1（GPU 重力集成 + D1 梯度验证）
2. 运行 2×2=4 组优化（2 位置 × 2 初始化）
3. 选取最优结果送 FEA 验证
4. 如需迭代，调整超参数后重复

**这是 P0 最高优先级实验。** 如果 E1 通过，项目的核心目标"物理可实现"即得到证明。

---

### E2: 中间优化步骤的 FEA 追踪 [FEA — 可选增强]

**问题**: 优化过程中间步骤的代理模型预测是否也在物理上准确？（不仅仅是最优点）

**方法**: 选取优化的 iter 0, 5, 10, 20, 50 的螺栓配置，各做一个 FEA 验证。

**价值**: 确认代理模型的梯度在整个优化路径上都准确，而不仅仅是终点。

---

## Phase 3: 物理可实现性约束

### F1: 螺栓行程约束验证 [纯 Python + 优化重跑]

**问题**: 优化器输出的螺栓高度是否可以转化为物理可实现的螺栓伸出量？

**当前后处理**（CLAUDE.md）:
```
h_pipe_final = h_opt - max(h_opt) - 0.5mm    # 全部 ≤ -0.5mm (管线约定)
h_phys       = -h_pipe_final                   # 全部 ≥ +0.5mm (物理约定)
h_stroke     = h_phys - min(h_phys)            # 实际伸出量, 最短=0
```

**待验证**:
1. 当前优化结果的 `max(h_stroke)` 是否在商用螺栓行程范围内？（通常 ≤ 30mm）
2. 零初始化优化的最终螺栓行程是否合理？
3. 椭圆初始化是否有螺栓行程优势？

**如果需要约束**:
- 在 loss 中加入 `max(0, |h_b| - h_max)^2` 惩罚项
- 或在 B-spline CP 参数化中约束 CP 范围

---

### F2: 斜面/曲率制造约束 [纯 Python + 可能需要 C++ loss]

**问题**: 优化后的镜面局部斜率是否超过玻璃可承受的弯曲极限？

**方法**:
1. 从优化后的 `h_opt` 计算代理模型表面 `w(x,z)`
2. 计算局部斜率 `|∇w|` 和曲率 `κ_xx, κ_zz`
3. 对照玻璃制造约束：典型浮法玻璃可弯曲曲率半径 > 5m

**判定标准**:
- 局部斜率 < 0.01 rad/m（~5.7° 弯曲）
- 曲率半径 > 5m（即 κ < 0.2 m⁻¹）

**已有基础**: `loss_curvature.slang` 和 `loss_slope.slang` 已实现，`bolt_curvature.slang` 已实现曲率的解析梯度。只需在配置中启用。

---

### F3: 螺栓灵敏度分析 [纯 Python]

**问题**: S95 对每个螺栓高度误差的敏感度如何？制造公差（如 ±0.1mm）会导致多大 S95 退化？

**方法**:
```python
for b in range(35):
    h_perturbed = h_opt.copy()
    h_perturbed[b] += 0.1mm  # 制造公差
    S95_perturbed = evaluate_s95(h_perturbed)
    sensitivity[b] = (S95_perturbed - S95_opt) / 0.1
```

**价值**: 
- 识别关键螺栓（对 S95 影响大的位置）
- 为制造公差分配提供依据
- 如果某些螺栓极其敏感，说明优化可能找到了不稳定的局部极小

---

## Phase 4: 全工况鲁棒性

### G1: 训练/测试角度交叉验证 [纯优化重跑]

**问题**: 在部分太阳方向上优化的螺栓配置，在未见过的太阳方向上是否仍然有效？

**方法**:
1. 将 36 个太阳方向分为训练集（24 方向）和测试集（12 方向）
2. 仅在训练集上优化
3. 在测试集上评估 S95（不做优化）
4. 比较：训练 S95 vs 测试 S95

**判定标准**: 测试 S95 退化 < 20%（即泛化良好）

**变体**: 按角度分层划分（每组包含低/中/高角度），vs 按方位角划分（东/南/西/北）

---

### G2: 全年度模拟 [纯 Python]

**问题**: 优化配置在全年的实际运行中，综合光学效率如何？

**方法**:
1. 加载全年 8760 小时的太阳位置数据
2. 对每个小时计算 cosθ 和重力缩放
3. 如可能，计算每个小时的 flux 分布和 S95
4. 汇总：年均 S95、年均溢出损失、各月统计

**简化版**: 使用 TMY（典型气象年）12×24=288 个代表性时刻

**价值**: 将单点 S95 转化为实际年度发电量预估，是与工程实践对接的关键指标。

---

## 实验执行优先级与依赖

```
                          A3 ──┐
                          A4 ──┤
                  C1 ─────────┤
                              ├──→ GPU-G ──→ D1 ──→ E1 ──→ E2
                  B1 ─────────┤                      │
                  A2 ─────────┘                      ├──→ F1, F2, F3
                                                     │
                                                     └──→ G1 ──→ G2
```

### 推荐执行顺序

| 批次 | 实验 | 需要资源 | 预计时间 |
|:---:|------|------|:---:|
| **Week 1** | A3, A4, C1 | 本机 Python | 1-2h |
| **Week 1** | GPU-G | 本机 C++ | 4-8h |
| **Week 1-2** | B1, D1 | 本机 Python + GPU | 2-4h |
| **Week 2** | A2 | 台式机 FEA | 2-4h (含 FEA 求解) |
| **Week 2-3** | **E1** 🔑 | 本机优化 + 台式机 FEA | 1-2 天 |
| **Week 3** | E2 | 台式机 FEA (多次) | 1-2 天 |
| **Week 3** | F1, F2, F3 | 本机 Python | 2-4h |
| **Week 4** | G1, G2 | 本机优化 + Python | 4-8h |

---

## 成功标准

项目"物理可实现"目标达成的最低条件：

1. ✅ **E1 通过**: 优化结果的 FEA 验证 RMS < 0.5mm，S95 预测误差 < 10%
2. ✅ **D1 通过**: 螺栓梯度符号一致率 > 90%
3. ✅ **F1 通过**: 螺栓行程在商用范围内（≤ 30mm）
4. ✅ **G1 通过**: 未见太阳方向 S95 退化 < 20%

如果 E1 未通过（FEA 验证 RMS > 0.5mm），需要回到代理模型层面诊断原因：
- 是否 VSM 在边界处的系统误差积累？
- 是否重力插值在优化路径上偏离？
- 是否大螺栓位移下的非线性效应（NLGEOM）显著？
