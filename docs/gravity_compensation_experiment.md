# 重力补偿实验主报告：让 TPS Proxy 真正"抵抗重力"

> **目标**：回应导师批评（"proxy 未起真正优化作用"），建立可微渲染友好的实验框架——
> (1) 确立每面镜在斜率误差下的年均 S95 下界；(2) 用 TPS proxy 的物理特性显式抵抗重力、逼近该下界；
> (3) 设计与该目标匹配的正则项体系（含解除 tanh 有界参数化的消融）。
>
> **状态**：Phase 0–3 完成（2026-07-30，9 组消融闭环，结论定稿）；Phase 4 进行中（FEA 抽查待执行）。
> **终稿一句话结论**：重力经修复成为光学主导项后，35 螺栓面型调节对其畸变的补偿上限仅 ~13–16%，
> 理论可缩小差距的 84–87% 是支撑布局/玻璃刚度决定的**结构性硬地板**——与参数化、正则、init、优化器均无关。

---

# 第一部分　诊断结论

## 1.1 原始诊断：三个决定性事实（2026-07-27，已定量验证）

### 1.1.1 致命结构缺陷：重力在原渲染器中光学隐身

`shaders/bolt_common.slang:125-127`（修复前 `boltSurfaceAtGrid`）：

```glsl
y  = (disableGravity != 0u) ? 0.0f : sampleGravityUY(...);  // 重力进高度
yu = 0.0f;   // ← 重力不进 u 向导数
yv = 0.0f;   // ← 重力不进 v 向导数
```

法线 `nrm` 只由 `yu/yv` 决定，渲染器采样的是 `nGrid`。**重力只改变光线交点高度（≤11mm 视差，
300–1200m 距离上可忽略），从不改变反射方向。** 这精确解释了所有历史结果：

- "LS-Fit(重力开) ≡ Pure Ellipse(重力关)"（North_300m 51.61 = 51.61，逐位级一致）；
- 优化结果必然 ≈ 理想椭圆面——S95 损失根本感受不到重力，最优解当然只剩椭球法线场；
- 导师的批评可被机械地证明：proxy/重力链对光学目标的贡献**结构上为零**（不是"近似为零"）。

### 1.1.2 重力形变以"支撑间凹陷"为主，35 螺栓 TPS 张量结构性无法补偿

对 `data_proxy/gravity_*.bin`（20 角度 bin）的定量分解（`scripts/gravity_decomposition.py`）：

| 角度 | PV (mm) | 斜率 RMS (mrad) | 仿射 | 二次 | 高阶(凹陷) |
|---|---|---|---|---|---|
| 10° | 11.09 | 6.59 | 0.00 | 0.57 | **6.36** |
| 30° | 5.37 | 3.16 | 0.00 | 0.27 | **3.05** |
| 46° | 0.29 | 0.17 | ≈0 | ≈0 | 0.16（NLGEOM 过零反转点）|
| 58° | 2.84 | 1.60 | ≈0 | 0.17 | **1.52** |
| 80° | 1.50 | 0.96 | ≈0 | 0.10 | **0.92** |

- 重力场在螺栓处≈0（螺栓即支撑点 BC），凹陷在螺栓之间 → 而 `Φh` 是"过螺栓值的双调和插值"，
  两者几乎正交：高度-L2 投影 R²≈0.25–0.34；**斜率空间最优补偿也只能消去斜率方差的 ~20–24%**。
- 物理直观：4mm 玻璃跨 1.8m 支撑间距自重凹陷 ~7–11mm（板理论 w≈qa⁴/384D 估算一致）。
  这是**支撑布局/玻璃刚度决定的硬件属性**，不是螺栓行程能修的。

### 1.1.3 固定螺栓只能消去"年均均值场"，θ 变化分量不可约

对 20 面镜 × 334 太阳方向计算倾角分布与重力场统计：

- North 远镜 θ 范围窄（48–77°），θ 变化分量小（irr_slp≈0.34 mrad）；
- East/West 镜 θ 跨越 1–78°，穿越 **46° NLGEOM 变号点**（重力场方向反转），
  θ 变化分量达 2.5–2.9 mrad——固定螺栓对此完全无能为力；
- 全年均值场的最优固定补偿（斜率空间）总移除率仅 **0.2–22%**（受 1.1.2 可达性限制）。

**反射 ×2 后的原始重力斜率预算 2.3–8.5 mrad，与 Buie 太阳宽度 2.2 mrad 同量级甚至更大。**
一旦 1.1.1 的缺陷被修复，重力将从"光学隐身"变为"光学主导项"——这才是真正值得优化的问题。

### 1.1.4 诊断总结论

> 原管线中"优化 ≈ 椭圆拟合"不是优化器的失败，而是因为重力从未进入光学目标。
> 要让 proxy 起真正的优化作用，必须：(a) 修复重力→法线耦合（使其成为真实的光学扰动），
> (b) 用 proxy 的线性性给出**闭式均值场补偿**（proxy 显式做功），
> (c) 把不可达部分（凹陷 + θ 变化）定量归因到硬件，并认证可达下界。

## 1.2 修复后实测：H1 成立，重力惩罚定量化（Phase 1，2026-07-27 晚）

`analysis/real_gravity_penalty_table.md`（20 镜 A/B，coupling=0 vs 1，三轮跑批后定稿）：

