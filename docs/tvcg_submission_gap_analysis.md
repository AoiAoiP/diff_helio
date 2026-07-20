# TVCG 投稿差距分析与补充实验规划

> 撰写日期：2026-07-14 | 基于 IEEE VIS 2024–2026 审稿标准与相关论文发表先例

---

## 1. TVCG 期刊背景

IEEE TVCG（Transactions on Visualization and Computer Graphics）是计算机图形学与可视化的旗舰期刊。主要投稿通道为 IEEE VIS 会议 special issue track，采用两轮审稿制。

| 指标 | 数据 |
|------|------|
| VIS 2024 接收率 | 124/557 = **22.3%**（一轮条件接受 23.2%，二轮 5 篇拒稿） |
| 审稿轮次 | 2 轮（条件接受 → 修订 → 终审） |
| 审稿人数 | ≥3（2 PC members + 1 external） |
| 论文类型 | Technique / System / Application / Evaluation / Theory |

### 五项核心审稿标准

1. **Scientific quality and novelty** — 科学质量与新颖性
2. **Potential impact** — 潜在影响力
3. **Degree to which evidence supports the findings** — 证据对结论的支持程度
4. **Appropriateness of methodology** — 方法适当性
5. **Research process followed** — 研究过程严谨性

TVCG 审稿指导明确鼓励审稿人 champion **"innovative, bold, creative, and potentially transformative work"**，即使验证不够穷尽也可以接受——但前提是方法的创新性确实突出。

### 相关发表先例

| 论文 | 期刊/会议 | 年份 | 与本项目的关系 |
|------|-----------|------|---------------|
| *Computational Caustic Design for Surface Light Source* (Zhou et al.) | TVCG Vol.32(2) | 2026 | 可微渲染 + 自由曲面透镜优化 + CNC 实物验证 |
| *SurroFlow* (Shi et al.) | TVCG Vol.31(1) | 2025 | Normalizing-flow 代理模型替代物理仿真 |
| *Efficient Specular Glints Rendering With Differentiable Regularization* (Fan et al.) | TVCG Vol.29(6) | 2023 | 可微路径追踪 + 微结构 BRDF 优化 |
| *Automatic heliostat learning for in situ CSP metrology* (Pargmann et al.) | Nature Comms | 2024 | **最接近的工作**：可微光线追踪用于定日镜表面计量 |
| *Differentiable design of freeform optics* (Sun, Deng, Zhang) | ACM TOG/SIGGRAPH | 2025 | 可微渲染 + 物理光学仿真 + 实物原型验证 |

**关键定位**：Pargmann et al. 做的是 *inverse problem*（从校准图像反推表面误差，面向已安装镜子），你做的是 *design optimization*（出厂前螺栓预调优化），需在 related work 中显式区别。

---

## 2. 差距分析

差距按严重程度分为三级：

- 🔴 **致命差距** — 缺少则直接拒稿
- 🟡 **重大差距** — 审稿人会重点攻击，需在投稿前解决
- 🟢 **增强项** — 加分但不致命，可部分延后

---

### 🔴 致命差距

#### 2.1 缺少与竞争方法的对比实验

当前管线只运行了"TPS 代理模型 + Adam 梯度优化"一种方案，没有任何对照组。TVCG 审稿人必然要求系统对比。

**需要补充的对比维度**：

| 对比维度 | 方案 A（你的方法） | 方案 B/C/D | 评估指标 |
|----------|-------------------|-----------|----------|
| 优化算法 | Adam + 可微梯度 | CMA-ES / 贝叶斯优化 / 遗传算法 | 最终 S95、收敛速度（iter / wall-clock）、目标函数评估次数 |
| 代理模型 | TPS 影响函数叠加 | 直接 FEA 每步求解（有限差分）/ 神经网络代理 | S95、面型 RMS vs FEA ground truth |
| 面型参数化 | 35 螺栓 TPS | Bézier 曲面（16 CP）/ NURBS / 直接节点位移（1024 变量） | S95、优化变量数 vs 质量 Pareto |
| 初始化策略 | 零初始化 | 椭圆解析解初始化 / 最小二乘初始化 | 最终 S95、收敛 iter 数 |

**最低要求**：
- 至少完成"优化算法对比"（CMA-ES 作为最小 baseline）
- 至少完成"面型参数化对比"（Bézier 16 CP 已有实现）
- 报告 wall-clock time 和 function evaluation count

**参考文献**：
- Hansen (2016) "The CMA Evolution Strategy: A Tutorial" — CMA-ES 标准实现
- ZeroGrads (ACM TOG 2024, DOI: 10.1145/3658173) — 神经网络代理 + 可微优化的对比范式

---

