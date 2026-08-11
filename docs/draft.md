# 论文草稿 — 重力作用下的定日镜面型优化（中文版）

> **基本大纲**：
> 文章主要叙事：当前CSP领域的可微优化仅限于理想曲面，没有工程参考价值——设计了嵌入物理信息的可微渲染优化方法——参考重力形变特性，使用优化器获得最优面型
> §1 引言设计：说明定日镜的可微优化的局限性，以及传统的将诸多误差因素一股脑编码为斜率误差$\sigma$的局限性。
> §2 相关工作设计：定位，说明与五条脉络的交叉与区分
> §3 系统模型设计：说明当前的物理系统与目标
> §4 方法框架设计：说明工具——包括可微渲染、TPS代理、梯度链、正则化
> §5 理论分析设计：说明重力的形变分析与优化器如何进行补偿
> §6 实验结果说明：
> §7 结果讨论：
> 目标投递期刊：Computational Visual Media、TVCG

**状态说明（非正文）**：
- 2026.8.10 ： 设计大纲
- 参考文献在`ref/`目录下

---

**题目**

面向重力形变的物理信息可微定日镜面型优化：界限、可补偿性与镜位设计规则

*（英文题备用：Physics-informed differentiable optimization of heliostat surfaces against gravity-induced deformation: bounds, compensability, and field-position design rules）*

**摘要**



**关键词**：聚光太阳能热发电；定日镜；可微光线追踪；物理信息优化；薄板样条；重力补偿；结构优化；

---

## 1. 引言
在塔式聚光型太阳能发电系统中，定日镜的质量发挥着举足轻重的作用。
### 1.1 定日镜光学质量是CSP聚光效率的瓶颈
- 塔式 CSP 系统中，定日镜场贡献了约 50% 的资本成本和主要光学损失
- 面型误差（与跟踪误差、斜率误差并列）是聚光损失的首要来源
- 传统做法：将外力造成的结构形变、制造公差、安装误差统一编码为标量斜率误差 σ_S → 无法区分可补偿与不可补偿分量，在仿真中图了方便，但不利于具体的优化。

### 1.2 重力弯沉：一个被结构侧与光学侧同时忽视的耦合问题
- 结构侧：FEA 能算形变，但结果从不回灌到光学面型规格中，止于刚度校核
- 光学侧：canting/瞄准调整只动仿射自由度（面板倾角），够不着高阶凹陷
- 仿真侧：可微光追已用于瞄准优化 [1] 和 canting [2]，但从未用于面型设计
- 关键张力：重力弯沉在 300m 典型距离上产生的斜率误差（2.3–8.5 mrad 反射×2 后）与 Buie 太阳宽度（2.2mrad）同量级——一旦被正确建模，将从"光学隐身"变为"光学主导项"

### 1.3 本文试图探讨的三个问题
- RQ1（惩罚有多大？）：真实重力弯沉对不同镜位/距离的定日镜年均光斑面积影响多大？
- RQ2（物理上能补多少？）：给定 35 螺栓支撑布局，面型调节的物理上限在哪里？不可约地板的成因是什么？
- RQ3（如何正则化逼近？）：在承认地板存在的前提下，如何设计正则化策略使优化器安全逼近地板而不失真？

### 1.4 文章主要贡献
1. 首个穿越力学-光学双域的端到端可微面型优化框架（？需要进一步检索）
2. 重力形变的可补偿性理论（三分解 + 子空间投影）
3. 可达性界定框架（B*/B_reachable/B_naive/B_comp 四层差距分解。批注：这四个指标需要重命名，太不直观了）
4. 镜位-纬度倾角分布模型 → 设计指南
5. 面向地板逼近的正则化设计
---

## 2. 相关工作

本工作位于五条研究脉络的交汇处——定日镜能流仿真、定日镜面型调整、CSP 中的可微光线追踪、耦合结构-光学优化、以及工程设计中的物理信息优化。以下逐节综述并定位本文贡献；表 1 给出与最接近工作的对比。

### 2.1 定日镜能流仿真：从光线追踪到学习代理

*思路*：  MCRT (SolTrace/Tonatiuh) → 解析卷积 (HFLCAL/UNIZAR) → 神经代理 (Fast-NCM)。点明：代理仅接受标量σ_S这一宏观统计量，无法处理空间结构化形变。我们的渲染器居中——保留全物理但面向可微性工程化。