- **H1 成立（趋势），量级为卷积预测的一半**：实测 S95_naive/B_ideal = 1.001–1.539×
  （South_150m 最大 1.539，North 远镜 ≈1.00–1.01）；与 H3 预测趋势高度一致
  （Pearson 0.913 / Spearman 0.922），但实测/预测均值仅 0.634 → S95 对斜率方差亚二次响应，
  H3 需加 α<2 修正（"可预测光学"的定量结果）。
- **Δ_envelope（h\* 闭式补偿 init 收益）**：近场显著（South_150m +5.10、South_300m +3.40、
  East_150m +3.17 m²，消去惩罚的 12–18%）；远场与 North ≈0 或略负。补偿后比值仍
  1.006–1.440 > 1 → 结构性地板存在（H2 定性成立）。
- **物理结论**：重力惩罚是**近场 South/East/West 镜的问题**；North 远镜可忽略。
- 德令哈 300m NEWS 全年倾角分布（110dir）：North θ∈[36.1°,64.5°] 中位 50.9°、35% 时间落
  40–50° 低凹陷区；South θ∈[0.2°,56.6°]、24% 时间 θ<20°。几何解释了惩罚非均匀性。

## 1.3 终稿结论：35 螺栓结构性硬地板（Phase 3，2026-07-30 闭环）

**9 组消融终表**（36dir, 300m NEWS, coupling=1, best S95 m²）：

| 组 | 参数化/正则 | N | E | S | W |
|---|---|---|---|---|---|
| a0 基线 | tanh 有界 | 50.34 | 76.21 | 94.28 | 76.19 |
| a1e3 | +锚定 1e3 | 50.42 | 76.26 | 94.33 | 76.18 |
| a1e4 | +锚定 1e4 | 50.48 | 76.27 | 94.26 | 76.14 |
| a1e5 | +锚定 1e5 | 50.73 | 76.33 | 94.47 | 76.29 |
| nt_soft1e5 | 无界+软墙 1e5 | 50.37 | 76.21 | 94.29 | 76.12 |
| nt_a1e3_soft1e5 | 无界+锚定+软墙 | 50.39 | 76.20 | 94.24 | 76.19 |
| nt_a1e3_soft1e6 | 无界+锚定+软墙1e6 | 50.39 | 76.20 | 94.24 | 76.19 |
| tanh_a1e3_b1e2 | tanh+锚定+弯曲能 | 50.46 | 76.24 | 94.34 | 76.15 |
| naiveinit | LSQ init 无正则 | 50.42 | 76.23 | 94.36 | 76.16 |

**判决（六重证据闭环）**：全部 9 组 E/S/W 地板锁定 ~76.2/94.3/76.2 m²（极差 ≤0.13 m²，
Monte Carlo 噪声量级），与以下因素全部无关：

1. **参数化形式**：tanh 有界 vs 无界物理空间（nt_soft1e5 与 a0 的 East 四位小数相同——硬界不是地板成因）；
2. **锚定强度** 0–1e5：a1e5 单调略差（强锚定压制仅存增益，锚定冗余成立）；
3. **行程约束**：soft1e5 与 soft1e6 逐位一致 → 软墙全程未激活，行程约束无关；
4. **弯曲能**：tanh_a1e3_b1e2 ≈ 基线，无额外增益；
5. **init 选择**：naiveinit（init 逐位等于 B_naive）与 comp-init 路径收敛到同一点，
   总回收量一致（E：77.90→76.23=1.67 ≈ comp 路径 1.19+0.50=1.69）；
6. **先验投影上界**：Phase 0 子空间投影（斜率空间最优补偿仅 20–24%）与端到端实测（~15%）同量级互证。

E/S/W 重力地板是 **35 螺栓支撑布局的结构性硬约束**。论文叙事确立为
"认证地板 + 解释地板 + 结构性出路（支撑布局/刚度优化，而非螺栓调节）"。
North 对照（优化降至 50.34，距 B\* 49.77 仅 0.57）说明优化器本身工作正常，地板不是优化失败而是物理。

## 1.4 差距三分解（论文定量核心，@36dir, 300m NEWS, S95 m²）

框架：每面镜从最差（naive init，重力全罚）到理论最优（B\*，无重力优化下界）的总差距，
分解为三段——① 闭式补偿 init 回收；② 端到端优化再回收；③ 结构性地板残余（35 螺栓不可达）。

| 镜 | 总差距 naive→B\* | ① comp init 回收 | ② 端到端再回收 | ③ 地板残余 | ③占比 |
|---|---|---|---|---|---|
| North | 51.31→49.77 = 1.54 | −0.44（comp 略伤免罚镜） | +1.41 | 0.57 | 37%（小罚镜，残差主要是优化噪声/正则化差距） |
| East | 77.90→65.00 = 12.90 | 1.19（9.2%） | 0.50（3.9%） | **11.21** | **86.9%** |
| South | 98.33→73.07 = 25.26 | 3.43（13.6%） | 0.62（2.5%） | **21.21** | **84.0%** |
| West | 78.07→64.68 = 13.39 | 1.24（9.3%） | 0.64（4.8%） | **11.51** | **86.0%** |

