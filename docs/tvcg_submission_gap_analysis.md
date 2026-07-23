# TVCG 投稿差距分析与行动建议

> 初始撰写：2026-07-14 | 全面修订：2026-07-23（基于 7 月密集实验进展 + 论文大纲 + 投稿策略）

---

## 目录

1. [TVCG 期刊背景](#1-tvcg-期刊背景)
2. [当前项目状态（截至 2026-07-23）](#2-当前项目状态)
3. [差距分析：已完成 vs 待补](#3-差距分析已完成-vs-待补)
4. [论文框架大纲](#4-论文框架大纲)
5. [投稿策略建议](#5-投稿策略建议)
6. [执行路线图](#6-执行路线图)
7. [参考文献](#7-参考文献)

---

## 1. TVCG 期刊背景

IEEE TVCG（Transactions on Visualization and Computer Graphics）是计算机图形学与可视化的旗舰期刊。主要投稿通道为 IEEE VIS 会议 special issue track，采用两轮审稿制。

| 指标 | 数据 |
|------|------|
| VIS 2024 接收率 | 124/557 = **22.3%** |
| 审稿轮次 | 2 轮（条件接受 → 修订 → 终审） |
| 审稿人数 | ≥3（2 PC members + 1 external） |
| 论文类型 | Technique / System / Application / Evaluation / Theory |

### 五项核心审稿标准

1. **Scientific quality and novelty** — 科学质量与新颖性
2. **Potential impact** — 潜在影响力
3. **Degree to which evidence supports the findings** — 证据对结论的支持程度
4. **Appropriateness of methodology** — 方法适当性
5. **Research process followed** — 研究过程严谨性

### 相关发表先例

| 论文 | 期刊/会议 | 年份 | 与本项目的关系 |
|------|-----------|------|---------------|
| *Computational Caustic Design for Surface Light Source* (Zhou et al.) | TVCG Vol.32(2) | 2026 | 可微渲染 + 自由曲面透镜优化 + CNC 实物验证 |
| *SurroFlow* (Shi et al.) | TVCG Vol.31(1) | 2025 | Normalizing-flow 代理模型替代物理仿真 |
| *Efficient Specular Glints Rendering With Differentiable Regularization* (Fan et al.) | TVCG Vol.29(6) | 2023 | 可微路径追踪 + 微结构 BRDF 优化 |
| *Automatic heliostat learning for in situ CSP metrology* (Pargmann et al.) | Nature Comms | 2024 | **最接近的工作**：可微光线追踪用于定日镜表面计量 |
| *Differentiable design of freeform optics* (Sun, Deng, Zhang) | ACM TOG/SIGGRAPH | 2025 | 可微渲染 + 物理光学仿真 + 实物原型验证 |

**关键定位**：Pargmann et al. (2024) 做的是 *inverse metrology*（从校准图像反推表面误差，面向已安装镜子），本项目做的是 *design optimization*（出厂前螺栓预调优化）。两者的 differentiable ray tracing 底座相似，但优化变量本质不同——螺栓机械参数 vs 表面法向场。

---

## 2. 当前项目状态

### 2.1 核心管线（全部完成）

| 组件 | 状态 | 关键指标 |
|------|:--:|------|
| GPU S95 协作二分查找 | ✅ | 单 workgroup 256 线程 20 轮二分，与 CPU 版误差 ~1e-6 |
| 免原子定点归约 | ✅ | gradPartialTile 12 KB，取代 368 MB boltGradPartial |
| Command buffer 合批 | ✅ | 每 sun 单次 submit |
| 可见性缓存 + 路径重放 | ✅ | rayValidity bitmask，反向零遮挡查询 |
| 稀疏像素剔除 (activePixelList) | ✅ | ~49% workgroup 减少 |

### 2.2 P0/P1 优化（2026-07-20 全部落地并验证）

| 项 | 描述 | 实测结果 |
|:---|------|------|
| **A1** 逐光线预裁剪 | 宏观法向反射角预测试，cutoff 经 sunp[11] 传入 | 无损 −4.8%（margin≥8 位精确）；有损 margin=−30 可达 ~3.2× |
| **L1** 效率正则项 | λ·M·E_ref/E 加至 S95 loss | 机制精确生效（偏移 +28,342 ≈ 理论 +28,260），λ=0.1 代价 +0.65% S95 |
| **L4** tanh 行程约束 | h = h_max·tanh(ε)，始终启用 | 最优质量无损（50.0476 vs 50.0387），行程内建 <40 mm |
| **A2** 编译期日轮特化 | Buie/Pillbox/Gaussian 三入口 | 性能中性（分支非瓶颈），代码保留 |
| **L3** 逐迭代种子 | randomize_seed 机制就位 | 默认 OFF，多种子重评实验待做 |
| **A4** 多 sun 合批 | 36→6 submits/iter | **已舍弃**：实测性能中性（submit 开销仅 ~0.2%，低于噪声） |
| **A3** reflection-only | — | **已放弃**：改变物理模型，与全折射不可比 |

### 2.3 太阳方向采样系统（2026-07-22 完成）

| 模式 | 方向数 | 设计 | 200 iter 耗时 |
|------|:---:|------|:---:|
| paper | ~110 | 12 月 × 1 天 × 13 时点（真太阳正午对称） | ~15 min |
| balanced（推荐） | ~334 | 12 月 × 3 天 × 13 时点 | ~50 min |
| dense | ~1556 | 12 月 × 14 天 × 13 时点 | ~4 h |

**核心实验结论**（详见 `sundir_sample/`）：

| 定日镜朝向 | 36dir 过拟合 | 110dir 过拟合 | 334dir 过拟合 | 推荐最低训练集 |
|-----------|-------------|--------------|--------------|:---:|
| North（面南） | +0.37 m² | +0.03 m² | ±0.00 m² | 36dir |
| East（面西） | **+1.69 m²** | +0.45 m² | +0.01 m² | **≥110dir** |
| West（面东） | **+1.71 m²** | +0.29 m² | — | **≥110dir** |

东西侧对面型优化的训练集敏感度是北侧的 4–5 倍。110dir (paper) 在各朝向下均为最佳速度/精度平衡点。

### 2.4 FEA 验证体系（2026-07-20–21 重组）

**三路验证管线**（`scripts/post_fea_validation.py`）：

| 对比对 | RMS | R² | shape_corr | 结论 |
|------|:---:|:---:|:---:|------|
| **APDL vs GUI** (29.5°) | **0.050 mm** | **1.0000** | **1.0000** | 位精确一致——自动化 APDL 可替代手工 GUI |
| **APDL vs GUI** (58.5°) | **0.051 mm** | **1.0000** | **1.0000** | 同上 |
| Proxy vs APDL (29.5°) | 2.79 mm | 0.909 | 0.963 | 代理系统性高估形变幅值 |
| Proxy vs APDL (58.5°) | 3.34 mm | 0.873 | 0.953 | 高角度偏差更大 |

### 2.5 光斑验证（2026-07-20）

对 North 300m 最优螺栓配置（35.7 mm max），在 29.5° 和 58.5° 进行 FEA vs TPS Proxy 能流对比：

| 指标 | 29.5° | 58.5° |
|------|:---:|:---:|
| NRMSE | 0.017 | 0.018 |
| 能流相关系数 | **0.997** | **0.996** |
| S95 偏差 | −11.7% | −13.2% |

> **结论**：形变误差（~2-3 mm RMS）经光学低通滤波后仅造成 ~1.7% NRMSE。S95 偏乐观 12–13%（代理形变幅值更大 → 聚焦更好），但光斑形态高度一致（相关系数 >0.996）。

### 2.6 Ellipse vs TPS LSQ 对比（2026-07-22）

四面镜椭圆解析面 vs TPS 最小二乘拟合：

| 镜面 | 形变 RMS | R² | shape_corr | S95 比 (TPS/ellipse) |
|:---:|:---:|:---:|:---:|:---:|
| North | 0.40 mm | 0.9984 | 0.9992 | 1.017 |
| East | 0.41 mm | 0.9983 | 0.9992 | 1.015 |
| South | 0.41 mm | 0.9981 | 0.9991 | 1.013 |
| West | 0.40 mm | 0.9983 | 0.9992 | 1.015 |

> **结论**：TPS 表示能力几乎无损失地覆盖椭圆解析面（形变 RMS <0.41 mm, R² >0.998），证明 TPS 35-bolt 参数化的表示能力充分。

### 2.7 四面镜优化结果（2026-07-17, 20-bin 数据修正后）

| 镜面 | 初始 S95 | 最优 S95 | 改善 | Max Stroke |
|:---:|:---:|:---:|:---:|:---:|
| North | 227.3 m² | **50.05 m²** | 78.0% | 36.0 mm |
| East | 214.4 m² | **65.11 m²** | 69.6% | 35.9 mm |
| South | 198.3 m² | **73.13 m²** | 63.1% | 34.6 mm |
| West | 215.0 m² | **64.67 m²** | 69.9% | 36.7 mm |

> 配置：200 iter, lr=4e-4 constant, Adam β=(0.9, 0.999), 36 sundirs, pixel-centered 32×32 grid, 20-bin plate-normal gravity, Buie CSR=0.01, DNI=1000 W/m².

---

## 3. 差距分析：已完成 vs 待补

差距分级沿用原有约定：

- 🔴 **致命差距** — 缺少则直接拒稿
- 🟡 **重大差距** — 审稿人会重点攻击，需在投稿前解决
- 🟢 **增强项** — 加分但不致命

---

### 3.1 🔴 致命差距

#### 差距 1：缺少与竞争方法的对比实验

| 对比维度 | 当前状态 | 待补实验 | 预期结论 |
|----------|:--:|------|------|
| **优化算法**：Adam vs CMA-ES vs BayesOpt | ❌ 未做 | Python black-box wrapper 调用 C++ 前向；CMA-ES（`cma` 库）、BayesOpt（`scikit-optimize`）；记录 S95 vs 评估次数 | Adam 在 35D 问题上样本效率远超无梯度方法 |
| **参数化**：TPS 35-bolt vs Bézier 16-CP | ❌ 未做 | 重跑 Bézier 模式优化（已有代码），记录 S95 vs 自由度 | 35-bolt 优于 16-CP（自由度更高），但边际递减 |
| **初始化**：零初始化 vs 椭圆 LSQ | ❌ 未做 | 椭圆面 TPS LSQ 拟合作为 warm-start，对比收敛曲线 | 椭圆 warm-start 可能加速前期收敛 |

**优先级**：P0 | **估计工作量**：3–4 周

#### 差距 2：缺少系统消融实验

| 消融组件 | 当前状态 | 待补实验 |
|----------|:--:|------|
| 自影响修正 ON/OFF | ❌ | 关掉 `phi_kernel[j, self] += λ`，跑优化对比 S95 + 面型 RMS |
| NLGEOM-ON vs OFF 重力 | 🟡 有 NLGEOM-ON/OFF 对比数据 | 用 OFF bins 重跑优化，量化 S95 退化 |
| 重力 bin 密度 5/10/20 | 🟡 CLAUDE.md 报告 10-bin 已充分 | 用最终管线重验证，输出正式消融表 |
| SPP 32²/25²/20²/16² | ❌ | SPP 扫描，记录最终 S95 + 收敛曲线稳定性 |
| **Sundir 密度** 36/110/334 | ✅ **已完成** | 直接整理为消融图（训练/验证 S95 vs 方向数） |
| **A1 预裁剪** ON/OFF | ✅ **已完成** | 位精确已验证，消融表直接引用 |
| **L1 效率项** λ = 0/0.01/0.05/0.1 | 🟡 仅 λ=0 vs 0.1 | λ 扫描 → S95 vs 能量 Pareto 图 |

**优先级**：P0 | **估计工作量**：1–2 周（sundir 消融已做完，SPP + 自影响 + NLGEOM 是主要新工作）

#### 差距 3：缺少实物验证或系统误差预算分析

**路径 B（最低可接受）当前进度**：

| 误差源 | 量化方法 | 当前估计 | 状态 |
|--------|---------|------|:--:|
| TPS 基函数表示误差 | 椭圆面 → 最佳 TPS 拟合残差 | RMS **0.40 mm** (四面镜均值) | ✅ 已有 |
| 线性叠加假设误差 | FEA-ON(全螺栓) vs proxy(全螺栓) | RMS **2.0–3.3 mm**, shape_corr **0.95–0.96** | ✅ 已有 |
| 光斑能流误差 | FEA vs Proxy 光斑对比 | NRMSE **0.017–0.018**, 相关系数 **>0.996** | ✅ 已有 (仅 North 2 角度) |
| 重力插值误差 | 20-bin 线性插值 vs 加密 reference | 10-bin → 20-bin 变化 <0.03 mm RMS（螺栓解相关 >0.9999） | ✅ 已有 |
| 渲染器离散化误差 | SPP 32²→64² 外推 / SPP 扫描 | **待测** | ❌ |
| 材料参数不确定度 | E, ν, 玻璃 n ±5% 扰动 → S95 变化 | **待测** | ❌ |
| 太阳形状敏感度 | Buie vs Pillbox vs Gaussian → S95 差异 | **待测** | ❌ |

**待补**：将以上整合为一份 Error Budget Table（误差源 | 量级 | S95 影响 | 可减小性），并完成渲染器 + 材料 + 太阳形状三项补充测量。

**优先级**：P0 | **估计工作量**：1–2 周（主要是表格整合 + 3 项补测）

---

### 3.2 🟡 重大差距

#### 差距 4：面型验证不完整

| 维度 | 当前覆盖 | 待扩展 |
|------|------|------|
| 镜面 | North（有螺栓 FEA） | East/South/West 有 ellipse 级验证，**缺有螺栓 FEA 对照** |
| 角度 | 29.5°, 58.5°（North 优化后） | 扩展到 **5–6 角度**（14°/29.5°/45°/58.5°/67°），覆盖全工作范围 |
| 空间分布 | 仅有全局 RMS/R² | 需要 **per-pixel 误差热力图**（板上哪里误差大？边角 vs 中心？） |
| 工作点 | 优化后螺栓 FEA 验证仅 North | 需要 **四面镜 × 2 工作点**（零螺栓纯重力 + 优化后螺栓） |

**优先级**：P1 | **估计工作量**：2–3 周（主要是 ANSYS 批量跑 FEA 对照）

#### 差距 5：光斑验证不完整

| 维度 | 当前覆盖 | 待扩展 |
|------|------|------|
| 角度数 | 2 个 (29.5°, 58.5°) | 至少 4–5 个代表性角度 |
| 镜面数 | 仅 North | 至少再加 East 或 West |
| 全年评估 | ❌ | 用最优螺栓跑 334/1556 方向的纯前向 S95 评估（不反向，~15-20 min） |
| 多指标 | 仅 NRMSE + correlation + S95 | 加总能量比 (E_proxy/E_fea)、峰值比、溢出能量 |

**全年 S95 分布**是论文的重要图表——展示优化解的泛化性能。单次纯前向 ~20 min 完成。

**优先级**：P1 | **估计工作量**：1–2 周

#### 差距 6：收敛性与敏感度分析

| 分析维度 | 当前状态 | 待补实验 |
|----------|:--:|------|
| 初始化敏感度 | ❌ | 零初始化 vs 椭圆 LSQ vs 3 个随机种子 → 是否收敛到同一解？ |
| 学习率扫描 | ❌ | lr ∈ {5e-5, 1e-4, 2e-4, 4e-4, 8e-4} × 200 iter |
| Adam β 参数 | ❌ | β₁ ∈ {0.8, 0.9} × β₂ ∈ {0.99, 0.999} |
| 多种子稳健性 (L3) | 🟡 机制就位 | randomize_seed=ON，同一配置 5 seeds → 解的标准差 |
| 不同螺栓数 | ❌ | 35 (7×5) vs 36 (6×6) 收敛对比 |

**优先级**：P1 | **估计工作量**：1–2 周

#### 差距 7：与相关工作的差异化定位（写作）

需要在论文中显式论述与以下工作的区别：

| 工作 | 共同点 | 区别点 |
|------|------|------|
| Pargmann et al. (2024) | 可微光线追踪用于定日镜 | 他们是 *inverse metrology*（诊断已装镜子），我们是 **design optimization**（出厂前预调）；我们有力学代理模型连接螺栓→面型→光学 |
| ARCAim / diffspt (2026) | Vulkan compute + Slang AD + 接收面 MCRT | 他们优化瞄准点（2 DOF/mirror），我们优化面型（35 DOF/mirror）；我们有 TPS 力学代理模型；我们的梯度穿越力学→光学双域 |
| Zhou et al. (TVCG 2026) | 可微渲染 + 光学设计优化 | 他们是透镜自由曲面，我们是反射镜支撑结构；我们的优化变量是机械参数（螺栓行程）而非光学面型直接参数 |
| Sun et al. (TOG 2025) | 可微自由曲面光学 | 同上——机械参数 vs 光学面型 |

**优先级**：P1 | **估计工作量**：3–5 天（纯写作）

#### 差距 8：性能加速

| 项 | 状态 | 说明 |
|------|:--:|------|
| A5 网格课程 16²→32² / 低 SPP + 滤波 | ❌ **最大剩余加速杠杆** | 前 60% iter 用 16×16 网格（成本 1/4），后 40% 切 32×32 精修。预期总时间 −30–40% |
| A4 多 sun 合批 | ⚠️ 已舍弃 | 实测性能中性（submit 开销仅 ~0.2%） |
| L2 反向滤波 (dL/dF) | ❌ | 与 A5 低 SPP 配套降噪，S95 对通量扰动敏感需先量化 |

**优先级**：P1（A5 低风险高收益） | **估计工作量**：1–2 周（A5）

---

### 3.3 🟢 增强项

| # | 增强项 | 状态 | 工作量 |
|:---:|------|:--:|:---:|
| 2.9 | 全年 1556 方向 S95 分布统计 | ❌ | 1 周 |
| 2.10 | B-spline 降维 (25 CP → 35 bolts) | ❌ | 3 天（已有实现） |
| 2.11 | 6×6 vs 7×5 螺栓布局对比 | ❌ | 3 天（已有两个 JSON） |
| 2.12 | 开源代码 + 可复现管线 | 🟡 代码在 repo | 1 周（整理 doc + 配置清理） |
| — | cosθ 修正 + 重跑椭圆三方法对比 | 🟡 | ~1 天 |

---

### 3.4 差距汇总矩阵

| 优先级 | # | 差距 | 已完成 % | 剩余工作量 | 对论文的影响 |
|:---:|:---:|------|:---:|:---:|------|
| 🔴 P0 | 1 | 对比实验（优化算法 + 参数化） | 0% | 3–4 周 | 无对比 = 直接拒稿 |
| 🔴 P0 | 2 | 系统消融实验 | ~40% | 1–2 周 | 核心组件贡献无法证明 |
| 🔴 P0 | 3 | 误差预算 (Path B) | ~60% | 1–2 周 | 代理模型可信度无定量支撑 |
| 🟡 P1 | 4 | 面型验证扩展 | ~30% | 2–3 周 | 验证范围不足，泛化性存疑 |
| 🟡 P1 | 5 | 光斑验证扩展 + 全年 | ~25% | 1–2 周 | 光学端证据单薄 |
| 🟡 P1 | 6 | 收敛性/敏感度分析 | ~10% | 1–2 周 | 方法稳健性无定量支撑 |
| 🟡 P1 | 7 | 差异化定位论述 | 0% | 3–5 天 | novelty 不清晰 |
| 🟡 P1 | 8 | A5 网格课程加速 | 0% | 1–2 周 | 性能数字不够有竞争力 |
| 🟢 P2 | 9–12 | 增强项 | 0–20% | 2–3 周 | 锦上添花 |

**总估计剩余工作量**：**10–16 周**（全职），集中在对比实验 + 验证扩展 + 论文写作。

---

## 4. 论文框架大纲

### 4.1 建议投稿信息

| 项目 | 内容 |
|------|------|
| **目标期刊** | IEEE TVCG（VIS 2027 Special Issue）或 Solar Energy（备选） |
| **论文类型** | Technique Paper |
| **页数** | 10–12 页（TVCG 正文上限 12 页） + 补充材料 |

### 4.2 建议标题

**主标题**（二选一）：

> **Differentiable Heliostat Surface Optimization: Connecting Bolt Strokes to Optical Performance via Thin-Plate Spline Proxy Models**

> **Bolt-Stroke Optimization of Heliostat Surfaces with Differentiable Ray Tracing and Physics-Based Proxy Models**

### 4.3 作者与贡献

建议按贡献排序为：
- **第一作者**：你（核心方法 + 全部实验 + 代码实现）
- **通讯/合作者**：如能纳入 FEA / CSP 领域导师，可增强学术可信度

### 4.4 核心创新点（论文卖点）

1. **首个连接机械自由度 → 光学性能的完全可微优化管线**
   - 螺栓行程 (35 DOF) → TPS 影响函数 → 表面位移 → MCRT → S95 loss → 梯度反传
   - 梯度穿越**两个物理域**（力学 + 光学），此前无人实现

2. **TPS 影响函数代理模型使梯度流动成为可能**
   - 物理驱动的 RBF 薄板样条（非数据驱动）
   - 单位分解性质（Σφ_b ≡ 1）保证叠加的物理正确性
   - 解析梯度链：dL/dh_b = Σ ∂L/∂flux · (∂flux/∂y · φ_b + ...)

3. **GPU 端到端零回读优化循环**
   - S95 阈值 GPU 协作二分查找（单 workgroup，20 轮）
   - Adam 在 tanh ε-空间更新
   - 单 command buffer 提交，全流程 4 字节回读/iter

4. **真太阳时对称训练集采样策略**
   - 消除均时差导致的训练不对称性
   - 实验验证：东西侧对采样密度敏感度是北侧 4–5 倍

### 4.5 详细结构

```
1. Introduction (≈1.5 pages)
   ├─ 1.1 CSP 定日镜聚光效率与面型精度的关系
   ├─ 1.2 现有面型优化方法的局限
   │      - FEA 试错：慢、非可微
   │      - 经验规则（椭圆面等）：不考虑安装位置特殊性
   │      - 无梯度黑箱优化：35D 问题上样本效率极低
   └─ 1.3 本文贡献（Contributions 列表，4–5 条）

2. Related Work (≈2 pages)
   ├─ 2.1 Heliostat Metrology and Surface Optimization
   │      - Pargmann et al. (2024): differentiable RT for inverse metrology
   │        区别：inverse problem（诊断已装镜）vs design optimization（出厂前预调）
   │      - ARCAim (2026): differentiable aiming optimization
   │        区别：瞄准点 (2 DOF/mirror) vs 面型 (35 DOF/mirror)
   ├─ 2.2 Differentiable Rendering for Optical Design
   │      - Zhou et al. (TVCG 2026): 可微焦散设计
   │      - Sun et al. (TOG 2025): 自由曲面透镜优化
   │        区别：机械支撑参数 vs 光学面型直接参数
   ├─ 2.3 Proxy Models and Reduced-Order Methods
   │      - SurroFlow (2025): normalizing-flow 代理
   │      - POD-ROM in computational mechanics
   │        区别：TPS 是物理驱动 RBF（无训练数据），不是数据驱动
   └─ 2.4 GPU-Accelerated Monte Carlo Ray Tracing for CSP
          - SolTrace, Tonatiuh, etc.

3. Method (≈4–5 pages)
   ├─ 3.1 Problem Formulation
   │      - 定日镜几何参数 + 螺栓布局
   │      - 目标：min_h Σ_sun S95(flux(h; sun)), s.t. |h_b| ≤ h_max
   │      - 太阳方向分布（训练集设计）
   │
   ├─ 3.2 TPS Influence Function Proxy Model  ← 核心创新 #1
   │      - 板法向位移场分解：w(r) = UY_grav(θ) + Σ h_b·φ_b(r)
   │      - TPS 系统构建：K_{ij} = r²log(r²) + λδ_{ij}
   │      - 自影响修正 + pixel-centered 网格
   │      - 单位分解性质 (Σφ_b ≡ 1) 及其物理意义
   │      - φ_b 解析导数（供 shader 法向计算）
   │      - 图：φ_b 的空间分布示例 (3–4 个代表性螺栓)
   │
   ├─ 3.3 Gravity Model: FEA-Direct + Dense Angular Interpolation
   │      - 20-bin 稠密角度方案
   │      - NLGEOM-ON vs OFF 差异
   │      - GUI 坐标系约定与自动化 APDL 管线
   │      - 图：重力分量随倾角变化 + 双线性插值示意
   │
   ├─ 3.4 Differentiable Ray Tracing Pipeline
   │      - 接收面收集式 MCRT（与 ARCAim 同构）
   │      - Buie 太阳模型 + 双层玻璃折射
   │      - 逐光线预裁剪 (A1) + 可见性位缓存
   │      - S95 损失函数：GPU 协作二分查找阈值 + sigmoid 损失
   │
   ├─ 3.5 Gradient Backpropagation Chain  ← 核心创新 #2
   │      - dL/dh_b = Σ_sun Σ_pixel [∂L/∂flux · (∂flux/∂y · φ_b + ∂flux/∂y_u · ∂φ_b/∂u + ∂flux/∂y_v · ∂φ_b/∂v)]
   │      - 三段反向：bwd_diff → reduceSurfaceGradients → projectBoltGradients
   │      - Slang 自动微分实现
   │
   ├─ 3.6 Optimization
   │      - Adam in ε-space with tanh bounding
   │      - 效率正则项 λ·E_ref/E
   │      - 单 command buffer 提交 + GPU 零回读
   │      - 算法伪代码
   │
   └─ 3.7 Training Set Design: True-Solar-Noon Symmetric Sampling
          - 均时差问题与对称采样动机
          - 12 月 × 3 天 × 13 时点方案
          - 东西侧经验训练集敏感度差异

4. Implementation (≈1 page)
   ├─ 4.1 Vulkan Compute + Slang Shader System
   ├─ 4.2 Dispatch 拓扑（见 CLAUDE.md dispatch 表）
   └─ 4.3 Data Flow per Iteration

5. Experiments (≈5–6 pages)
   ├─ 5.1 Experimental Setup
   │      - 镜面 12.84×9.45 m, 35 bolts (7×5), 接收器 R=10 m H=20 m
   │      - 四面镜 N/E/S/W @ 300 m
   │      - RTX 4070 SUPER, Buie CSR=0.01, 200 iter, lr=4e-4
   │
   ├─ 5.2 Main Results: Four-Heliostat Optimization  ← 图+表
   │      - 表：四面镜 初始 S95 → 最优 S95 → 改善率 → max stroke
   │      - 图：(a) 收敛曲线 S95 vs iter (4 镜 × 1 图)
   │           (b) 螺栓行程分布 35-bar chart (4 镜 × 1 图)
   │
   ├─ 5.3 Proxy Model Fidelity  ← 验证
   │      - Error Budget Table（见 §3.1 差距 3）
   │      - 图：Proxy vs FEA 形变散点 (per-angle)
   │      - 图：Proxy vs FEA 光斑像素级散点 + 残差图
   │      - 表：per-angle 形变指标 (RMS/R²/shape_corr/PV ratio)
   │      - 讨论：为什么 shape_corr >0.95 意味着误差不影响优化方向
   │
   ├─ 5.4 Ablation Study  ← 消融
   │      - 表：消融矩阵（组件 | S95 退化 | 相对影响 %）
   │        - 自影响修正 ON/OFF
   │        - NLGEOM-ON vs OFF 重力
   │        - SPP 32² → 25² → 20² → 16²
   │        - Sundir 36 → 110 → 334
   │        - L1 λ scan (Pareto)
   │      - 图：Sundir 消融 (训练 vs 验证 S95, 3 曲线)
   │      - 图：SPP 消融 (S95 vs SPP, 收敛稳定性)
   │
   ├─ 5.5 Comparison with Baseline Methods  ← 对比
   │      - 表：Adam vs CMA-ES vs BayesOpt
   │        (最终 S95 | 评估次数 | wall-clock | S95/千次评估)
   │      - 图：S95 vs 评估次数 (3 方法 × 1 图)
   │      - 表：TPS 35-bolt vs Bézier 16-CP vs 椭圆面
   │        (S95 | 自由度 | 形变 RMS vs 理想面)
   │
   ├─ 5.6 Convergence and Robustness  ← 稳健性
   │      - 图：初始化敏感度 (3 seeds → 收敛到同一解?)
   │      - 图：lr 扫描 (S95 vs lr, U 型曲线)
   │      - 图：λ scan → S95 vs 能量 Pareto 前沿
   │
   ├─ 5.7 Annual Performance Validation  ← 泛化
   │      - 表：334 方向全年 S95 分布 (中位数/P5/P25/P75/P95/最差 5%)
   │      - 确认优化解不只在训练方向有效
   │
   └─ 5.8 Performance and Scalability  ← 工程
          - 表：各阶段 wall-clock breakdown (per-iter)
          - A5 网格课程加速效果
          - 讨论：全场面型优化的计算扩展

6. Discussion (≈1 page)
   ├─ 6.1 为什么梯度优化在 35D 螺栓问题上有优势
   ├─ 6.2 TPS Proxy 的适用边界 (shape_corr >0.95 的前提)
   ├─ 6.3 局限：超大变形、材料非线性、热变形耦合
   ├─ 6.4 对未来全场 10k+ 镜面型优化的启示
   └─ 6.5 梯度穿越力学→光学域的更广泛意义

7. Conclusion (≈0.5 page)
   - 贡献重述
   - 关键数字：四面镜 63–78% S95 改善
   - 开源与可复现

Supplementary Material (单独 PDF)
   A. ANSYS APDL Automation Pipeline Documentation
   B. Sundir Sampling Script and Validation
   C. Full Parameter Tables
   D. Additional Convergence Plots
   E. Code Repository Link
```

### 4.6 关键图表清单

| # | 图/表 | 章节 | 数据来源 | 状态 |
|:---:|------|:---:|------|:--:|
| 1 | TPS φ_b 空间分布示例 | 3.2 | 已有数据 | ✅ 可做 |
| 2 | 重力分量-倾角曲线 + 双线性插值 | 3.3 | 已有数据 | ✅ 可做 |
| 3 | **四面镜收敛曲线** (S95 vs iter) | 5.2 | 已有 history.csv | ✅ 可做 |
| 4 | **螺栓行程分布** (35-bar × 4 镜) | 5.2 | 已有 BEST_BeCP | ✅ 可做 |
| 5 | Error Budget Table | 5.3 | 部分已有 | 🟡 需整合 |
| 6 | Proxy vs FEA 形变散点图 (4-5 angles) | 5.3 | North 2 角度已有 | 🟡 需扩展 |
| 7 | Proxy vs FEA 光斑散点 + 残差 | 5.3 | North 2 角度已有 | 🟡 需扩展 |
| 8 | **消融矩阵表** | 5.4 | 部分已有 | 🟡 需补实验 |
| 9 | Sundir 消融图 (train/val S95 vs dirs) | 5.4 | ✅ 已有 | ✅ 可做 |
| 10 | **Adam vs CMA-ES vs BayesOpt 对比** | 5.5 | ❌ | ❌ 核心实验 |
| 11 | TPS vs Bézier vs Ellipse 对比 | 5.5 | ellipse 已有 | 🟡 需 Bézier |
| 12 | 初始化/学习率敏感度 | 5.6 | ❌ | ❌ |
| 13 | λ-S95 vs 能量 Pareto 前沿 | 5.6 | 仅 λ=0, 0.1 | 🟡 需扫描 |
| 14 | 全年 S95 分布箱线图 | 5.7 | ❌ | ❌ |
| 15 | 各阶段耗时 breakdown | 5.8 | 已有 | ✅ 可做 |

---

## 5. 投稿策略建议

### 5.1 作者画像与投稿难度评估

本项目作者为**首次投稿者**，具备以下特点：

| 优势 | 劣势 |
|------|------|
| 工程实现能力强（完整 GPU 管线 + FEA 自动化） | 无英文学术写作经验 |
| 方法论理解深入（物理 + 数值 + 图形学交叉） | 无学术导师/合作者反馈 |
| 实验设计系统性强（消融/对比维度思考到位） | 不熟悉审稿 rebuttal 流程 |
| 创新性真实（机械→光学可微链是首创） | 学术文献覆盖面不够广 |

### 5.2 推荐路线：两步走策略

**不建议以 TVCG 作为首次投稿目标。** 原因：
- TVCG 接收率 ~22%，一审直接拒稿 ~55%
- 审稿人对新手痕迹极度敏感（图表规范、文献引用、论述克制度）
- 被拒后修改再投周期 6–12 个月，对首次投稿者时间成本过高

**建议策略**：

```
当前 ──→ 第一站: Solar Energy / Applied Optics ──→ 第二站: TVCG
         (~3–4 个月, 高概率录用)                   (~1 年后, 扩展版)
```

#### 第一站：Solar Energy（推荐首选）

| 指标 | 数据 |
|------|------|
| **JCR** | Q1（IF ~3.5, 中科院 2 区） |
| **审稿周期** | 8–12 周（快则 6 周收到一审意见） |
| **主题匹配度** | ⭐⭐⭐⭐⭐ — CSP 定日镜是期刊核心主题范围 |
| **对首次投稿者** | ⭐⭐⭐⭐ — 审稿标准比 TVCG 更侧重工程实用性 |
| **页面费** | 无（非 OA 不收版面费） |

**为什么 Solar Energy 是最佳首发目标**：
1. **主题完美匹配**：定日镜光学优化是 Solar Energy 的读者真正关心的问题
2. **方法创新性够用**：可微梯度优化 35D 螺栓问题对 SE 读者是显著的 methodological advance
3. **实验深度已接近**：补完对比实验 (CMA-ES) + 消融 + 误差预算后，实验部分对 SE 绰绰有余
4. **审稿意见有价值**：即使被拒（概率较低），意见也来自 CSP 领域专家，免费改论文
5. **发表记录铺垫**：有了 SE 这篇论文，再投 TVCG 时审稿人对你的学术可信度完全不同

**需要调整的地方**：
- 论文只需 8–10 页（非 12 页）
- Introduction 需要更多 CSP 工程背景，少一些图形学 framing
- Related work 加 CSP 定日镜面型优化文献（而非只列图形学管线）
- 实验部分整编为"工程验证"风格（少一些消融表格，多一些全年性能评估）

#### 备选：Applied Optics

| 指标 | 数据 |
|------|------|
| **JCR** | Q2（IF ~1.9, 中科院 3 区） |
| **审稿周期** | 4–8 周（非常快） |
| **主题匹配度** | ⭐⭐⭐⭐ — 光学仿真 + 可微优化 |
| **优点** | 审稿周期短，对方法论文宽容度最高 |
| **缺点** | 影响力低于 Solar Energy |

#### 第二站：TVCG（有了第一次经验后）

前提条件：
- 第一篇 Solar Energy 论文已录用/发表
- 至少 1 次投稿/审稿/rebuttal 经验
- 如有学术合作者加入更好
- 内容上做实质扩展（例如：POD-Linear 代理替换 TPS、全场多镜协同、实物缩比验证等）

### 5.3 如果坚持直投 TVCG

需要满足以下全部条件：
1. **找到有经验的学术合作者**（做过可微渲染或 CSP 发表，有指导博士生经验）
2. **对比实验全部做完**（CMA-ES + BayesOpt + Bézier 对比）
3. **有专门时间投入论文写作和图表**（预计 6–8 周 full-time）
4. **准备好 rebuttal 心理预期**——几乎一定有条件接受而非直接接受，需要逐条回应 ~30 条审稿意见

即使以上条件都满足，首次投稿接受率预估也仅 **30–40%**。

### 5.4 长期规划

| 时间线 | 里程碑 |
|------|------|
| 2026 Q3 | 补充实验 + 论文初稿（按 Solar Energy 框架） |
| 2026 Q4 | 投稿 Solar Energy |
| 2027 Q1 | 收到一审意见 → 修订 |
| 2027 Q2 | Solar Energy 录用/发表 |
| 2027 Q3–Q4 | 基于 SE 论文反馈 + 扩展（POD 代理等）→ 重写 TVCG 版 |
| 2028 Q1 | 投稿 TVCG VIS 2028 |

这个节奏比"直接冲 TVCG 然后被拒→等一年"要健康得多。

---

## 6. 执行路线图

### Phase 1：基础验证补齐（2–3 周）← 立即开始

| # | 任务 | 工作量 | 输出 |
|:---:|------|:---:|------|
| 1.1 | Error Budget Table 整合 | 3 天 | 一张表 + 配套论述 |
| 1.2 | 渲染器 SPP 外推 + 材料扰动 | 3 天 | 离散化 + 材料误差量级 |
| 1.3 | North 面型验证扩展到 5 角度 | 1 周 | 5-angle 形变 + 光斑对比 |
| 1.4 | 全年 334dir S95 评估 | 2 天 | 箱线图 + 分布统计 |
| 1.5 | 论文图表：基础图表先行制作 | 穿插 | 已可做的 8 张图 |

### Phase 2：对比实验（3–4 周）← 论文核心卖点

| # | 任务 | 工作量 | 输出 |
|:---:|------|:---:|------|
| 2.1 | Python black-box wrapper（C++ forward-only 调用） | 3 天 | CMA-ES/BayesOpt 可用的接口 |
| 2.2 | CMA-ES 对比实验 | 1 周 | 35D 问题收敛曲线 + 评估次数 |
| 2.3 | BayesOpt 对比实验 | 3 天 | 同上 |
| 2.4 | Bézier 16-CP 重跑 | 3 天 | TPS vs Bézier 对比 |
| 2.5 | 正式消融实验（自影响/NLGEOM/SPP） | 1 周 | 消融矩阵表 |

### Phase 3：收敛性与稳健性（1–2 周）

| # | 任务 | 工作量 | 输出 |
|:---:|------|:---:|------|
| 3.1 | 初始化敏感度（≥3 seeds） | 3 天 | 多 seed 收敛图 |
| 3.2 | lr + Adam β 参数扫描 | 1 周 | S95 vs lr U 型曲线 |
| 3.3 | λ (lambda_energy) 扫描 | 2 天 | Pareto 前沿图 |
| 3.4 | L3 多种子稳健性 | 2 天 | 随机种子下的解标准差 |

### Phase 4：性能与可选增强（1–2 周）

| # | 任务 | 工作量 | 输出 |
|:---:|------|:---:|------|
| 4.1 | A5 网格课程实现 + 验证 | 1 周 | 30-40% 加速数字 |
| 4.2 | B-spline 25-CP 实验 | 3 天 | scalability 讨论素材 |
| 4.3 | 6×6 布局对比 | 3 天 | 布局不敏感性论证 |

### Phase 5：论文写作（与 Phase 1–4 并行）

| # | 任务 | 时间 |
|:---:|------|:---:|
| 5.1 | Related Work 第一稿 | Week 1–2 |
| 5.2 | Method 第一稿（已有 CLAUDE.md 材料） | Week 2–4 |
| 5.3 | 图表制作（与实验进度同步） | Week 1–8 |
| 5.4 | Experiments 第一稿（Phase 1–2 完成后集中写） | Week 5–8 |
| 5.5 | Introduction + Discussion + Conclusion | Week 8–9 |
| 5.6 | 内部修改 + 英文润色 | Week 10–12 |

---

## 7. 参考文献

1. Zhou, Sun, Deng, Zhang. "Computational Caustic Design for Surface Light Source." *IEEE TVCG*, Vol. 32, No. 2, pp. 1911–1927, Feb 2026. DOI: 10.1109/TVCG.2025.3633081.
2. Shi et al. "SurroFlow: A Flow-Based Surrogate Model for Parameter Space Exploration and Uncertainty Quantification." *IEEE TVCG*, Vol. 31, No. 1, pp. 635–644, Jan 2025. DOI: 10.1109/TVCG.2024.3456372.
3. Fan et al. "Efficient Specular Glints Rendering With Differentiable Regularization." *IEEE TVCG*, Vol. 29, No. 6, pp. 2940–2949, June 2023. DOI: 10.1109/TVCG.2022.3144479.
4. Pargmann et al. "Automatic heliostat learning for in situ concentrating solar power plant metrology with differentiable ray tracing." *Nature Communications*, Vol. 15, Article 6997, 2024.
5. Sun, Deng, Zhang. "Differentiable design of freeform optics." *ACM TOG*, Vol. 44, No. 3, 2025. DOI: 10.1145/3732284.
6. ZeroGrads (ACM TOG 2024). DOI: 10.1145/3658173.
7. Xing, Cantareira et al. "A Review and Analysis of Evaluation Practices in VIS Publications." BELIV 2024. arXiv: 2408.16080.
8. IEEE VIS 2026 Review Instructions: <https://www.ieeevis.org/year/2026/info/call-participation/review-instructions/>
9. IEEE VIS 2025 Open Practices: <https://www.content.ieeevis.org/year/2025/info/open-practices/open-practices>
10. Hansen, Nikolaus. "The CMA Evolution Strategy: A Tutorial." arXiv: 1604.00772, 2016.
11. 叶金伟, 何采投. "定日镜场地光学效率模拟中的蒙特卡洛光线跟踪方法中时间采样点灵敏度分析研究." *Computer Science and Application*, Vol. 16, No. 3, pp. 96–105, 2026.

---

> **总结**：2026 年 7 月至今的实验密集期已将项目从"管线原型"推进到"实验半成品"阶段。P0/P1 代码优化 100% 完成、sundir 采样系统建立、FEA 验证体系重组、四面镜优化基线确立。剩余工作的重心从"搭架子"转向**"跑对比实验 + 写论文"**——CMA-ES 对比和系统消融是必须跨越的硬门槛。
>
> **对于首次投稿者，建议首发 Solar Energy 而非 TVCG**：主题完美匹配、审稿对工程方法更友好、录用率高得多、且为后续 TVCG 投稿提供学术发表记录的背书。无论选择哪个目标期刊，建议从现在开始与实验并行的论文写作——Related Work 早写早暴露文献盲区，Method 部分已有 CLAUDE.md 提供了完善的素材。