吸热器能流密度预测是定日镜设计的计算基石。蒙特卡洛光线追踪（MCRT）是精度基准，由 SolTrace [11]、Tonatiuh [12] 等成熟工具及大量自研代码实现；但其开销若不针对 GPU 深度工程化，便无法承受优化循环内的反复调用。另一端，解析卷积模型（HFLCAL [13]、UNIZAR [14] 及其变体）将光斑近似为高斯误差在投影镜面上的卷积，速度快数个量级，但前提假设是误差统计均匀的理想表面。近期的混合趋势是用学习器预测*解析*光斑参数：Lin 等人的 Fast-NCM [6] 训练一个紧凑 MLP，从九个场景标量（含标量高斯斜率误差 σ_S）回归"剪切椭圆高斯 ⊗ 投影矩形"光斑模型的八个参数，光斑由误差函数闭式渲染，可在 16 ms 内仿真 6282 面镜的全场。这类代理对表面质量的输入刻画只有一个*标量*；重力弯沉与螺栓调节产生的空间结构化、非高斯形变——正是本文的优化对象——不在其输入域内。因此我们的渲染器刻意居于中间位置：保留完整 MCRT 物理（Buie 日轮、双层玻璃折射、统计斜率误差），但面向可微性与迭代速度做工程化，而非以代理取而代之——使任意空间分辨率的表面高度场始终是一等输入。

### 2.2 定日镜面型调整：canting、对焦与结构校核

调整定日镜光学面型在历史上是一种机械、离线的过程。canting——面板或子镜的预置角偏移——与焦距选择在装配或调试阶段确定，依据是经验法则、偏折测量或逐镜人工整定 [19]。重力、风载与热载下的结构形变由 FEA 分析 [20]，但几乎只作为刚度校核，其结果从不回灌到光学面型规格中。近年来，基于优化的 canting 随可微渲染复兴：[2] 用可微光线追踪优化定日镜抛物面 canting。这条路线与本文共享渲染器技术，但设计变量本质不同：canting 调整的是*面板级刚体*（仿射）自由度，而本文调整 35 个连续支撑螺栓行程，在高阶子空间内重塑面型。这一区别并非细枝末节——本文的分解分析（第 4.4 节）表明，重力弯沉的仿射成分被支撑结构自身钉死为零，因此仅有仿射自由度的调整在原理上无法触及主导形变模态；第 5.7 节还设置了 canting 等效基线，从实验上量化这一差距。瞄准策略优化（包括近期镜场尺度的可微 MCRT 形式化 [1]）同样作用于指向自由度（每镜 2 个），无法修正面型误差；它与本文互补，面型-瞄准联合优化是我们在第 6 节展望的自然延伸。

### 2.3 CSP 中的可微光线追踪：瞄准、canting 与逆问题计量

可微渲染在计算机图形学中已趋成熟 [16–18]，并正在进入聚光太阳能领域。除上述优化类工作外，Pargmann 等人 [3] 将可微光线追踪用于定日镜*原位*计量——从标定图像反推已安装镜的面型误差；[4, 5] 提出逆深度学习光线追踪，从焦斑预测定日镜表面并完成 sim-to-real 迁移研究。这些工作验证了 DMCRT 梯度在 CSP 光学中行为良好且有用，但它们求解的是已有硬件上的*逆向诊断*问题。本文的问题是出厂阶段的正向*设计*问题：优化变量是机械量（螺栓行程），扰动是自带 FEA 模型的结构载荷（重力），梯度链因此必须穿越力学与光学两个物理域——这是上述工作均未尝试的。我们同时指出，使本文正向-反向闭环可行的 GPU 工程（S95 分位数的全设备协作二分、稀疏像素剔除、单提交命令合批）一脉相承自图形学文献，详见第 4.1 节与附录 C。

### 2.4 工程设计中的物理信息机器学习与可微仿真

