# 投稿方向分析与论文大纲设计

> 2026-07-28 全面重写（取代原《TVCG 投稿差距分析》）。
> 重写动因：① 毕业硬性要求明确为 **CCF-A 或 SCI 中科院一区**，旧版"首发 Solar Energy"建议不再成立；
> ② 项目主线已从"可微渲染管线"演进为**重力补偿叙事**（导师 2026-07-27 批评：proxy 必须起真正的优化作用）；
> ③ 期刊格局有重要事实更新（TVCG 中科院降区、Solar Energy 失去 Top、多篇直接竞争性先例发表）。
>
> 期刊数据核实日期：2026-07-28（LetPub/bioxbio/出版社官网交叉核对；审稿周期含网友自报成分，已标注）。

---

## 目录

1. [结论速览](#1-结论速览)
2. [投稿方向分析](#2-投稿方向分析)
3. [论文大纲设计（结合重力补偿主线）](#3-论文大纲设计)
4. [后续补充工作](#4-后续补充工作)
5. [竞争性先例精读清单](#5-竞争性先例精读清单)
6. [参考文献](#6-参考文献)

---

## 1. 结论速览

- **首选：Advanced Engineering Informatics (AEI)**——中科院工程技术 1 区 Top、IF 9.9、首轮决定 ~9 周，"AI + 物理 + 工程优化"正是其招牌栏目，与本工作形态匹配度最高，且已有形态最接近的先例（可微结构优化, 2024）。
- **强备选：Applied Energy**（1 区 Top, IF 11.0）——有同赛道先例（可微 MCRT 定日镜瞄准优化, 2025），可行性已被背书；但需要把收益从"单镜 S95"翻译成"全场年能量收益"，需补 2–4 周系统级实验。
- **TVCG（导师建议之一）**：满足 CCF-A 通道，但存在两个必须向导师如实说明的风险——(a) 中科院 2025 版已降为计算机大类 **2 区** Top（若学院按 SCI 一区通道认定则不算数，只有 CCF-A 通道算）；(b) 其 scope 要求图形学/可视化方法贡献，**经检索无任何太阳能/定日镜先例**，必须重构为"可微渲染方法 + 能源应用验证"，而本工作的图形学方法增量有限，桌拒风险中高。
- **Solar Energy**：主题最匹配、直接先例最多，但中科院 2025 版为 **2 区非 Top**，不满足硬约束，只能作为不计较分区时的选择。旧版文档"首发 Solar Energy"的路线作废。

---

## 2. 投稿方向分析

### 2.1 硬性约束

学院毕业要求：**CCF-A 或 SCI 一区**。国内语境的"SCI 一区"通常指**中科院分区表（升级版）大类一区**（非 JCR Q1，非小类）。按 2025 年 3 月升级版，两条通道各自可用的本刊相关期刊为：

- **CCF-A 通道**：图形学领域仅 TVCG、ACM TOG 现实可及（TOG/SIGGRAPH 对本应用题材过难，不列入）。
- **中科院一区通道**：AEI、Applied Energy、ECM、Energy、Renewable Energy、CMAME（均 1 区 Top）。

### 2.2 候选期刊对比矩阵

| 期刊 | 2024 JIF | 中科院 2025 大类 | CCF | 首轮决定 | APC (USD) | 与本课题匹配度 |
|------|:---:|:---:|:---:|:---:|:---::|------|
| **AEI** | 9.9 | **工程技术 1 区 Top** | — | ~9.3 周（官网）；评审后决定 49 天 | 3,380 | ★★★★★ AI×工程决策，PIML/可微优化主阵地 |
| **Applied Energy** | 11.0 | **1 区 Top** | — | 5.8 周（官网） | 4,210 | ★★★★☆ 需系统级能量收益叙事；有同赛道先例 |
| ECM | 10.9 | **1 区 Top** | — | 3.1 周（官网），但编辑处理慢著称（网友自报 ~12.8 月，有慢样本偏差） | 4,370 | ★★★★ 需突出能量转换收益 |
| Energy | 9.4 | **1 区 Top** | — | 首次决定 8 天；投稿→录用 126 天 | 4,050 | ★★★☆ 综合能源，体量大 |
| Renewable Energy | 9.1 | **1 区 Top** | — | 首次决定 15 天；→录用 158 天 | 4,270 | ★★★☆ CSP 镜场文章常见，偏系统评估 |
| CMAME | 7.3 | **1 区 Top** | — | 8.6 周；评审后决定 36 天（偏难，自报录用 ~20%） | 4,670 | ★★★★ 适合"数值方法为主体"的重构版本 |
| **TVCG** | 6.5 | 计算机 **2 区** Top | **A** | 2–4 个月；录用率 ~25% | ~2,645（混合 OA） | ★★☆ 无能源先例；须图形学方法贡献 |
| Solar Energy | 6.6 | 2 区（非 Top） | — | 12.6 周 | 4,390 | ★★★★★ 但不满足硬约束 |
| Engineering with Computers | 4.9 | 2 区 Top | — | 中位 5 天（官网） | 3,290 | ★★★ 不满足硬约束 |
| SMO | 4.0 | 3 区 | — | ~3 个月 | 4,190 | ★★★ 不满足硬约束 |

### 2.3 关键事实修正（相对旧版文档）

1. **TVCG 中科院降区**：2023 版曾为计算机大类 1 区 Top，2025 版降为 2 区 Top。它仍满足 CCF-A 通道，但若学院只认中科院一区，TVCG 已失效——**投稿前务必与教务确认认定口径**。
2. **Solar Energy 失去 Top 且从未进过大类一区**：2 区非 Top，不满足硬约束。
3. **SMO 降至 3 区**：优化专业刊路线关闭。
4. **出现直接竞争性先例**（2025 年集中发表，详见 §5）：可微光追用于定日镜 canting 优化（Solar Energy 2025）、瞄准优化（Applied Energy 2025）、面型逆问题（Solar Energy 2025 ×2）。赛道被验证可行，但"第一个做"的窗口正在关闭——**投稿时机有真实压力**。

### 2.4 三种可行定位的 framing 对比

**定位 A（AEI，推荐）**：*"Physics-informed differentiable optimization for structural-optical co-design of heliostats"*。卖点 = 诊断（重力形变分解）+ 界定（B\*/B_reachable 框架）+ 补偿（正则化端到端优化）+ 指南（镜位-纬度设计规则）的完整工程知识体系。AEI 审稿人吃"AI 给工程决策带来了什么新知识"这一套，我们的倾角分布设计指南、可补偿性判据正中下怀。

**定位 B（Applied Energy / ECM）**：*"Annual energy gains from gravity-compensated heliostat surface optimization via differentiable MCRT"*。卖点 = 系统级收益。需要新增：全场（或代表性镜阵）年能量收益折算、与 aiming 优化的收益对比。工作量 +2–4 周，期刊档次与影响力更高。

**定位 C（TVCG）**：*"Differentiable Monte Carlo ray tracing for opto-structural design optimization"*。卖点 = 可微渲染系统（GPU 零回读优化循环、协作二分 S95、跨物理域梯度链）。风险：图形学增量被质疑（"standard differentiable MCRT applied to a new domain"）；能源应用无先例，审稿人匹配困难。仅在导师坚持且确认 CCF-A 通道有效时考虑。

### 2.5 推荐决策

```
首选   AEI               （匹配度 × 分区 × 审稿速度 × 工作量 综合最优）
强备选 Applied Energy    （若愿意补全场能量实验，上限更高）
三选   ECM / Energy      （能源叙事同 B，作为被拒后的顺位）
方法版 CMAME             （若实验故事被质疑"工程案例太窄"时的重构出口）
TVCG   仅在确认 CCF-A 通道 + 导师坚持时
```

被拒顺位预案：AEI → Applied Energy/ECM → Energy/Renewable Energy。每次转投按目标刊调整 Introduction 与 Related Work（约 3–5 天工作量），实验主体不变。

---

## 3. 论文大纲设计（结合重力补偿主线）

### 3.1 新故事线（导师批评 → 论文中心论点）

导师的批评"proxy model 并未起到真正的优化作用"恰好定义了论文的中心论点。我们把"嵌入物理 proxy"从一个实现细节提升为**被严格检验的科学假设**：

> **论点**：物理代理模型嵌入可微渲染的价值不在于"多几层有物理意义的梯度链接"，而在于它使优化器能够**主动抵抗重力弯沉**，让受重力约束的真实面型逼近无重力理想面——且这一过程的可行边界可以被理论刻画、被实验测量。

支撑这个论点的四段证据链（全部来自当前工作）：

1. **问题是真的**（Phase 0–1）：修复重力法向耦合后，真实重力惩罚首次被量化——naive/ideal 达 1.001–1.539（South_150m 最大），且随镜位强非均匀。修复前重力只进高度不进法线，"优化≈椭圆拟合"的历史结果实为 bug 的幻影。
2. **边界是可算的**（Phase 0/2）：重力形变三分解（仿射≈0 / 二次≤0.6 mrad / 高阶凹陷主导 6.36 mrad@10°）+ 螺栓 TPS 子空间覆盖率仅 26–38% ⇒ 存在结构性不可约地板；B\*（无重力地板）与 B_reachable（有重力地板）给出差距的上下界。
3. **非均匀性是可解释的**（Phase 2）：镜位 + 纬度决定全年倾角分布（德令哈 300m NEWS：North θ∈[36°,65°] 全年落在 46° NLGEOM 过零低凹陷区 ⇒ 几乎免罚；South 24% 时间 θ<20° ⇒ 惩罚最大）——直接产出"哪些镜位需要补偿"的设计指南。
4. **逼近是可优化的**（Phase 3，在跑）：闭式补偿 init 只回收惩罚的 10–14%，端到端正则化优化（anchor=TPS 弯曲能、soft stroke、tanh 解除）负责回答"螺栓调节究竟能补回多少、以什么物理代价"。

### 3.2 贡献清单（Contributions）

1. **首个穿越力学-光学双域的定日镜面型端到端可微优化框架**：螺栓行程 (35 DOF) → TPS 影响函数 + FEA 重力库（含法向耦合）→ 面型 → MCRT → 年均 S95 → 梯度反传。修正了"重力不进法线"这一使此前所有同类结果失效的关键缺陷。
2. **重力形变的可补偿性理论**：仿射/二次/高阶三分解；支撑钉死平均平面 ⇒ 仿射≈0（解释 canting 类方法为何触及不到主损伤）；螺栓子空间与凹陷子空间近正交（斜率方差覆盖率 26–38%）⇒ 不可约地板的存在性与量级。
3. **可达性界定框架**：B\*（无重力地板）vs B_reachable（有重力地板）vs B_naive/B_comp（现状/闭式补偿）的四层差距分解，给出任何补偿策略效果的上界认证方法。
4. **镜位-纬度倾角分布模型**：由站址经纬度 + 镜场几何解析推出全年 θ 分布，解释重力惩罚的非均匀性并给出镜场设计指南（德令哈案例：北侧镜几乎免罚，南侧近场镜惩罚 1.54×）。
5. **面向地板逼近的正则化设计**：斜率空间锚定（物理上 = TPS 弯曲能 hᵀGh）、软行程墙、tanh 解除的系统消融，给出"逼近 B\* 而不失真/不过拟合"的正则化处方。

### 3.3 建议标题

- **AEI 版**：*Physics-informed differentiable optimization of heliostat surfaces against gravity-induced deformation: bounds, compensability, and field-position design rules*
- **Applied Energy 版**：*Gravity-compensated heliostat surface optimization via differentiable Monte Carlo ray tracing: from single-mirror bounds to field-level annual gains*
- **TVCG 版**（备用）：*Differentiable Monte Carlo ray tracing across structural and optical domains: heliostat surface optimization under gravity*

### 3.4 详细大纲（AEI 版，预计 30–40 页双栏）

```
1. Introduction (~3 页)
   ├─ 1.1 CSP 塔式系统与定日镜光学质量：面型误差是聚光损失首要来源
   ├─ 1.2 重力弯沉：一个被结构侧与光学侧同时忽视的耦合问题
   │      - 结构侧：FEA 可算形变，但不进光学目标
   │      - 光学侧：canting/瞄准调整只动仿射自由度
   │      - 仿真侧：可微光追已用于瞄准/计量，从未用于面型设计
   ├─ 1.3 三个研究问题：惩罚有多大？物理上能补多少？如何正则化逼近？
   └─ 1.4 贡献列表（§3.2 五条）

2. Related Work (~4 页)
   ├─ 2.1 Heliostat flux simulation: MCRT (SolTrace/Tonatiuh), 解析卷积
   │      (HFLCAL/UNIZAR), 神经代理 (Fast-NCM 等)
   ├─ 2.2 Heliostat surface adjustment: canting/facet 优化传统方法;
   │      可微光追先例（canting-DRT 2025, aiming-DMCRT 2025）;
   │      逆问题面型计量（Pargmann 2024, Inverse-DL-RT 2025）
   │      —— 逐一点明区分（见 §5）
   ├─ 2.3 Physics-informed ML & differentiable simulation in engineering
   │      design（AEI/CMAME 先例：可微结构优化 2024, PINN 综述）
   └─ 2.4 小结：三大流派（结构/光学/可微仿真）从未在"面型设计"点汇合

3. System model and problem formulation (~3 页)
   ├─ 3.1 定日镜-螺栓结构：12.84×9.45 m 玻璃镜、35 螺栓 (7×5) 支撑
   ├─ 3.2 镜场与站址：德令哈 (37.36°N, 97.29°E)、圆柱接收器、NEWS 镜位
   ├─ 3.3 目标函数：年均 S95 = Σ_sun w_sun · S95(flux(h; sun))，行程约束
   └─ 3.4 倾角 θ 的定义与全年分布（几何解析 + 德令哈 110dir 分布表）

4. Method (~10 页)
   ├─ 4.1 可微 MCRT 渲染器（Vulkan/Slang：Buie 日轮、双层玻璃折射、
   │      GPU 协作二分 S95、稀疏剔除、零回读优化循环）—— 适度压缩，
   │      细节放附录，强调"为跨域梯度而设计"的部分
   ├─ 4.2 FEA 衍生的 TPS 物理代理：
   │      w(r) = UY_grav(θ) + Σ h_b·φ_b(r)；20-bin NLGEOM 重力库；
   │      单位分解；自影响修正；法向耦合（w, dw/du, dw/dv 三平面）
   ├─ 4.3 梯度链：dL/dh_b 穿越光学→力学两域（公式 + 三段反向）
   ├─ 4.4 重力形变三分解与可补偿性（核心理论节）
   │      - 仿射/二次/高阶 LSQ 分解（脚本+数据）
   │      - 螺栓 TPS 子空间投影：逐角斜率方差移除率 26–38%
   │      - 推论：不可约地板 ≈ (1−覆盖率) × 凹陷能量
   ├─ 4.5 可达性界定：B*（disable_gravity 端到端优化）/ B_reachable /
   │      B_naive / B_comp 的定义、计算协议与语义
   ├─ 4.6 正则化设计：
   │      - 斜率空间锚定 λ_s‖∇(Φh)−∇(Φh*)‖²（= TPS 弯曲能 hᵀGh）
   │      - 软行程墙 vs tanh 有界参数化（解除动机：硬界阻碍地板逼近）
   │      - 闭式补偿初始化 h* = h_shape + h_comp
   └─ 4.7 太阳方向采样：真太阳正午对称设计；36/110/334 方向
          收敛性-过拟合权衡（E/W 镜 36dir 过拟合 +1.7 m²）

5. Case study and experiments (~10 页)
   ├─ 5.1 设置：镜场、RTX 4060、36dir 训练/110dir 复核协议
   ├─ 5.2 真实重力惩罚图谱（20 镜 A/B 表：naive/ideal 1.001–1.539；
   │      Pearson 0.913；Δ_envelope 近场显著远场≈0）
   ├─ 5.3 非均匀性的几何解释（倾角分布 ↔ 惩罚；North 免罚机制）
   ├─ 5.4 差距四层分解（300m NEWS 36/110dir：
   │      ideal → naive → comp → optimized → B*；各段归因）
   ├─ 5.5 正则化消融（8 组：anchor 扫描 × tanh on/off × soft wall ×
   │      bend；回收率 vs 物理保真度 Pareto）
   ├─ 5.6 代理保真度与误差预算（FEA 三路验证、光斑 NRMSE 0.017–0.018、
   │      相关 >0.996、S95 偏差 12–13% 的方向性讨论、误差预算总表）
   ├─ 5.7 与基线方法对比（CMA-ES/BayesOpt 无梯度；canting-only 仿射
   │      子空间基线；纯 LSQ 与纯闭式补偿）
   └─ 5.8 年度泛化（334/1556 方向前向评估，箱线图）

6. Discussion (~2 页)
   ├─ 6.1 设计指南：哪些镜位/纬度值得补偿；支撑布局（间距）才是
   │      地板的决定因素 → 给结构侧的量化建议
   ├─ 6.2 对"proxy 是否真在优化"的回答：闭式补偿 10–14% vs
   │      端到端回收率（Phase 3 数字）vs 不可约地板（62–74%）
   ├─ 6.3 局限：TPS 线性叠加（shape_corr 0.95–0.96）、单几何训练、
   │      热变形/风载未计、36dir 对 E/W 的过拟合
   └─ 6.4 扩展路径：全场规模化、POD/算子学习代理、与 aiming 优化联合

7. Conclusion (~0.5 页)

附录
   A. ANSYS APDL 自动化管线与坐标系约定
   B. TPS 系统构建细节与性质验证
   C. GPU dispatch 与性能数据
   D. 完整 20 镜数据表与收敛曲线
   E. 代码与数据开源
```

### 3.5 关键图表清单（新故事线必需）

| # | 图/表 | 素材 | 状态 |
|:---:|------|------|:---:|
| 1 | 重力惩罚全场热力图（naive/ideal 20 镜） | `analysis/real_gravity_penalty_table.md` | ✅ |
| 2 | 形变三分解堆叠图（仿射/二次/高阶 vs θ） | `analysis/gravity_compensability_report.md` | ✅ |
| 3 | 德令哈 300m NEWS 全年倾角分布（分位表/直方图） | 已算（110dir） | ✅ |
| 4 | **差距四层瀑布图**（ideal→naive→comp→opt→B\*） | Phase 2/3 跑批 | 🟡 在跑 |
| 5 | 正则化 Pareto（回收率 vs 行程/弯曲能） | Phase 3 八组 | 🟡 待跑 |
| 6 | Proxy vs FEA 形变/光斑对比（多角度） | 已有 + 抽查 | 🟡 需扩 |
| 7 | 误差预算总表 | 部分已有 | 🟡 整合 |
| 8 | CMA-ES/BayesOpt 对比曲线 | — | ❌ |
| 9 | canting-only 基线对比 | 可用现有框架实现 | ❌ |
| 10 | 年度泛化箱线图（334/1556dir） | — | ❌ |
| 11 | 收敛曲线 + 螺栓行程分布（4 镜） | history.csv | ✅ |
| 12 | （定位 B）全场年能量收益折算图 | — | ❌ |

---

## 4. 后续补充工作

### 4.1 在跑实验收尾（本周，GPU 排队中）

| 任务 | 内容 | 预计完成 |
|------|------|:---:|
| B\*@36 四镜 | North 跑透 + ESW 120-iter 封顶（cron 监控平台早停） | 2026-07-28 晚 |
| Phase 3 八组消融 | `_fw_tanh_a0/a1e3/a1e4/a1e5`、`_fw_nt_soft1e5`、`_fw_nt_a1e3_soft1e5/1e6`、`_fw_tanh_a1e3_b1e2`（300m NEWS, 36dir, 200iter） | ~3 天 GPU |
| Phase 4 | 差距三分解表（36+110dir）、FEA 抽查（`post_fea_validation.py`）、CLAUDE.md 更新 | 跑批后 1–2 天 |

### 4.2 投稿前必须新增的实验

**P0（任何定位都要）**：

| 任务 | 说明 | 工作量 |
|------|------|:---:|
| 110dir 终稿数字复核 | 36dir 对 E/W 镜过拟合 +1.7 m²（sundir 实验结论）；论文所有关键表至少 110dir 训练、334dir 验证 | 3–4 天 GPU |
| CMA-ES / BayesOpt 对比 | 35D 无梯度基线，Python wrapper 调 C++ 前向；证明梯度法样本效率 | 2–3 周 |
| canting-only 基线 | 只放开仿射子空间（等效 canting/瞄准类方法）做优化，直接量化"仿射自由度够不着凹陷"——可用现有框架低成本实现，且与 §4.4 理论互证 | 3–5 天 |
| 误差预算表整合 + 3 项补测 | SPP 外推、材料参数 ±5% 扰动、太阳形状敏感度 | 1–2 周 |
| 年度泛化评估 | 最优解 334/1556dir 纯前向箱线图 | 2 天 |

**P1（按定位取舍）**：

| 任务 | 服务定位 | 工作量 |
|------|------|:---:|
| 全场年能量收益折算（S95→截断效率→年发电量） | B（Applied Energy/ECM） | 2–3 周 |
| 多纬度/多站址重复（如敦煌 40.1°N、西班牙 PS10 37.4°N→对比） | A/B 泛化性加分 | 1 周 |
| 螺栓布局扫描（35 vs 36 vs 加密 48）→ 地板随支撑间距变化 | A 的设计指南强化 | 1–2 周 |
| E/S/W 镜 FEA 抽查（当前仅 North 有螺栓 FEA 对照） | 验证完整性 | 1–2 周 |

### 4.3 写作与工程化

| 任务 | 时间 |
|------|:---:|
| 精读 §5 五篇先例，写出逐条区分段落（Related Work 骨架） | 1 周 |
| Method 英文初稿（CLAUDE.md + 本文档 §3.4 素材已齐） | 2–3 周 |
| 图表制作（§3.5 清单，随实验进度） | 并行 |
| Experiments/Introduction/Discussion 初稿 | 3 周 |
| 内部修改 + 英文润色 + 导师两轮反馈 | 3 周 |
| 代码整理开源（AEI 鼓励 reproducibility；清理探针代码） | 1 周 |

### 4.4 总时间线

```
2026-08 上旬   Phase 3/4 收尾 + 110dir 复核启动
2026-08 下旬   CMA-ES 对比 + canting-only 基线 + 误差预算
2026-09        年度泛化 + （可选）全场能量折算；Related Work/Method 初稿
2026-10        全文初稿 + 图表定稿 + 导师反馈
2026-11        投稿 AEI（若完成能量折算可冲 Applied Energy）
2027 Q1–Q2     一审意见（AEI 投稿→录用均值 ~125 天）
```

---

## 5. 竞争性先例精读清单

投稿前必须精读并在 Related Work 中逐条区分（区分点已草拟）：

| 先例 | 出处 | 他们做的 | 我们的区分 |
|------|------|---------|-----------|
| Heliostat paraboloid canting via differentiable ray tracing | Solar Energy 2025 | 可微光追优化 canting（面板级倾角/对焦） | canting 只有**仿射自由度**；我们的分解理论证明重力主损伤在仿射≈0 的高阶凹陷——canting 类方法理论上够不着主损伤，且我们提供 canting-only 基线实验直接量化差距 |
| Heliostat aiming optimization via differentiable MCRT | Applied Energy 2025 | 瞄准点优化（2 DOF/镜） | 瞄准改不了面型；2 DOF vs 35 DOF；我们处理的是结构-光学耦合而非指向策略 |
| Inverse Deep Learning Raytracing (+ Sim-to-Real) | Solar Energy 2025 ×2 | 从光斑反推面型（逆问题/计量） | 诊断已装镜 vs 出厂前设计优化；变量是表面法向场 vs 机械螺栓行程 |
| Pargmann et al. | Nature Comms 2024 | 可微光追做 in-situ 计量 | 同上；且我们有力学代理连接螺栓→面型→光学 |
| Fast-NCM（学长，投 Solar Energy） | 预印本 2026-03 | MLP 预测解析光斑参数，全场仿真 16 ms | 互补不竞争：前向仿真加速；其 erf 闭式可微渲染思路可引为我们 H3 卷积修正的佐证；其输入只接受标量 σ_S，无法处理面型空间结构（正是我们工作的必要性） |

---

## 6. 参考文献

**新增（本轮调研核实）**：
1. Differentiable automatic structural optimization using graph deep learning. *Advanced Engineering Informatics*, 2024.
2. A novel heliostat aiming optimization framework via differentiable Monte Carlo ray tracing for solar power tower. *Applied Energy*, 2025.
3. The optimization of heliostat paraboloid canting via differentiable ray tracing. *Solar Energy*, 2025.
4. Inverse Deep Learning Raytracing for heliostat surface prediction. *Solar Energy*, 2025.
5. Scalable heliostat surface predictions from focal spots: Sim-to-Real transfer of inverse Deep Learning Raytracing. *Solar Energy*, 2025.
6. Digital twin of wind farms via physics-informed deep learning. *Energy Conversion and Management*, 2023.
7. 林瑞剑 et al. Real-time Radiative Flux Density Distribution Simulation via Data-Driven Neural Convolution Model (Fast-NCM). 预印本, 2026.

**保留（旧版，图形学方向，TVCG 版需要）**：
8. Pargmann et al. Automatic heliostat learning for in situ CSP metrology with differentiable ray tracing. *Nature Communications* 15:6997, 2024.
9. Zhou et al. Computational Caustic Design for Surface Light Source. *IEEE TVCG* 32(2), 2026.
10. Sun, Deng, Zhang. Differentiable design of freeform optics. *ACM TOG* 44(3), 2025.
11. Fan et al. Efficient Specular Glints Rendering With Differentiable Regularization. *IEEE TVCG* 29(6), 2023.
12. Shi et al. SurroFlow. *IEEE TVCG* 31(1), 2025.

**方法学**：
13. Karniadakis et al. Physics-informed machine learning. *Nature Reviews Physics* 3:422–440, 2021.
14. Nimier-David et al. Mitsuba 2/3: differentiable rendering. *ACM TOG*, 2019/2022.
15. Hansen. The CMA Evolution Strategy: A Tutorial. arXiv:1604.00772, 2016.

---

> **与旧版文档的关系**：旧版（2026-07-23）中仍然有效的素材——GPU 管线优化清单、sundir 采样结论、FEA/光斑验证数据、差距 1/2/3（对比实验、消融、误差预算）——已整合进本文 §3–§4，不再单独维护。旧版 git 历史可查。