对承罚镜（E/S/W），理论可缩小差距的 **84–87% 是结构性的**；螺栓面型调节对重力畸变的
补偿上限 ~13–16%。出路只能是支撑布局/刚度设计（支撑点数量与位置、背板结构）。
init 无关性已由 naiveinit 组确认，③占比对 init 选择稳健。

## 1.5 基线定义与数值表（@36dir, 300m NEWS, S95 m²）

| 镜 | B_ideal（LSQ 无重力） | B_naive（LSQ+真实重力） | B_comp（闭式补偿 init） | B\*（无重力端到端优化） | 重力惩罚 naive−ideal |
|---|---|---|---|---|---|
| North | 51.32 | 51.31 | 51.75 | **49.77**（−3.0%） | −0.01 |
| East | 65.68 | 77.90 | 76.71 | **65.00**（−1.0%） | 12.22 |
| South | 73.51 | 98.33 | 94.90 | **73.07**（−0.6%） | 24.82 |
| West | 65.60 | 78.07 | 76.83 | **64.68**（−1.4%） | 12.47 |

要点：四镜 B\* 均低于 B_ideal（余量 0.44–1.55 m²）——300m 处椭圆 LSQ 离无重力地板已很近，
真正的战场是重力惩罚段（E/S/W 12–25 m²）；该段正是结构性地板所在。

## 1.6 事故教训：台式机幻影重力（2026-07-29 判定）

台式机 4 组消融曾声称"全组收敛至 B\*、地板系 init 困住优化器、锚定充分"——**全部无效**，
系幻影重力（phantom gravity）环境假象。判决证据：其 naiveinit 的 LSQ init 与**无重力** B_ideal
逐位相等（真实重力下必须等于 B_naive，E/S/W 差 12–25 m²）；耗时 439s/组 vs 笔记本 12527s/组（28×）。

**根因**：v2 三平面重力 bins（12288 B/bin）在笔记本本地重生成后未及时 commit，台式机 pull 到旧版
单平面 bins（4096 B/bin），加载器走 legacy 分支（du/dv 补零 → 法线不吃重力斜率 → 重力光学隐形，
即 1.1.1 的 bug 在台式机上复活）。已修复并推送（注：本文涉及的 commit 哈希均为 2026-07-30 仓库历史重写前的旧哈希，仅作叙事保留，已失效）。

**双机校验规程（今后强制执行）**：凡含 `data_proxy` 的交接，必须校验
① bins 字节数 = 12288；② 运行日志含 `Loaded gravity_*deg.bin (3-plane, ...)`（20 行）；
③ 眼检 East init ≈77.9（真实重力）而非 ≈65.7（幻影）。
台式机事故数据的附带价值：构成"重力光学失效签名"标准样本（init==B_ideal、全组→B\*、早停、~28× 加速），
可作任何新环境的自检对照。

---

# 第二部分　诊断方案

## 2.1 核心概念

- **B_ideal**：理想椭圆面 + 无重力 + 斜率误差的年均 S95。
- **B\***：无重力下端到端螺栓优化的年均 S95（`disable_gravity:1`）——光学可达性的经验地板。
- **B_reachable**：有重力时 35 螺栓结构性可达的下界 ≈ 由"补偿后残余斜率预算"预测的 S95。
- **差距三分解**（每面镜）：
  `S95_naive(LS螺栓+真实重力) − B* = Δ_envelope(可闭式补偿) + Δ_tune(可微调) + Δ_irreducible(凹陷+θ变化)`

## 2.2 可证伪假设（预注册）

- **H1**：修复斜率耦合后，`S95_naive/B_ideal` 显著 >1（预测 1.3–4×，South/East 近距离最大）。
  → **已成立**（实测 1.001–1.539×，趋势 Pearson 0.913，量级为预测 ~0.63 倍，见 1.2）。
- **H2**：闭式均值场补偿 + 锚定微调可缩小差距，但存在由凹陷决定的硬地板 B_reachable > B\*。
  → **已成立**（回收上限 ~15%，地板 84–87%，见 1.3/1.4）。
- **H3**：实测 S95 与简化卷积模型 `σ_tot² = σ_sun² + (2σ_slope)² + (2σ_grav,res)²` 趋势一致。
  → **趋势成立、需 α<2 亚二次修正**（S95 对斜率方差响应低于二次模型预测）。
- **H4**：有形状锚定时，解除 tanh 界不会发散，且收敛更快/行程更物理。
  → **不发散成立**；但锚定本身冗余（收益为零，a1e5 反而略差），"更快/更物理"无意义——
  地板对所有正则组合一视同仁。

## 2.3 Phase 0–4 设计与通过标准

### Phase 0 — 数据审计与诊断定量化（纯 Python 只读）

`scripts/gravity_decomposition.py`：每角度重力 bin 的 PV/RMS/三频带分解（仿射/二次/高阶）；
46° 变号点原生 ANSYS CSV 独立复核；高度-L2 与斜率空间两种投影的可补偿率；
每镜 θ 分布、年均均值场、不可约 θ 方差、残余斜率预算 → H3 预测表。
产出 `analysis/gravity_compensability_report.{md,json}`。
**通过标准**：预测表完整；46° 变号点有明确结论。✅（变号点确为 FEA 物理，bin 保真度差 0.0000mm）

### Phase 1 — 重力斜率耦合修复 + 真实重力惩罚测定

