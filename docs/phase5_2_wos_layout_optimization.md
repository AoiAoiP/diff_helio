# Phase 5.2 设计方案：可微 WoS 螺栓布局端到端优化

> 状态：设计评审稿 v3（G0 否决粗插值；G1 否决 WoS 原型；**m06 加密验证：重力场插值最终否决、φ 族通过**——Track B 解析降阶模型升为主力，见 §6）
> 前置文档：`phase5_layout_optimization.md`（布局扫描）、`gravity_compensation_experiment.md`（Phase 0–4 主报告）、`material_steel_feasibility.md`（M1）
> 参考文献：`ref/2024_Solving Inverse PDE Problems using Grid-Free MonteCarlo Estimators.pdf`、`ref/2025_State of the Art in Grid-Free Monte Carlo Methods for Partial.pdf`

## 0. 问题定义

Phase 5.0/5.1 已确立：重力补偿天花板由螺栓布局决定；7×5 布局存在悬挑-跨距守恒律，最优 margin≈4%。但扫描是**离散、穷举式**的——每个布局点都要一批 ANSYS FEA（35 探针 + 20 角度重力），无法覆盖连续布局空间，更无法进入优化闭环。

**Phase 5.2 目标**：固定螺栓数（35），把螺栓**位置**变成端到端可微的优化变量，让优化器自己学出 margin（乃至逐栓位置）。判据：300m NEWS @110dir 光学端到端，margin 从初值 0.08 收敛到 3–5% 区间（与 5.1 机械代理量预测互验）。

**核心障碍**：面型模型为

```
w(x) = w_0(x, θ; π) + Σ_b h_b · φ_b(x; π)
```

重力场 w_0 与影响函数 φ_b 都是布局 π 的函数，当前依赖 ANSYS 逐布局预计算。渲染器本身与布局完全解耦（shader 中无任何布局参数，bolt 位置仅以预计算场的形式进入，已 grep 确认）——唯一需要解决的是**场如何随布局变化且可微**。

## 1. 路线排除：跨布局 ANSYS 插值（G0 实验，已完成）

最便宜的方案是在 margin 网格上预计算若干套 ANSYS 场、渲染端线性混合。G0 用现有数据做了零成本证伪：m02+m08 线性插值预测 m04（7×5，4 个共有角度 10/30/58/80°，3-plane 重力场），脚本 `scripts/g0_layout_interp_validation.py`。

| 预测方式 | cos_sim（均值） | relL2（均值） | 10° cos | 80° cos |
|---|---|---|---|---|
| m02+m08 插值 → m04 | 0.909 | 0.42 | 0.949 | 0.818 |
| m08 锚点直接使用 | 0.387 | 1.27 | 0.497 | 0.178 |
| m02 锚点直接使用 | 0.894 | 0.58 | 0.944 | 0.791 |

两个关键观察：

1. **绝对精度不足**。插值虽远优于锚点直用，但 cos≈0.91 / relL2≈0.42 距 proxy 准入标准（M1 材料缩放实验的 cos≥0.996）差一个量级，且在最需要分辨率的 80° 附近最差。
2. **振幅随 margin 非单调**（w-plane RMS：m02=3.81e-3, m04=3.36e-3, m08=3.64e-3 @10°，U 形）。这正是 5.1 守恒律（margin↓→悬挑↓但跨距↑）在总体量上的体现。**粗网格插值会抹掉极小值位置**——而它恰是布局优化的目标——对梯度法是致命的。

结论：粗网格 ANSYS 插值**否决**为主力路线（保留为兜底/验证基准）。加密网格（每 1–2% margin 一层，4–7 批 FEA）可缓解但治标不治本，且 margin 之外的布局维度（逐栓位置）依然无法覆盖。→ 转向 WoS 在线求解。

### 1.1 Track A1 加密验证（m06，2026-07-30 台式机执行）——插值路线最终判决

为检验"加密到 Δ≈0.02 后插值是否收敛"，台式机生成了 m06 全套场（35 探针 + 20 角度，`margin06_data_2026-07-30/`），用 hold-out 方式验证 m04+m08→m06：