#### 2.2 缺少消融实验（Ablation Study）

需要系统性地移除/替换管线关键组件，展示每个组件对最终结果的贡献。

**消融矩阵**：

| 消融组件 | 移除方式 | 预期影响 | 评估指标 |
|----------|---------|---------|----------|
| 自影响修正 | 关掉 `phi_kernel[j, self] += λ` 修正 | 螺栓自位置响应被压低至 ~0.53，优化可能偏移 | S95 变化、面型 RMS vs FEA |
| NLGEOM 重力 | 替换为 NLGEOM-OFF 重力 bins | 低角度（≤30°）膜刚化效应丢失 | S95 变化、面型差 |
| 重力 bin 密度 | 5-bin vs 10-bin vs 20-bin | CLAUDE.md 报告 10-bin 已充分，需用最终管线重验证 | S95、收敛解相关度 |
| 稀疏 culling | 关闭 active pixel list | 无光学影响，仅性能差异 | iter time、总优化时间 |
| 渲染 SPP | 32² → 25² → 20² | 梯度噪声增加可能影响收敛 | 最终 S95 vs SPP、收敛曲线稳定性 |
| 太阳方向数 | 36 → 18 → 9 | 年化代表性下降 | 优化后 S95 在 738 方向上的泛化表现 |

**最低要求**：至少完成前 4 项（自影响、NLGEOM、bin 密度、SPP），每项展示定量退化。

---

#### 2.3 缺少实物验证或系统误差分析

这是三个致命差距中最难解决的。虽然 TVCG 对实物验证的要求略低于 TOG/SIGGRAPH，但完全没有是致命弱点。

**路径 A（理想，投入最大）**：实物原型验证
- 制作缩小比例镜面原型（如 1:4 缩比，~3m×2.4m）
- 用摄影测量/激光扫描实测优化后螺栓调节的面型
- 用太阳模拟器 + CCD 实测焦斑
- 对比 TPS proxy 预测 vs 实测

**路径 B（最低可接受）**：Simulation-to-reality gap 系统量化
- 以 FEA NLGEOM-ON 作为 pseudo-ground-truth
- 分解误差预算（error budget）：

| 误差源 | 量化方法 | 当前估计 |
|--------|---------|---------|
| TPS 基函数表示误差 | 理想椭圆面 → 最佳 TPS 拟合残差 RMS | CLAUDE.md 报告 0.63mm（但光学影响大） |
| 线性叠加假设误差 | FEA-ON(全螺栓) vs proxy(全螺栓) | CLAUDE.md 报告 RMS 1.53mm |
| 重力插值误差 | 20-bin 线性插值 vs 加密 40-bin reference | 待测 |
| 渲染器离散化误差 | SPP→∞ 外推 vs 32² | 待测 |
| 材料参数不确定度 | E, ν, 玻璃 n 的 ±5% 扰动 → S95 变化 | 待测 |

- 给出总误差预算表，讨论各项的量级与可控性
- 论证"代理模型误差不影响优化方向"（已有部分证据：CLAUDE.md 5.3 节）

**最低要求**：完成路径 B 的全部误差预算分析。

---

### 🟡 重大差距

#### 2.4 面型验证不完整

**当前状态**：仅验证了 North 300m 在 0°/29.5°/58.5° 三个角度下的面型（且 CLAUDE.md 标注为 10-bin 数据，需重做）。

**需要补充**：
- [ ] 用 **20-bin** 重力重做全部验证
- [ ] 扩展到 **5–6 个角度**覆盖全工作范围（如 0°/15°/30°/45°/60°/75°）
- [ ] **四面镜（E/S/W）的面型验证**——当前只有 North
- [ ] **空间误差分布图**——误差在板上哪里大？边角 vs 中心？与弯曲刚度分布的关系？
- [ ] **优化后工作点验证**——在优化后的非零螺栓高度下验证 FEA vs proxy，而非仅零螺栓纯重力
- [ ] 报告 per-angle 的 **RMS、R²、shapeCorr、slopeCorr**

**评估矩阵**：

| 镜面 | 0° | 15° | 30° | 45° | 60° | 75° |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| North 300m | ✓重做 | ✗ | ✓重做 | ✗ | ✓重做 | ✗ |
| East 300m | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| South 300m | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| West 300m | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

---

#### 2.5 光斑验证不足

**当前状态**：仅验证了 3 个太阳方向的 flux map。