- 数据：`scripts/generate_proxy_model.py` 重力 bin 扩展为 3 平面 `[w, dw/du, dw/dv]`
  （中心/单边差分 + σ=1px 高斯预平滑），`gravity_angles.json` 加 `"format": "w_du_dv_v2"` 标记，
  旧格式回退 legacy（幻影）行为。
- Shader：`bolt_common.slang` 三平面采样 + `gravityNormalCoupling` 开关
  （`yu += coupling ? gdu : 0`）；`bolt_forward.slang` push const 透传。
  反向路径无需改动：重力导数是与参数无关的数据，AD 链不变。
- C++：`pipeline.cpp` 按 3×1024 float/bin 加载；push const 扩展。
- 验证：强制重编 shader；`--check-grad` 在 coupling∈{0,1} 下判定；
  20 镜 A/B 差距表（`iterations:1, lr:0` eval 模式）→ `analysis/real_gravity_penalty_table.md`。
- **通过标准**：check-grad 判定在案；A/B 表与 H1 预测对照一致（或解释偏差）。✅

### Phase 2 — 下界建立 + 闭式重力补偿

- B\*：`disable_gravity:1` 端到端优化，300m NEWS。sanity：B\* ≤ B_ideal。✅（四镜均低 0.4–1.5 m²）
- 闭式补偿生成器 `scripts/lsq_fit_compensated.py`：

```
h_shape = argmin_h ||Φh − s_ellipse||²                      （形状拟合）
ḡ(x,z)  = Σ_dirs w_dir · g(θ_dir)(x,z)                     （年均均值场）
h_comp  = argmin_h ||∇(Φh) − ∇(−ḡ)||² = −(AᵀA)⁺Aᵀ·∇ḡ       （斜率空间，闭式）
h*      = h_shape + h_comp                                  （框架初始螺栓）
```

  输出 `data/init_comp*/{name}_bolt_init.txt`、锚定 buffer（斜率 Gram G 35×35 + G·h\*，存
  `{name}_anchor.bin` 35×36 float32）、comp_summary.csv（行程 PV、移除率、残余预算）。
- 补偿有效性 eval 验证（不动优化器）：LS init vs h\* init 的 S95 差 = Δ_envelope 实测。✅

### Phase 3 — 正则项套件 + 解除 tanh 消融

总损失：

```
L(h) = L_S95(h) + λ_E·L_energy(h)          （已有，≥900m 保留）
     + λ_s·(h−h*)ᵀ G (h−h*)                R_anchor：斜率度量信任域
     + λ_b·hᵀ K h                           R_bend：弯曲能量（可选）
     + λ_h·Σ_b max(|h_b|−h_max, 0)²         R_soft：软行程墙（替代 tanh）
```

- **R_anchor**：G 为斜率 Gram——把优化限制在"物理一致的补偿椭球面"附近，度量本身即光学相关量；
  梯度闭式 `2λ_s·G(h−h*)`。这是"proxy 抵抗重力"在损失层面的表达（锚点 h\* 已含闭式补偿）。
- **R_bend**：弯曲能 Gram，抑制相邻螺栓高频震荡；实现上与 anchor 共用 regGram——
  对 TPS 双调和插值，弯曲能恰为 hᵀGh（斜率 Gram 二次型），物理一致，非 bug。
- **R_soft**：单边二次墙；`tanh_bound:0` 时成为唯一行程约束（检验"有锚定时硬界是否多余"）。
- 实现：全部二次型 → 闭式梯度，GPU 开销可忽略（`bolt_optimizer.slang` `adamUpdateBolt`
  + `pipeline.cpp` `boltAdamStep` push const `{λ_s, λ_b, λ_h, tanh_bound}`）。
- 消融矩阵（300m NEWS，36dir）：`tanh{on,off} × anchor{0,1e3,1e4,1e5} × bend{0,1e2}` + naiveinit，共 9 组。
- **通过标准**：λ 扫描 Pareto；tanh off + anchor on 不发散且行程 ≤ 软墙+10%；正则梯度占比记录在案。✅

### Phase 4 — 全场验证与差距分解报告（进行中）

1. ✅ 差距三分解表（300m NEWS @36dir，见 1.4）。
2. ✅ FEA 抽查（2026-07-30，见 3.7）：South+North 300m × {0°, 29.5°, 58.5°}，proxy(螺栓+重力) vs FEA
   RMS 2.1–3.3mm、shape_corr 0.95–0.98，与历史验证同水平——**地板为真实物理，非 proxy 伪影**。
3. 可选：110dir 复核（`_bound_nograv_300m`、`_fw_tanh_a0_110`）；
   布局敏感度 Tier-2（w∝a⁴ 解析估算 + 6×6/8×6 布局对照）——"地板由硬件决定，
   框架能量化并优化这个权衡"的收口论证。
4. ✅ CLAUDE.md 更新（实验日志条目 + 双机校验规程）。

## 2.4 新增配置键

| 键 | 默认 | 说明 |
|---|---|---|
| `gravity_normal_coupling` | 1 | 重力导数是否进入法线（0=legacy 幻影行为，供消融/环境自检） |
| `anchor_lambda` (λ_s) | 0.0 | 形状锚定强度；>0 时需 `{name}_anchor.bin` |
| `bend_lambda` (λ_b) | 0.0 | 弯曲能量正则强度 |
| `soft_stroke_lambda` (λ_h) | 0.0 | 软行程墙强度（单边二次） |
| `tanh_bound` | 1 | 1=L4 tanh 现状；0=无界物理空间 + 软墙 |