| 场 | 方法 | cos_sim | relL2 | 判决 |
|---|---|---|---|---|
| influence_phi | 线性中点 | **0.9998**（min 0.9996） | 0.020 | **通过** |
| influence_phi_u/v | 线性中点 | 0.9990 | 0.044 | 通过 |
| influence_kxx/kxz/kzz | 线性中点 | 0.983–0.990 | 0.13–0.17 | 勉强（二阶场，噪声大；且 m06 真值自身 TPS 自检 3 栓 <0.95，含噪声下限） |
| 重力场 @10° | 线性中点 | 0.953 | 0.314 | **否决** |
| 重力场 20 角均值 | 线性中点 | 0.918 | 0.43 | **否决**（80° 最差 0.85） |
| 重力场 @10–30° | 二次（含 m02） | 0.968–0.976 | 0.26 | 仍不达标 |

误差成分分解（10–80° 六个代表角）：

- **最优权重基**（m06 投影到 span{m04,m08}）：cos 0.90–0.98 ⇒ 即使振幅权重拟合最优也到不了 0.99，且存在 2–10% 跨子空间新结构；
- **配准插值**（按栓排位置做分段线性 warp 消除节点线移位后再插值）：cos 0.88–0.97 ⇒ 移位效应存在，但只能收回一部分误差。

**最终判决：重力场的布局依赖 = 非线性振幅重分配 + 节点线空间移位 + 少量新模态，任何插值形式在可负担的网格密度下都压不进 1%——Track A 对重力场死刑（φ 族保留插值方案）。** 加密 m03/m05/m07 的台式机批次取消。

关键不对称性：φ（补偿影响函数）是**局部**响应，对全局约束拓扑不敏感，插值 cos≥0.9998；w_0（重力场）是**全局**响应，节点线由栓排位置直接决定，布局一变全场重排。后续架构按此不对称性分工（§3）。

## 2. 文献基础与定位

精读 ref/ 两篇 + 补充检索（2026-07-30，OpenAlex/出版社页/GitHub 交叉核实）：

**直接技术先例**
- Yilmazer, Vicini, Jakob 2024（TOG 43(6), SIGGRAPH Asia）：逆问题 WoS 框架。导数满足**同核新源的 Fredholm 方程**；Path Replay Backpropagation（PRB）实现线性时间 reverse-mode；weight windowing 控制分支游走的方差；§6.3 演示了**内部 Dirichlet 物体位置**的优化（一阶展开 u≈V+d·∂n u + 固定偏移 t 处估法向导数）——与我们的点支撑位置优化数学同构。
- Miller, Sawhney, Crane, Gkioulekas 2024（TOG 43(6)，Differential WoS）：前向可微 WoS，**对所有参数联合估计导数，代价不随参数量增长**，含域几何参数。
- Yu, Wu, Zhou, Zhao 2024（SIGGRAPH'24，diff-wos）：可微 Poisson WoS；处理球半径依赖几何导致的采样分布可微性校正。
- Yu, Sawhney, Miller, Wu, Zhao 2025（TOG，Robust Derivative WoSt）：∇u 估计用导数调和性重写 BIE，解决近边界高方差/偏差——我们估计板面 slope ∇w 必须用此法而非朴素 FD。
- Qi, Seyb, Bitterli, Jarosz 2022（CGF）：bidirectional WoS，为**稀疏源项**（如 Dirac 点源）降方差。
- Himmler & Günther 2026（TOG）：图形学首个双调和 MC 求解器，Δ²u 拆为 Laplace+Poisson 两个二阶问题——与现有 `shaders/wos_influence.slang` 的双层耦合结构同构，互为合法性印证。
- Sabelfeld 体系（Spherical Means for PDEs, De Gruyter；Sabelfeld & Shkarupa 2003）：polyharmonic 球面平均/体积 Green 函数的严格性背书。