**需要补充**：
- [ ] 使用 `738_sundir_year.txt` 报告 **全年 S95 分布**（中位数、P5/P25/P75/P95、最差 5% 场景）
- [ ] FEA 面型 → 光追 vs. TPS proxy 面型 → 光追：**逐像素 flux 相关性 + 散点图**
- [ ] 报告 **总能量、峰值能流、S95** 三指标的全年对比
- [ ] 修复 `main.cpp:218` 硬编码 `boltForwardSurface(1.0f)` → 使用正确的 `computeTilt(sunDir, pos, aim)` 计算 cosθ
- [ ] 在正确 cosθ 下重跑椭圆三方法对比（CLAUDE.md 后续工作#1）

---

#### 2.6 收敛性与敏感度分析

**需要补充**：
- [ ] **初始化敏感度**：零初始化 vs 椭圆初始化 vs 随机初始化（≥3 seeds）→ 是否收敛到同一解？
- [ ] **学习率敏感度**：lr ∈ {5e-5, 1e-4, 2e-4, 5e-4} → 最终 S95 vs lr 曲线
- [ ] **Adam β 参数**：β₁ ∈ {0.8, 0.9, 0.95}、β₂ ∈ {0.99, 0.999} 的影响
- [ ] **收敛速度**：报告 S95 进入最优值 5% 以内所需的 iter 数
- [ ] **不同螺栓数**：35 (7×5) vs 36 (6×6) → 收敛行为差异

---

#### 2.7 与最相关工作的差异化定位

需要在论文中显式论述与以下工作的区别：

| 工作 | 区别点 |
|------|--------|
| Pargmann et al. (2024) | 他们是 *inverse metrology*（诊断已有镜子），你是 *design optimization*（出厂前预调）；你有力学代理模型连接螺栓到面型，他们只有光学逆问题 |
| Zhou et al. (TVCG 2026) | 他们是点光源 → 透镜自由曲面设计，你是平行光 → 反射镜面优化；你的物理约束（重力/弯曲）是核心而非仅光学 |
| Sun et al. (TOG 2025) | 他们优化透镜曲面，你优化反射镜支撑结构；你的优化变量是机械参数（螺栓行程）而非光学面型直接参数 |

---

#### 2.8 性能加速未完成

多 sun 批量并行（CLAUDE.md 后续工作#3，预期 2–3× 加速）未实现。虽然不影响方法论创新性，但影响 "potential impact" 评分——TVCG 审稿人关注方法的工程可行性。

---

### 🟢 增强项

#### 2.9 全年性能评估

使用 738 太阳方向做全年 S95 统计（已有数据，需跑实验）。

#### 2.10 B-spline 降维

探索 `useBSpline`（25 CPs → 35 bolts）对优化质量和收敛速度的影响，作为 scalability 分析。

#### 2.11 螺栓布局对比

6×6 (36 bolts) vs 7×5 (35 bolts) — 已有两个布局 JSON，证明方法对布局不敏感。

#### 2.12 开源与可复现性

TVCG 鼓励 open practices。准备开源代码、数据、配置是加分项。

---

## 3. 补充实验优先级排序

| 优先级 | 实验 | 预计工作量 | 对应差距 | 备注 |
|:---:|---|:---:|:---:|---|
| **P0** | 与 ≥2 种无梯度优化方法对比（CMA-ES + 贝叶斯优化） | 高（~3–4 周） | 🔴#1 | 需实现 CMA-ES wrapper 调用 C++ 管线或 Python proxy |
| **P0** | 系统消融实验（≥5 组件逐个移除） | 中（~1–2 周） | 🔴#2 | 多数可在 Python proxy 中完成 |
| **P0** | Simulation-to-reality gap error budget | 中（~2 周） | 🔴#3 | 路径 B |
| **P1** | 用 20-bin 重做全部面型验证（5 角度 × 4 镜面 × 2 状态） | 中（~2–3 周） | 🟡#4 | 需 ANSYS 批量重算 FEA 对照 |
| **P1** | 全年 738 方向光斑验证 + FEA vs proxy 像素级对比 | 中（~1–2 周） | 🟡#5 | 数据已有，需编写对比脚本 |
| **P1** | 收敛性分析（初始化/lr/β 敏感度 + 收敛曲线） | 低（~1 周） | 🟡#6 | 参数扫描脚本 |
| **P1** | 修复 `main.cpp:218` cosθ bug + 重跑椭圆三方法对比 | 低（~1–2 天） | 🟡#5,7 | 代码修复 + 重跑 |
| **P1** | 差异化定位论述 + Related work 框架撰写 | 低（~3 天） | 🟡#7 | 论文写作 |
| **P2** | 多 sun 批量并行 + 性能对比 | 高（~2–3 周） | 🟡#8 | C++/Slang 重构 |
| **P2** | B-spline 降维实验 | 低（~3 天） | 🟢#10 | 已有实现，仅需跑实验 |
| **P2** | 6×6 vs 7×5 布局对比 | 低（~3 天） | 🟢#11 | 已有两个布局 JSON |
| **P3** | 实物原型制作 + 测量 | 很高（数月） | 🔴#3 路径 A | 需经费与加工资源 |