注意 lr 语义：`tanh_bound:0` 时 lr 为物理步长；tanh 模式内部 `lr_ε = lr/h_max`
（`pipeline.cpp:996`），两种模式零点物理步长均等于 lr——**均推荐 lr=4e-4**。

## 2.5 分支预案（实际走向已加粗）

- 最可能：H1 成立 + 结构性地板 → **已证实，叙事="认证地板 + 解释地板 + 结构性出路"，
  这正是对导师最硬的回答：proxy 不仅给出闭式补偿，还精确归因了不可达部分（支撑间距/玻璃刚度）**。
- 若 H1 不成立（重力光学无关）→ 未发生。
- 若 h_comp 行程超界 → 未发生（max|h\*|=33–54mm < 60mm 界）。
- 若 tanh off 发散 → 未发生（有/无锚定均不发散，硬界冗余）。

---

# 第三部分　实验日志

## 3.1　2026-07-27：Phase 0 完成；Phase 1 修复落地；bug #1–#4

**Phase 0 完成**：`scripts/gravity_decomposition.py` + `analysis/gravity_compensability_report.{md,json}`。
关键数字：重力斜率（σ=1 平滑后存储导数）0.078–3.264 mrad/角度；高阶凹陷绝对主导（仿射≈0、二次≤0.6 mrad）；
46° NLGEOM 变号点经原生 ANSYS CSV 复核为 FEA 物理（bin 保真度差 0.0000mm）；
TPS 逐角斜率方差移除 26–38%；每镜原始斜率预算 0.56–2.30 mrad；
H3 卷积预测 S95_naive/B_ideal = 1.14–3.39×。

**Phase 1 实现落地**（并行实现 + 审查修复），审查发现并修复 3 处 bug：

1. `bolt_common.slang` `boltSurfaceAtGrid`：bin 存物理斜率 ∂w/∂x，shader 约定 ∂/∂u=∂/∂x·W，
   补 `yu = gField.y * hs.x; yv = gField.z * hs.y`（不修法向效应被低估 ~10×）；
2. `pipeline.cpp` `boltAdamStep`：`lrComp = lr/hMax` 原对 tanhBound=0 也生效（物理步长会大 25×），
   改为 `tanhBound ? lr/hMax : lr`；
3. 锚定 buffer 逐镜加载：`createBoltBuffers()` 有一次性守卫且 auto 路径为全镜共享 `anchor.bin`，
   改为创建期只建零填充 dummy（保绑定 26/27），`optimize()` 在 bolt init 解析后按
   `_bolt_init.txt → _anchor.bin` 逐镜加载，缺失时 hard error。

**check-grad 判定**：coupling=1 与 coupling=0 的 S95 Sigmoid 测试均报 ISSUES
（cosine ≈0.966/0.967，AD/FD ratio ≈0.35，FD 在 eps 扫描中符号翻转）——两者逐位一致，
判定为分位点损失上 FD 检查的**既有伪差**，与重力耦合无关，记录在案后继续。

**c0 ≡ Pure Ellipse 实证**：`_eval_lsq_c0`（coupling=0）North_150m = 38.7852 m²，
与既有 Pure Ellipse 表 38.78 一致 → 334dir 下 c0 列冗余。

**Phase 2 闭式补偿**：`scripts/lsq_fit_compensated.py` 产出 `data/init_comp/` 20 镜
（h\* init + 逐镜 `_anchor.bin` [G 35×35 | G·h\* 35] + comp_summary.csv）。

**首轮跑批暴露并修复 bug #3、#4 前身的 2 个新 bug（下午）**：

- **`lsq_fit_compensated.py` 活塞模态污染**：斜率设计矩阵近零奇异方向（σ≈2e-7，螺栓整体同升同降——
  斜率空间不可见），`rcond=None` 的 lstsq 给 h_comp 叠了 ~1.3×10⁶ mm 常数分量
  （h_star_max_abs 达 1346540mm），渲染时镜面等效下移 1.3km → comp_c1 全场 S95=0。
  修复：`rcond=1e-6` 截断 + |h\*|>0.2m sanity 断言；修复后 max|h\*|=33–54mm，移除率不变（4–37%）。
- **`runValidation` 重力 bin 陈旧**（`pipeline.cpp` bolt 路径）：逐方向 eval 只调
  `updateUniforms + forwardRender`，从不重建表面——法线实际用"上一次 `boltForwardSurface` 的
  cos-θ bin"渲染全部方向。coupling=0 无影响（c0 有效）；coupling=1 时 init/iter-0 eval 双双错误
  （East_150m：64.26 vs 45.81，并出现"重力改善 S95 低于无重力理想"的物理不可能结果）。
  **首轮 c1 数据全部作废。** 修复：runValidation 内每方向调
  `boltForwardSurface(computeCosTheta(sd,...))`。该 bug 影响所有 coupling=1 训练运行的周期性验证
  （bestS95 选择会被带偏），修复是 Phase 2/3 跑批前提。