将物理嵌入学习与优化循环已成为一种独立方法论（Karniadakis 等人的综述 [7]），在本刊版面亦已常见——如图深度学习的可微自动结构优化 [8]、起重机负载摆动预测的物理信息网络 [9]、风电场物理信息数字孪生 [10]。主流范式有二：训练神经代理以替代仿真器；或构建暴露物理模型精确梯度的可微仿真器。我们的代理刻意*既不是*学习代理、*也不是*全可微 FEA：TPS 影响模型是一种物理推导、数据轻量的降阶模型——每种镜面几何只需由单位载荷 FEA 解构建一次，具备保证叠加精确性的单位分解性质，并对完整 NLGEOM 解验证通过（形状相关 0.95–0.96）。这一选择以微小、可量化的保真度损失，换取了解析、GPU 常驻、且便宜到足以嵌入每次蒙特卡洛迭代的梯度通路——正是这一性质使端到端光-结构优化成为可能；其误差预算在第 5.6 节量化。在精神上与本文最接近的是 [8]：两者都使结构优化可微；区别在于本文的目标是光学的（全年辐射光斑面积），设计变量耦合两个物理域，且分析包含了显式的可达性界限，把"优化能修复什么"与"优化不能修复什么"分开。

### 2.5 耦合结构-光学优化（Coupled structural-optical optimization）

在定日镜工程中，连接结构设计与光学评估的努力并非始于本文。如前所述，颜健等人 [21, 22] 的螺栓参数 FEA 扫描直接以斜率误差为输出指标，将结构参数（间距 d、数量 N）映射为光学精度——这项工作在概念上与本文的 margin 优化最为接近，均将支撑布局视为光学表现的设计杠杆。Yang 等人 [23] 的伞形定日镜耦合分析（ANSYS 结构模型 → TracePro 光追）以正交试验法同时优化多个结构尺寸，在减重 31.7% 的同时将斜率误差增幅控制在 0.4 mrad 以内。Thalange 等人 [24] 以参数化结构模型驱动自研光追代码，将三脚架定日镜的成本和光学误差联合优化。近期的多物理场工作进一步将 CFD 风压场纳入 FEA→光追管线 [25]，量化风致变形对聚光效率的影响（效率损失 10–24%）。

这些工作共同确立了一个关键前提——结构设计参数的连续变化可以产生连续的光学性能改善——并验证了"FEA→光学评估"这一耦合方向的可行性。然而，它们的方法共性也划定了三方面边界，这些边界恰是本文试图突破的。**第一，优化粒度**：所有上述工作均为参数枚举或群体智能搜索（遗传算法、正交试验），每一步评估需要一次完整 FEA + 一次完整光追；这意味着参数空间的探索粒度受限于枚举步长，且无法利用梯度信息引导搜索方向。**第二，评估指标的代理层级**：离线耦合管线中的光学评估使用的是 FEA 网格变形直接导出的斜率误差 RMS，或经简化的光斑参数——而非全物理蒙特卡洛光线追踪下的 S95 光斑面积；后者对高阶形变分量、太阳形状卷积和双折射玻璃的敏感性是斜率误差代理无法捕捉的。**第三，分析的深度**：参数扫描可以回答"哪个参数组合更好"，但无法回答"给定布局下任何螺栓调节的物理上限在哪里"——后者需要对梯度可达子空间的结构性分析（§4.4–4.5），而这一分析只有端到端可微框架才能提供。

**表 1** 与最接近工作的定位对比。（TBC = 最终书目核对时补全）

| 工作 | 任务 | 设计/推断变量 | 重力/结构模型 | 端到端可微 | 界限/可补偿性分析 |
|------|------|---------------|---------------|------------|-------------------|
| [1] aiming-DMCRT 2025 | 镜场瞄准优化 | 瞄准点（2 自由度/镜） | 无 | 是 | 无 |
| [2] canting-DRT 2025 | canting 优化 | 面板倾角（仿射自由度） | 无 | 是 | 无 |
| [3] Pargmann 2024 | 原位计量（逆问题） | 表面法向场（反演） | 无 | 是 | 无 |
| [4,5] inverse-DL-RT 2025 | 由光斑预测面型 | 表面系数（反演） | 无 | 神经网络 | 无 |
| [6] Fast-NCM 2026 | 全场快速能流仿真 | —（前向代理） | 仅标量 σ_S | erf 闭式 | 无 |
| [21,22] 颜健 2024/25 | 支撑参数→光学精度 | 螺栓间距 d、数量 N（枚举） | FEA 参数化扫描（SHELL181） | 否（离线串行） | 无 |
| [23] Yang 2022 伞形镜 | 结构减重 | 支撑结构尺寸（正交试验） | ANSYS + TracePro | 否（离线串行） | 无 |
| [24] Thalange 2017 三脚架 | 结构-光学联合设计 | 三脚架尺寸（参数扫描） | STAAD Pro + 自研光追 | 否（离线串行） | 无 |
| 经典 canting / FEA 实践 | 调试阶段调整 | 面板倾角、焦距 | 离线 FEA 校核 | 否 | 无 |
| **本文** | **出厂面型设计** | **35 螺栓行程 + margin（梯度优化）** | **FEA 衍生 TPS 代理 + 20-bin NLGEOM 重力库（法向耦合）+ vK ROM** | **是（力学↔光学）** | **有（B\*、B_reachable、地板归因 + 可补偿性理论）** |