**文献空白（= 我们的贡献点）**
1. 内部点约束/点支撑（域内 Dirac 型 Dirichlet）的 WoS 处理与可微化——无人做过；
2. 含分布源项（D∇⁴w=q）的双调和 WoS——无发表实现；
3. 点支撑 Kirchhoff 板弯曲的 Monte Carlo 求解器——完全空白；
4. grid-free MC 结构求解器嵌入可微渲染做布局优化——空白。

**工程参照**：Zombie（rohan-sawhney/zombie，C++ header-only）；**WoSX（nv-tlabs/wosx，NVIDIA 官方 Slang/CUDA GPU 实现，与我们 Slang 管线同栈，但只支持二阶 PDE）**；differential_wos（baileymiller）；diff-wos（zihay）。

## 3. 总体架构：布局场提供器（layout field provider）

渲染器只消费同形的场：`gravity bins（20 角度 × 3-plane 32×32）+ influence_phi{,_u,_v} + influence_kxx/kxz/kzz`。定义抽象层 **layout field provider**：输入布局参数 π、输出上述场及其对 π 的导数。m06 验证后按 φ/重力不对称性分工：

- **φ 族（含曲率场）**：布局依赖弱且光滑（m06 hold-out cos≥0.9998）——**v1 直接固定用 m08 一套**（最省事，误差 ~2% 与 TPS 自检噪声同量级）；v2 若需更精可用相邻层线性插值。
- **w_0 重力场**：插值已否决（§1.1）。候选提供器：
  - **(B) 解析降阶模型（主力）**：梁-板条分解，栓排位置作为显式运动学参数进入模型——节点线移位（插值失败的成分之一）由构造天然表达；振幅重分配由守恒律 a³ 标度表达；少量系数用 m02/m04/m08 标定、**m06 作 hold-out 验证**。
  - **(C) 自由边 WoS（研究线）**：直接解 BVP，全部成分天然正确，但高风险（§6 Track C）。
  - **混合锚点**保留为 B/C 的修正层：w_0 = w_ANSYS(π₀) + [w_model(π) − w_model(π₀)]，CRN/公共基底下差分更稳。

**设计决策记录（2026-07-30，否决"WoS-φ + bins-重力"配置）**：曾评估用 WoS 仅替换 TPS 影响函数、重力仍走 bins 的方案，否决。理由：(1) φ 是布局弱依赖项，插值 cos 已达 0.9998、固定 m08 单套误差 ~2%，WoS 替换只换来小精度升级，却要付出自由边 BC（文献空白）的研究级成本；(2) 重力若固定 m08 bins，目标场不随布局变化，优化器只剩"补偿率"一个杠杆——而 5.1 双倍收益证伪已表明补偿率是弱杠杆（19–23% 天花板且随加密下降），布局收益的大头来自重力场本身缩小，固定重力等于把主收益从目标函数删除；(3) 重力 bins 跨布局插值已被 §1.1 否决。WoS-φ 的正确定位是 Track C 的中途里程碑（齐次子问题），不是主力架构。

π 的参数化分两版：
- **v1（margin 模式）**：π=(margin_x, margin_z)，2 维，栓位 p_b(π) 线性；
- **v2（自由模式）**：每栓有界偏移，p_b = p_b⁰ + δ_b，|δ_b|≤半间距（tanh 重参数化），保序防交叉，70 维。

## 4. WoS 求解器设计

### 4.1 PDE 模型

Kirchhoff 板：D∇⁴w = q(x)，矩形域，自由边（M_n=0，V_n=0），点支撑 w(p_b)=h_b。算子分裂为两个二阶问题：ΔM = −q，−DΔw = M（与 Himmler-Günther 2026 同构）。两个子问题：

- **φ_b**：q=0，w(p_b)=1，其余栓 w=0 → 影响函数（= 点约束 Green 函数）；
- **w_0**：q=ρgt·cosθ 均布，全部栓 w=0 → 重力变形。

### 4.2 现有实现审计（shaders/wos_influence.slang）