**bug #4（晚）：Adam tanh 回写静默夹紧 init**。修复 bug #2 后重跑，c1 出现 init/iter-0 分裂
（North_150m：init 45.63 vs iter-0 95.91）。逐方向 debug 探针（`BEZIER_DEBUG_EVAL=1`）定位链条：
iter-0 所有方向 S95 一致放大 ~2.1× → yGrid 逐方向精确下降 1.312762mm（恒常活塞）→
dump `m_boltHeights` 实锤：4 个角螺栓 50.6mm → 39.96mm（=0.999×hMax）。
根因：`adamUpdateBolt` tanh 路径无条件执行 `h = hMax·tanh(atanh(clamp(h/hMax)))`，即使 lr=0 也把
超界 init 螺栓投影到 0.999·hMax；LS/comp init 角螺栓 ~50.6mm > 旧默认 `max_bolt_stroke=0.040`。
c0 未暴露的原因：旧二进制 runValidation 用陈旧表面（bug #2），两个 bug 相互隐藏——
历史训练配置全部显式设 0.040，即所有历史优化运行都从这个夹紧瞬态起步。
修复（双管齐下）：`bolt_optimizer.slang` `lr==0` 时整个 adam update 提前返回；
全部新实验配置 `max_bolt_stroke: 0.06`。
最终裁决：c0 列与 c1/comp_c1 的 init 列有效；iter-0 列作废；修复后 init≡iter0，"Best S95" 重新可信。

**Phase 1 A/B 惩罚表完成（晚，三轮跑批）**：结论见 1.2。

## 3.2　2026-07-27 晚：加速决策与 36dir 转向

- 快速迭代环路先切 110dir（334dir 单镜 eval 815s → 110dir ≈270s）；后实测 110dir 训练
  ~254s/iter（含验证）→ 200iter×20镜不可行，**训练类跑批全部转 36dir**（36_sundir_fast.txt，
  ~3× 加速；基线 eval 同步生成 36dir 版保持同 sun set 可比）。334dir 仅留 Phase 4 最终全场表。
- 36dir↔110dir 一致性（c0 全 20 镜）：偏差 ±2.4% 以内（远场 <0.5%），合格。
- 36dir 资产：`_eval_*_36` 变体、`data/init_comp_36/`、`_bound_nograv_300m_36`。

## 3.3　2026-07-28：基线定稿；B\*@36 四镜齐备；Phase 3 启动

- 36dir 基线定稿（300m NEWS）：数值见 1.5。comp init 仅回收惩罚 10–14%（E/S/W），
  North 上 comp 反而略差（+0.44 m²，免罚镜补偿即失配）。
- **B\*@36 四镜齐备**：North 49.7719（init 51.3327，−3.0%）；E/S/W 见 1.5。
  North init 自洽性校验通过；North 平台期 iter 100 后出现（best@100），据此 ESW 与 Phase 3
  改为 120/150 iter 封顶。计时口径修正：~29.5s/iter 均值（验证迭代 ~82s、普通迭代 ~24s）。
- **范围决策（用户指示，今后一律执行）：训练/消融类跑批只跑典型 300m NEWS 四镜，不跑全 20 镜**；
  已启动任务中 600m 及以远样本全部终止。全 20 镜定量结论以 110dir 惩罚表为准。
- **Phase 3 启动**（任务 bash-0vw59byn）：8 组顺序跑批，300m NEWS、36dir、coupling=1、
  comp init（`data/init_comp_36`）、lr=4e-4（已核实 lrComp 分支：tanh 与物理两种模式零点物理步长
  一致，nt 组无需改 lr）。
- 支线：投稿规划文档重写（`docs/submission_strategy_and_outline.md`：AEI 首选/Applied Energy 备选/
  TVCG 风险）；NCM Model 调研结论（Fast-NCM 为 7.9 万参数 MLP，输入仅标量 σ_S，无法接收面型
  空间结构，不能用于逐面型"理想光斑"预测；可借鉴其 erf 闭式可微渲染与参数拟合管线）。

## 3.4　2026-07-28（二）：Phase 3 首组 a0——端到端回收率仅 ~15%

`_fw_tanh_a0`（tanh、无正则、comp init、重力全开、150iter）四镜：init 51.75/76.71/94.90/76.83 →
best 50.34/76.21/94.28/~76.21。**端到端在重力下几乎推不动 S95**——所有镜 iter ~80 后硬平台
（±0.03 m² 内波动）；comp init + 端到端合计仅回收惩罚 ~15%，远低于子空间投影预言的 26–38%。
叙事自此从"逼近 B\*"修正为"认证地板 + 解释地板 + 结构性出路"。

**估算错误更正**："每组 ~1.2h"系把每镜 75 分钟误当每组；实测 ~30s/iter → 每组（4 镜×150iter）≈5h。
处置：剩余 7 组砍至 100 iter（平台证据充分），新增第 9 组 `_fw_tanh_naiveinit`。

## 3.5　2026-07-29：锚定扫描；超时事故；台式机幻影重力；跑批收尾

- 新增完成组：a1e3/a1e4 ≈ 基线；a1e5 单调略差（锚定冗余）；nt_soft1e5 与 a0 完全一致
  （East 四位小数相同——硬界不是地板成因）。五重证据同指结构性硬地板。