---

## 3. 系统模型与问题形式化

### 3.1 定日镜-螺栓结构系统

- 镜面几何：12.84 × 9.45 m × 4 mm 玻璃，35 螺栓 (7×5) 支撑，边距 8% （问题：后续会讨论更换钢材，如何平衡叙事？）
- 板局部坐标系约定（板法向为 y）→ 法向位移场 w(r)
- 倾角 θ 的定义：板法向与铅垂方向夹角（0° = 水平朝天，90° = 竖直）
- 图：定日镜结构示意图（含螺栓布局、坐标系、倾角定义）

### 3.2 镜场与站址
- 中国西北部某地（实际上是德令哈，37.36°N, 97.29°E，但文中最好不要点明），塔高 300m，圆柱接收器 (R=10m, H=20m)
- NEWS 四方位 × 五距离 (150/300/600/900/1200m) = 20 面代表性镜子
- 图：镜场平面布局 + 接收器几何

### 3.3 目标函数
*标注*:这里需要结合具体代码进行分析，下列不一定对，主要是螺栓行程约束。
  min_h  Σ_{sun} w_sun · S95( flux(h; sun_dir) )
  s.t.   |h_b| ≤ h_max  (螺栓行程约束)
- S95 定义：包含 95% 能量的最小圆面积（m²）
- 太阳方向权重 w_sun：月度等权，日内 1h 间隔
- 训练/验证集划分：36dir（快速迭代）/ 110dir（论文模式）/ 334dir（终版验证）（在文中如何说明这件事？）

### 3.4 倾角$\theta$的全年分布
*标注*:这部分是否值得单开一小节讨论？暂且按下不表

- 由站址经纬度 + 镜场几何解析推出全年 θ 分布
- 表：德令哈 300m NEWS 全年倾角范围（已有数据，draft 中 Table 1-1）
- 关键判读：North 全年 θ∈[30°,58°] 远离低角度区；South 24% 时间 θ<20°；E/W 穿越 46° NLGEOM 变号点
- 这段是 §5.3 "非均匀性几何解释"的理论铺垫

## 4. 物理信息可微优化框架
分两条线：渲染管线（4.1）+ 力学代理（4.2–4.3）。渲染管线适度压缩（细节放附录），力学代理展开（这是论文的核心方法贡献）。

### 4.1 可微 MCRT 渲染器（~2 页，压缩）

要点式叙述，强调"为跨域梯度而设计"的部分：
- Vulkan/Slang 实现：Buie 日轮 (CSR=0.01)、双层玻璃折射 (n=1.523, 4mm)、统计斜率误差 (1 mrad)
- GPU 协作二分 S95：单 workgroup 在 GPU 上做与 CPU 语义一致的二分查找（20 轮），无需回读，精度仅受浮点归约影响
- 稀疏像素剔除 (A1)：Box-Muller 前做宏观法向反射余弦预裁剪 → −4.8% 时间
- 编译期太阳模型特化 (A2)：Slang 常量折叠，3 条管线按 sun_type 分派
- 零回读优化循环：标量 loss 以定点数 ×1e3 在 GPU 累加，每迭代仅回读 4 字节
- 表：GPU Dispatch 总览（10 个 dispatch × 每太阳方向 × 每迭代，单次 submit）
- 附录 C 放完整 GPU 管线细节与性能数据

### 4.2 FEA 衍生的 TPS 物理代理（~3 页，核心方法节）

这是论文的方法论核心——物理代理模型的形式化与性质。

#### 4.2.1 面型参数化