现状：双层耦合游走（moment 层边界反射、deflection 层球内 Green 体积采样 M·r²/4）、nearBolt ε-shell（半径 kEps·3=1.5cm）吸收、N_WALKS=5000、256×192 网格、N_BOLTS=35 硬编码、CPU 端 FD 求 φ_u/φ_v、CLI `--compute-wos` 直通。已修复一个致命 bug：pipeline 创建时 pName 误写为 `computeWoSInfluence`（SPV 入口实际为 `main`），导致该模式在此驱动上从未运行成功——旁证 WoS 路线自放弃后无人维护。

**G1 裁决结果（2026-07-30，决定性失败）**：修复后首轮运行，WoS φ vs ANSYS φ @m08，逐栓 cos_sim 均值 **0.039**（35 栓中 33 栓为 0，仅 bolt 0/1 有 0.66/0.69 残余信号），幅值比 ~1/1000；中心栓 bolt17 的 WoS 场**恒等于零**。失败是双重的、各自独立的：

1. **BVP 错误（结构性）**：`walkDeflection` 在 r<ε 时 `return w`（零贡献终止）⇒ 等价于**四边挠度恒零**——固支/简支边，而非物理自由边。悬挑变形（本问题的全部核心）被构造性抹除。moment 层的"反射"同样与自由边 M_n=0（应为 Dirichlet 终止）不符。
2. **估计器饥饿（统计性）**：点支撑靠 1.5cm 半径球壳吸收实现，在 12.84×9.45m 板面上随机游走 200 步内命中微壳的概率 ~O(1e-3 以下)；5000 walks 对多数栓零命中 ⇒ φ≡0。即使 BVP 修正，该估计器在此游走预算下也无法工作——必须改用 Dirac/Green 函数形式（确定性源贡献）+ bidirectional 采样（Qi 2022）。

这一结果也回溯性地解释了 WoS 路线当初为何被放弃：产出的近零垃圾场被误读为"WoS 不行"，而未诊断到估计器与边界处理。

### 4.3 点支撑的形式化

把 φ_b 视作 D∇⁴φ_b = δ(x−p_b) 的 Green 函数估计：Dirac 源项在 WoS 中是确定性贡献（等价于渲染中的 next event estimation），配合 Qi 2022 bidirectional 降方差。相比 ε-shell 吸收的好处：无壳半径超参数；**对 p_b 的依赖纯 pathwise 光滑**（导数无间断修正项，Yilmazer §4 的连续情形直接适用）。现有实现在 moment 层的 nearBolt 积累已具 Dirac 雏形，G1 将检验其一致性，再决定是否重写为显式 Green 函数估计器。

### 4.4 重力源项与角度依赖（关键设计决策）

源项扩展本身是标准做法：内层 Poisson 每步在球内按 Green 函数比例采一点，累计 q(y)·|G|（Yilmazer §3）。但有一个物理限制必须正视：**纯板均匀法向载荷给出 w_0(θ) = cosθ·w_0(0)，单调余弦律**；而 ANSYS 实测的角依赖不是余弦律（M1 实验观察到 mean_w 在 46° 附近变号，α(θ) 非常数）——整机姿态、面内分量与支撑结构效应超出了 Kirchhoff 板模型。