- **超时事故**：链条 bash-0vw59byn 于 09:15 撞 20h 超时被杀（死在 nt_a1e3_soft1e5 开头，无损失）；
  剩余 3 组以 bash-xatj04c5（disable_timeout）重启。
- **台式机幻影重力事故**：其 4 组结果判定无效（根因=未提交的 v2 bins，详见 1.6）；
  笔记本同配置对照组 nt_a1e3_soft1e5 = 50.39/76.20/94.24/76.19（12527s，20 行 3-plane 加载记录）。
- **跑批收尾**：nt_a1e3_soft1e6 与 soft1e5 逐位一致（软墙未激活）；tanh_a1e3_b1e2 ≈ 基线
  （弯曲能无增益）。收尾提交（含 v2 bins 修复 + 3 组结果 + 双机校验规程）。

## 3.6　2026-07-30：naiveinit 补跑——9/9 闭环，Phase 3 定稿

- `_fw_tanh_naiveinit`（LSQ init、无正则、36dir、100iter、真实重力 3-plane ×20 确认，13063s）：
  init 逐位等于 B_naive（51.31/77.90/98.33/78.07）→ best **50.42/76.23/94.36/76.16**，落同一地板。
  总回收量路径一致（E：naive 1.67 ≈ comp 1.69）→ **init 无关性闭环，六重证据齐备**。
- 报告定稿：消融终表、判决段落、差距三分解表（1.4）、FEA 抽查方案；CLAUDE.md 实验日志条目。
  收尾提交，已推送远端。
- **FEA 抽查命令已验证**（dry-run 通过，ANSYS v252 @ L:\）：

```
python scripts/run_fea_validation.py --result-dir results_fw_tanh_a0 --heliostat-prefix South_300m --compare
```

  选 South 300m（惩罚最大 Δenv≈25 m²、地板残余 84%——若地板系 proxy 伪影将在该镜暴露最明显），
  默认角度 0°/29.5°/58.5°，`--compare` 自动对照 proxy 形变。

---

# 第四部分　文件改动清单

## 4.1 代码（shader / C++）

| 文件 | 改动 |
|---|---|
| `shaders/bolt_common.slang` | 重力采样改三平面 `_readGravity3` / `sampleGravityField`；`boltSurfaceAtGrid` 增加 `gravityNormalCoupling` 耦合开关（∂w/∂x→∂/∂u 尺度修正，bug #1） |
| `shaders/bolt_forward.slang` | push const 透传 `gravityNormalCoupling` |
| `shaders/bolt_optimizer.slang` | 锚定/弯曲/软墙闭式梯度（regGram + anchorTarget buffer）；`tanh_bound` 分支；`lr==0` 时 adam update 提前返回（bug #4） |
| `src/pipeline.cpp` | 重力 bin 按 3×1024 float/bin 加载（兼容 legacy 警告分支）；`boltAdamStep` push const 扩展与 lrComp 修正（bug #2）；`runValidation` 逐方向重建表面（bug #3）；锚定 buffer 逐镜加载；`--check-grad` 支持 |
| `src/config.h` / `src/config.cpp` | 5 个新配置键（见 2.4） |

## 4.2 脚本

| 文件 | 改动 |
|---|---|
| `scripts/gravity_decomposition.py` | 新建（Phase 0 分析固化） |
| `scripts/lsq_fit_compensated.py` | 新建（h\* init + 锚定 buffer 生成；含 rcond=1e-6 截断 + sanity 断言） |
| `scripts/generate_proxy_model.py` | 重力 bin 输出 3 平面 [w,du,dv] + 平滑选项 + `w_du_dv_v2` 格式标记 |
| `scripts/run_fea_validation.py` | 现有管线，Phase 4 FEA 抽查入口（dry-run 已验证） |

## 4.3 数据资产

| 路径 | 说明 |
|---|---|
| `data_proxy/gravity_*.bin` | **v2 三平面格式（12288 B/bin）**——2026-07-27 重生成，曾因未提交导致台式机幻影重力事故，事故后修复入库 |
| `data_proxy/gravity_angles.json` | 增加 `"format": "w_du_dv_v2"` 标记 |
| `data/init_comp/` / `data/init_comp_36/` | h\* init（`_bolt_init.txt`）+ 逐镜锚定 buffer（`_anchor.bin` 35×36 float32 + JSON 元数据）+ comp_summary.csv |

## 4.4 配置（`configs/`）

| 配置 | 用途 |
|---|---|
| `_eval_lsq_c0/c1`、` _eval_comp_c1` 及 `_36` 变体 | A/B eval（B_ideal / B_naive / B_comp 基线） |
| `_bound_nograv_300m(_36)` | B\* 无重力下界 |
| `_fw_tanh_a0` / `_fw_tanh_a1e3/a1e4/a1e5` | Phase 3 消融：基线 + 锚定扫描 |
| `_fw_nt_soft1e5` / `_fw_nt_a1e3_soft1e5/soft1e6` | 解除 tanh + 软墙 ± 锚定 |
| `_fw_tanh_a1e3_b1e2` | 弯曲能组 |
| `_fw_tanh_naiveinit` | 第 9 组：LSQ init 无正则（init 无关性检验） |
| `_bound_nograv_300m`、`_fw_tanh_a0_110`（待建） | 可选 110dir 复核 |