$$w(r) = UY_grav(θ) + Σ_{b=1}^{35} h_b · φ_b(r)$$
- 第一项：零螺栓纯重力 FEA 解（NLGEOM-ON），20 个稠密角度 bin（10°–80°, 间距 ≤4°）双线性插值
- 第二项：35 螺栓单位位移 TPS 影响函数的线性叠加

#### 4.2.2 TPS 影响函数构建

  - 系统：A·[c; d] = [e_b; 0_3]，A = [K P; P^T 0]，K_ij = r²log(r²)
  - Tikhonov 正则 λ=10⁻⁶，自影响修正
  - 关键性质验证：单位分解（Σφ_b ≡ 1, PV≈1.3×10⁻⁶）、条件数 ~4.2×10⁶

  4.2.3 重力模型：20-bin NLGEOM 稠密插值 + 法向耦合

  - 为什么 20-bin：5-bin 稀疏插值导致 ~20% 系统性幅度低估 → "小光斑假象"
  - 三平面格式：每个 bin 存储 [w, ∂w/∂u, ∂w/∂v]（12KB/bin），重力同时进入高度和法线
  - 关键修复（可以作为"方法设计决策"来叙述，而非"bug 修复"）：重力必须进入 yu/yv 才能产生光学效应。此前重力仅进入高度 y
  不进导数 → 法线不变 → 反射方向不变 → 重力光学隐身。修复后重力成为真实光学扰动。
  - 46° NLGEOM 过零反转点：von Kármán 板非线性——膜应力在 ~46° 附近改变符号，重力场方向反转
  - 表：20-bin vs 5-bin 验证（R² 0.887→0.962, slopeCorr 0.931→0.996）

  4.2.4 代理精度与验证

  - TPS Proxy vs FEA 验证：RMS 2.0–3.3mm, shape_corr 0.95–0.96
  - APDL=GUI 位精确一致性（RMS<0.05mm）
  - 精度局限性讨论（线性叠加无 NLGEOM 反馈）→ §6.3 误差预算

  4.3 跨域梯度链（~2 页）

  dL/dh_b = Σ_sun Σ_p [∂L/∂flux · (∂flux/∂y · φ_b + ∂flux/∂yu · ∂φ_b/∂u + ∂flux/∂yv · ∂φ_b/∂v)]
  - 三段反向：bwd_diff（光学反传）→ reduceSurfaceGradients（跨 group 归约）→ projectBoltGradients（力学投影）
  - 力学域：∂w/∂h_b = φ_b（线性，精确），∂(∇w)/∂h_b = ∇φ_b
  - 光学域：∂flux/∂y, ∂flux
  - ∂yu, ∂flux/∂yv 由可微渲染器链式法则提供
  - 力学→光学的物理衔接：法线由 yu/yv 计算，重力三平面使重力斜率参与法线计算 → 梯度通过 yu/yv 通道反传至重力 bin
  查找（虽然重力 bin 不优化，但这是方法完整性的关键）

  4.4 正则化设计（~1.5 页）

  L(h) = L_S95 + λ_E·L_energy + λ_s·(h−h*)ᵀG(h−h*) + λ_b·hᵀKh + λ_h·Σ max(|h_b|−h_max, 0)²
  - R_anchor：斜率空间锚定 = TPS 弯曲能 hᵀGh（物理一致性——对 TPS 双调和插值，弯曲能恰为斜率 Gram 二次型）
  - R_bend：抑制相邻螺栓高频震荡（实现上与 anchor 共用 regGram）
  - R_soft：单边二次软行程墙（替代 tanh 硬界）
  - tanh 有界参数化：h = h_max·tanh(ε)，在无界 ε 空间做 Adam 更新
  - 闭式补偿初始化（见 §5.2 的快速预览或放在 §4.2.4）

  4.5 太阳方向采样策略（~0.5 页）

  - 真太阳正午对称设计（消除 EoT 不对称偏差）
  - 36/110/334 方向三级精度体系
  - E/W 镜过拟合证据：36dir 过拟合达 +1.7 m²


## 参考文献（占位编号；所有条目均需最终书目核对）