因此决策为：**w_0 的角度依赖结构由 ANSYS 锚点承担（提供器 (iii) 的第一项），WoS 只负责布局差分项**。该决策的对错由 G3 直接检验：WoS 差分 w(m04)−w(m08) 与 ANSYS 真实差分逐角度对比（10/30/58/80° 共有数据）。若 WoS 差分本身角依赖失真，退化为方案 (iii')：ANSYS 锚 + WoS 仅提供 φ（布局差分只作用于补偿项）。

### 4.5 布局梯度估计

目标量：dL/dπ = Σ_grid (∂L/∂w) · (∂w/∂π)，其中 ∂w/∂π = ∂w_0/∂π + Σ_b h_b ∂φ_b/∂π。

- **导数场**：∂φ_b/∂p_k = −∇_{源点}G（算子自伴 ⇒ 等于对求值点的梯度）——用导数 WoS（Miller 2024a）/ WoSt 导数估计器（Yu 2025）在栓点处直接估计 ∇φ_b、∇w_0，不做数值差分。
- **收缩技巧（决定性成本控制）**：不显式形成 ∂w/∂π 全场，而是按 |∂L/∂w_grid| 重要性采样 1k–8k 个网格点，只在这些点上跑导数游走，直接收缩出标量 dL/dπ（伴随 Jᵀv，与现有 bolt_backward 对栓高梯度的归约同构）。
- **CRN**：同一迭代内所有 π 分量共享 PRNG 种子族 ⇒ 路径族一致，梯度方差塌缩（PRB rewind 的 GPU 等价）。
- **反向实现**：新增一个收缩 kernel（现有 bolt_backward 的姊妹 kernel）；π 的 Adam 在 CPU 侧（v1 仅 2 参数）。Slang `bwd_diff` 已在生产 shader 中使用（backward.slang、bolt_backward.slang），PRB 的局部 AD 块可直接落地。

### 4.6 与渲染器的接口

提供器输出与现 ANSYS bins **同形**（32×32×3-plane bins + φ/φ_u/φ_v + kxx/kxz/kzz；曲率场 k** 由 φ 二阶导或 FD 得到），渲染前向零改动；init 文件（35 栓高 LSQ 值）与布局位置无关，直接复用。

## 5. 验证门（任何一门不过则停在该门修复，不进入下一门）

| 门 | 内容 | 数据/判据 | 状态 |
|---|---|---|---|
| G0 | 跨布局粗插值可行性 | m02+m08→m04，cos/relL2 | **已完成：否决（§1）** |
| G1 | WoS φ vs ANSYS φ @m08 | 逐栓 cos_sim、PV 比；目标 cos≥0.95 | **已完成：失败（cos 0.039），双重诊断见 §4.2** |
| G1.5 | 加密插值验证（Track A1） | m04+m08→m06 hold-out | **已完成：φ 族通过（0.9998）、重力否决（0.918），§1.1** |
| G2 | 重力场提供器保真 | Track B 模型 vs ANSYS（m06 hold-out + m02 4 角）：3-plane cos_sim，目标 cos≥0.99 @10–30°、≥0.98 全角均值 | 待 Track B 实现 |
| G3 | 布局增量保真 | 提供器差分(m04−m08) vs ANSYS 真实差分，逐角度 | 待 Track B（与 G2 共用数据） |
| G4 | 梯度正确性 | margin 有限差分 vs 解析/估计器梯度，相对差<10% | 待收缩 kernel |
| G5 | 端到端收敛 | 300m NEWS @110dir，margin 0.08→3–5%（5.1 预测区间） | 最终验收 |

## 6. 分阶段实施：修订版三线计划（m06 验证后）

**Track B（主力，零新 FEA，笔记本本地）**：解析降阶重力场模型。
- B1（~1 天）：模型形式——z 向 5 栓排 + 双悬挑的连续梁/板条柱面弯曲叠加，x 向同构，交叉耦合小项；栓排位置显式参数化（margin/逐栓位置 ⇒ 节点线运动学正确）；振幅系数为 θ 的光滑函数（用 ANSYS 20 角拟合）。
- B2（~0.5 天）：标定——m02/m04/m08 三层数据拟合少量自由系数；**m06 hold-out 验证（G2/G3 判据同上表）**。
- B3（~1 天）：提供器接入渲染器（输出同形 bins）+ 解析导数 + 收缩梯度 kernel + margin Adam；G4。
- B4：G5 端到端（300m NEWS @110dir 四镜）。

**Track A（缩减保留）**：φ 族固定 m08 单套（v1）——零工作量，误差可接受；无需任何新批次。

**Track C（研究线，有界里程碑，失败不影响 B）**：自由边 WoS 重写。修复清单：(i) moment 层改 Dirichlet-0 终止；(ii) 点支撑改 Dirac/Green 函数估计器 + bidirectional 采样（解决估计器饥饿）；(iii) 自由边 V_n=0 的处理——文献空白，候选 Himmler-Günther 式逆问题迭代；(iv) 重力源项（内层 Poisson 球内采样）；(v) 导数估计（Miller 2024a / Yu 2025）。**里程碑 M（2–3 天）：修正版 G1 cos≥0.95；达不到即放弃**，成果转入论文叙事（"为何不用在线 MC 求解器"成为有据可查的设计决策）。

台式机当前**无待办批次**（m03/m05/m07 已取消）；仅在 G5 最优布局需要 FEA 复核时介入（复用 Phase 4 抽查协议）。

## 7. 风险与缓解

- **R1 自由边 BC 无文献先例**：WoS 不需匹配第一性原理，只需匹配 ANSYS（Phase 4 确立的真理标准）。用 m08 标定自由参数（壳半径、边界处理系数），m04 数据检验标定的跨布局迁移性；最坏情况退回提供器 (i) 加密网格（4–7 批 FEA）。
- **R2 梯度噪声拖慢 Adam**：CRN + 场滑动平均 + 收缩采样；必要时 boundary value caching（Miller 2023）/ mean value caching（Bakbouk 2023）。
- **R3 单迭代成本**：全量场重估 ~2 min（5000 walks×49k px×35 栓）不可接受；收缩采样 + 懒惰更新（每 K 步重估场、期间冻结 π）使每迭代增量 <<1s。
- **R4 点支撑理想化**：真实栓有有限垫片；ε-shell/Dirac 核半径可解释为垫片半径，属物理参数而非数值 trick。
- **R5 板模型角依赖失真**：见 §4.4 决策与 G3 检验；兜底为 (iii')（WoS 只管 φ）。

## 8. 论文定位

本方案正面回应"proxy 未起真正优化作用"的批评：物理模型从"梯度链接"升级为**结构优化变量的载体**。贡献陈述：(1) 首个嵌入可微渲染的 grid-free Monte Carlo 板弯曲求解器；(2) 内部点支撑约束的可微 WoS（文献空白）；(3) 含分布源项的双调和 WoS 实现；(4) 布局-面型联合端到端优化框架，并在定日镜场场景闭环验证（与离散扫描的守恒律预测互证）。适配 TVCG / AEI 的"AI+物理"叙事。

## 附录 A：现有 WoS 相关文件地图

- `shaders/wos_influence.slang` / `wos_common.slang`：双层耦合 WoS（φ 原型，硬编码 35 栓/5000 walks/256×192）
- `shaders/computeWoSInfluence.spv`：已编译模块（入口名 `main`）
- `src/pipeline.cpp:1109 computeWoSInfluence()`：离线生成器，CLI `--compute-wos --wos-output <dir>`
- `scripts/g0_layout_interp_validation.py`：G0 插值证伪实验
- `scripts/g1_wos_vs_ansys_influence.py`：G1 对比（WoS 256×192 块平均→32×32，逐栓 cos_sim/PV 比）

## 附录 B：G1 实验记录（2026-07-30）

- 运行：`bezier_opt --config configs/_fw_tanh_a0_110.json --compute-wos --wos-output data_wos_g1`（RTX 4060 Laptop，GPU 27s，5000 walks/px，256×192×35）；日志 `logs/_g1_wos_influence.log`。
- 对比：`python scripts/g1_wos_vs_ansys_influence.py data_wos_g1 data_proxy`（WoS 块平均 256×192→32×32，逐栓 cos_sim/PV 比）。
- 结果：cos_sim 均值 0.039（33/35 栓为 0；bolt0/1 = 0.66/0.69）；WoS 幅值范围 [0, 0.0114] vs ANSYS [-0.266, 1.405]；中心栓场恒零；最优交叉匹配（35×35 全矩阵）均值 0.015，排除索引/轴映射错误可能。
- 裁决：**失败**。诊断两条（BVP 错误 + 估计器饥饿）见 §4.2。产物 `data_wos_g1/` 保留作 Track C 重写后的回归基准。
- 构建备注：本机 msys2 shell 中 `cmake --build` 因 VS 生成器检测失败不可用；用 `MSBuild.exe build/bezier_opt.sln -p:Configuration=Release -m -t:bezier_opt`（MSBuild 位于 `C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\`）。