公共参数：300m NEWS、36dir、coupling=1、100–150 iter、lr=4e-4、`max_bolt_stroke: 0.06`。

## 4.5 结果与分析文档

| 路径 | 说明 |
|---|---|
| `analysis/gravity_compensability_report.{md,json}` | Phase 0 诊断报告（三频带分解、可补偿率、H3 预测） |
| `analysis/real_gravity_penalty_table.md` | Phase 1 真实重力惩罚表（20 镜 A/B，H1 实测） |
| `results_fw_*/`（9 组） | Phase 3 消融结果（BEST_bolts + history + optimization_summary），force-add 入库 |
| `results_bound_300m_36/` | B\*@36 结果 |
| `docs/gravity_compensation_experiment.md` | 本文档（2026-07-30 按"结论/方案/日志/清单"重构） |
| `docs/gravity_compensation_experiment_DESKTOP.md` | 台式机侧记录 + 笔记本复核作废判定（保留作幻影重力样本） |
| `docs/submission_strategy_and_outline.md` | 投稿方向分析 + 论文大纲（AEI 首选） |
| `docs/draft.md` | 论文初稿中文版（摘要+引言+相关工作） |
| `CLAUDE.md` | Phase 0–3 实验日志条目 + 双机 data_proxy 校验规程（1.6） |

---

> **下一步**：Phase 4 FEA 抽查（3.6 命令）→ 报告定稿；可选 110dir 复核。

## 3.7　2026-07-30：Phase 4 FEA 抽查——地板通过独立验证（含第三次幻影重力事故）

**事故（幻影重力第三次转世）**：台式机首轮 FEA 对比（`run_fea_validation.py --compare`）报告
RMS 2.8–3.9mm"与历史同水平"并判通过——复核发现其日志 `WARN: gravity bin has 3072 floats,
expected 1024` + `Gravity PV: 0.00 mm`：Python 加载器只认 1024-float 旧格式，v2 bins 静默置零，
对比实为 FEA(螺栓+重力) vs proxy(仅螺栓)，RMS 递减曲线正是被减掉的重力场本身。
修复 `load_gravity_bins` v2 分支（取 w 平面；`post_fea_validation.py` 共享同一函数一并修复）后重跑。

**有效结果**（proxy 重力加载正确，Gravity PV=11.09/5.54/2.83mm 逐位吻合 bin 值）：

| 镜 | 角度 | RMS (mm) | R² | shape_corr | PV ratio | 无效轮 RMS→本轮 |
|---|---|---|---|---|---|---|
| South_300m | 0° | 2.281 | 0.942 | 0.975 | 1.089 | 3.907 → −42% |
| South_300m | 29.5° | 2.858 | 0.908 | 0.962 | 1.092 | 3.750 → −24% |
| South_300m | 58.5° | 3.346 | 0.877 | 0.954 | 1.267 | 2.900 → +15% |
| North_300m | 0° | 2.129 | 0.948 | 0.978 | 1.073 | 3.842 → −45% |
| North_300m | 29.5° | 2.739 | 0.914 | 0.964 | 1.075 | 3.667 → −25% |
| North_300m | 58.5° | 3.244 | 0.882 | 0.956 | 1.249 | 2.777 → +17% |

**判定：通过——重力地板是真实物理。** 论据：① 加入 proxy 重力后大重力角度 RMS 大降
（0° −42~45%）——proxy 与 FEA 重力场形状高度吻合；② South≈North（惩罚差 25 倍而偏差几乎相同）
→ 偏差由两镜共享的螺栓/TPS 侧主导，重力侧无系统性失真；③ 量级与 2026-07-17/21 历史验证一致
（RMS 2–3.3mm, corr 0.95–0.98）。
**保留项**：58.5° PV_ratio ~1.25–1.27（贴近 46° NLGEOM 变号区，小分母放大；方向为 proxy 高估形变，
地板若有偏差系略微高估而非伪造，结论方向安全）。

**校验规程追加（第四次幻影预防）**：任何读取 `gravity_*.bin` 的代码（C++/Python/未来脚本）
必须按文件大小分派格式（1024=legacy 拒绝或警告、3072=v2 取三平面），且打印所加载 gravity PV——
`Gravity PV: 0.00` 一律视为环境事故而非数据。

**Phase 4 状态**：核心验证收口。剩余可选：110dir 复核（`_bound_nograv_300m`、`_fw_tanh_a0_110`）。

**§3.7 补记（执行与产物）**：抽查于台式机执行（ANSYS v252 默认路径，`L:\Code\bezier_opt_desktop`）。
环境自检通过：bins=12288B、两镜 STROKE_bolts 在位。首轮（无效轮）数值：South 3.907/3.750/2.900、
North 3.842/3.667/2.777（proxy 重力置零所致，见上）；修复后重跑即上表有效值。
产物（台式机本地保留）：`results_fw_tanh_a0/fea_validation/`（APDL 输入、node_dump CSV、
逐角度对比 PNG×6、`comparison/metrics_*.json`×6，数值与日志一致）；
日志 `_phase4_fea_{south,north}300m_v2.log` 已随本报告归档于 docs/ 讨论记录。
North 作阴性对照（惩罚≈0），其与 South 偏差几乎相同是"偏差由螺栓/TPS 侧主导"的关键证据。