---

## 4. 建议的执行路线图

### Phase 1：基础修复 + 数据重跑（Week 1–2）

1. 修复 `main.cpp:218` cosθ bug
2. 用 20-bin 重跑 North 300m 面型验证（5 角度 × FEA 对照）
3. 编写全年 738 方向光斑对比脚本
4. 确定当前管线输出的"基线数字"（S95、面型 RMS、iter time）

### Phase 2：消融实验（Week 3–4）

1. 自影响修正 ON/OFF
2. NLGEOM-ON vs NLGEOM-OFF 重力 bins
3. 5-bin vs 10-bin vs 20-bin 重力
4. SPP 25² → 20² → 16²
5. 整理消融表格与论述

### Phase 3：对比实验（Week 5–8）

1. 实现 CMA-ES wrapper（Python proxy 侧）
2. 跑 CMA-ES / Bayesian opt / Adam 三方法对比
3. Bézier 16 CP vs TPS 35 bolt 参数化对比
4. 收敛性参数扫描

### Phase 4：误差预算 + 写作（Week 9–12）

1. Error budget 分析
2. 差异化定位论述
3. 论文初稿 + 图表

### Phase 5（可选，如条件允许）

1. 多 sun 批量并行优化
2. 实物原型制作

---

## 5. 投稿策略建议

### 首选：TVCG（通过 IEEE VIS 2027 或 Regular 通道）

- **VIS special issue**：截稿通常在每年 3 月（需确认 2027 日期），7 月通知一轮结果，10 月会议
- **Regular submission**：滚动接受，审稿周期 6–12 个月，没有会议 presentation 机会
- **建议走 VIS 通道**：有 presentation 曝光、审稿周期可控、且 VIS 鼓励"大胆创新"的偏好与你的方法论特征匹配

### 备选：ACM TOG / SIGGRAPH

- 如果你的实物验证能跟上，TOG 在 computational design/fabrication 赛道上声望更高
- TOG 对物理仿真精度的要求更苛刻

### 备选：Applied Optics / Optics Express

- 如果侧重光学结果验证，审稿周期短（4–8 周），但影响力不如 TVCG
- 可作为"保底"选项

### 关键决策点

| 时机 | 决策 |
|------|------|
| 现在 | 是否投入资源做实物原型？（决定走路径 A 还是 B） |
| Phase 3 后 | 如果对比实验显示 Adam 优势不明显，是否需要重新设计 framing？ |
| Phase 4 后 | 根据实验结果的质量决定投稿目标（TVCG vs TOG vs AO） |

---

## 6. 参考文献

1. Zhou, Sun, Deng, Zhang. "Computational Caustic Design for Surface Light Source." *IEEE TVCG*, Vol. 32, No. 2, pp. 1911–1927, Feb 2026. DOI: 10.1109/TVCG.2025.3633081.
2. Shi et al. "SurroFlow: A Flow-Based Surrogate Model for Parameter Space Exploration and Uncertainty Quantification." *IEEE TVCG*, Vol. 31, No. 1, pp. 635–644, Jan 2025. DOI: 10.1109/TVCG.2024.3456372.
3. Fan et al. "Efficient Specular Glints Rendering With Differentiable Regularization." *IEEE TVCG*, Vol. 29, No. 6, pp. 2940–2949, June 2023. DOI: 10.1109/TVCG.2022.3144479.
4. Pargmann et al. "Automatic heliostat learning for in situ concentrating solar power plant metrology with differentiable ray tracing." *Nature Communications*, Vol. 15, Article 6997, 2024.
5. Sun, Deng, Zhang. "Differentiable design of freeform optics." *ACM TOG*, Vol. 44, No. 3, 2025. DOI: 10.1145/3732284.
6. ZeroGrads (ACM TOG 2024). DOI: 10.1145/3658173.
7. Xing, Cantareira et al. "A Review and Analysis of Evaluation Practices in VIS Publications." BELIV 2024. arXiv: 2408.16080.
8. IEEE VIS 2026 Review Instructions: <https://www.ieeevis.org/year/2026/info/call-participation/review-instructions/>
9. IEEE VIS 2025 Open Practices: <https://www.content.ieeevis.org/year/2025/info/open-practices/open-practices>

---

> **总结**：当前项目有一条功能完整的管线，但实验深度距离 TVCG 标准差约 **6–12 个月的密集补充**。P0 的三个实验（对比方法、消融、误差预算）是"不做就过不了"的硬门槛，建议从 Phase 1 的 bug 修复和数据重跑开始，逐步推进。