1. [aiming-DMCRT 2025] "A novel heliostat aiming optimization framework via differentiable Monte Carlo ray tracing for solar power tower." *Applied Energy*, 2025. (verified; authors/pages TBC)
2. [canting-DRT 2025] "The optimization of heliostat paraboloid canting via differentiable ray tracing." *Solar Energy*, 2025. (verified; authors/pages TBC)
3. [Pargmann 2024] Pargmann et al., "Automatic heliostat learning for in situ concentrating solar power plant metrology with differentiable ray tracing." *Nature Communications* 15:6997, 2024. (verified)
4. [inverse-DL-RT 2025] "Inverse Deep Learning Raytracing for heliostat surface prediction." *Solar Energy*, 2025. (verified; authors/pages TBC)
5. [sim2real-DL-RT 2025] "Scalable heliostat surface predictions from focal spots: Sim-to-Real transfer of inverse Deep Learning Raytracing." *Solar Energy*, 2025. (verified; authors/pages TBC)
6. [Fast-NCM 2026] Lin et al., "Real-time Radiative Flux Density Distribution Simulation via Data-Driven Neural Convolution Model for Solar Power Tower Systems." Preprint / under review, 2026. (lab-internal; bibliographic status TBC)
7. [Karniadakis 2021] Karniadakis et al., "Physics-informed machine learning." *Nature Reviews Physics* 3:422–440, 2021. (TBC)
8. [diff-struct-opt 2024] "Differentiable automatic structural optimization using graph deep learning." *Advanced Engineering Informatics*, 2024. (verified; authors/pages TBC)
9. [AEI-crane 2025] "Physics-informed neural network for load sway prediction in travelling autonomous mobile cranes." *Advanced Engineering Informatics*, 2025. (verified; authors/pages TBC)
10. [ECM-wind 2023] "Digital twin of wind farms via physics-informed deep learning." *Energy Conversion and Management*, 2023. (verified; authors/pages TBC)
11. [SolTrace TBC] Wendelin, "SolTRACE: A New Optical Modeling Tool for Concentrating Solar Optics." NREL, 2003. (TBC)
12. [Tonatiuh TBC] Blanco et al., Tonatiuh. (TBC)
13. [HFLCAL TBC] Ho & Khalsa, HFLCAL flux model. (TBC)
14. [UNIZAR TBC] Collado & Guallar, UNIZAR/Campo analytical flux model. (TBC)
15. [Buie TBC] Buie et al., sunshape model, 2003. (TBC)
16. [Mitsuba TBC] Nimier-David et al., "Mitsuba 2: A Retargetable Forward and Inverse Renderer." *ACM TOG*, 2019. (TBC)
17. [ZeroGrads TBC] ZeroGrads, *ACM TOG*, 2024. (TBC)
18. [glints-diff TBC] Fan et al., "Efficient Specular Glints Rendering With Differentiable Regularization." *IEEE TVCG* 29(6), 2023. (verified)
19. [canting-practice TBC] 经典 canting/调试实践的代表性文献——书目核对阶段选定。
20. [FEA-practice TBC] 定日镜结构 FEA 分析的代表性文献——书目核对阶段选定。
21. [Yan-bolt-2024] Bin Li, Jian Yan*, Wei Zhou, Youduo Peng. "Influence of Service Load and Structural Parameters on Optical Accuracy of Solar Tower Heliostat" (服役载荷与结构参数对塔式太阳能定日镜光学精度的影响). *Acta Optica Sinica*, 2024, 44(6): 0623001. DOI: 10.3788/AOS231688. (verified)
22. [Yan-bolt-jacking-2025] Jian Yan*, Tianchi Song, Youduo Peng, Wei Zhou. "Optical Accuracy Study of Pentagonal Tower Solar Heliostat Based on Support Bolt Jacking Molding" (基于支撑螺栓顶压成型的五边形塔式太阳能定日镜光学精度研究). *Acta Optica Sinica*, 2025, 45(6): 0608001. DOI: 10.3788/AOS241006. (verified)
23. [Yang-umbrella-2022] Yang et al., "A coupled structural-optical analysis of a novel umbrella heliostat." *Solar Energy*, 2022. DOI: 10.1016/j.solener.2021.12.031. (verified; full author list + pages TBC)
24. [Thalange-tripod-2017] Thalange et al., "Design, optimization and optical performance study of tripod heliostat for solar power tower plant." *Energy*, 2017, 135: 610–624. DOI: 10.1016/j.energy.2017.06.116. (verified)
25. [CFD-FEM-optical-2026] Zhang et al., "Multi-physics investigation of concentrating efficiency degradation in heliostats caused by wind-induced deformations." *Renewable Energy*, 2026. (TBC; full reference to be verified)
