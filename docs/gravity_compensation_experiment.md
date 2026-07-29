# 实验设计：让 TPS Proxy 真正"抵抗重力"——逼近每面镜的年均 S95 下界

> 目标：回应导师批评（"proxy 未起真正优化作用"），设计并实现一套可微渲染友好的实验框架，
> (1) 确立每面镜在斜率误差下的年均 S95 下界，(2) 用 TPS proxy 的物理特性显式抵抗重力、逼近该下界，
> (3) 设计与该目标匹配的正则项体系（含解除 tanh 有界参数化的消融）。

---

## 进度日志

### 2026-07-27

**已完成**

- **Phase 0 完成**：`scripts/gravity_decomposition.py` + `analysis/gravity_compensability_report.{md,json}`。
  关键数字：重力斜率（σ=1 平滑后存储导数）0.078–3.264 mrad/角度；高阶凹陷绝对主导（仿射≈0、二次≤0.6 mrad）；
  46° NLGEOM 变号点经原生 ANSYS CSV 复核为 FEA 物理（bin 保真度差 0.0000mm）；
  TPS 逐角斜率方差移除 26–38%；每镜原始斜率预算 0.56–2.30 mrad；
  H3 卷积预测 S95_naive/B_ideal = 1.14–3.39×，B_reachable = 1.13–2.90×。
- **Phase 1 实现落地**（并行实现 + 审查修复）。审查发现并已修复 3 处 bug：
  1. `shaders/bolt_common.slang` `boltSurfaceAtGrid`：bin 存物理斜率 ∂w/∂x，shader 约定 ∂/∂u=∂/∂x·W，
     已补 `yu = gField.y * hs.x; yv = gField.z * hs.y`（不修法向效应被低估 ~10×）；
  2. `src/pipeline.cpp` `boltAdamStep`：`lrComp = lr/hMax` 原对 tanhBound=0 也生效（物理步长会大 25×），
     已改为 `tanhBound ? lr/hMax : lr`；
  3. 锚定 buffer 逐镜加载：`createBoltBuffers()` 有一次性守卫且 auto 路径为全镜共享的 `anchor.bin`，
     已改为创建期只建零填充 dummy（保绑定 26/27），`optimize()` 在 bolt init 解析后按
     `_bolt_init.txt → _anchor.bin` 逐镜加载，缺失时 hard error。
- **check-grad 判定**：coupling=1 与 coupling=0（legacy）的 S95 Sigmoid 测试均报 ISSUES
  （cosine ≈0.966/0.967，AD/FD ratio ≈0.35/0.34，FD 在 eps 扫描中出现符号翻转）——
  两者逐位一致，判定为分位点损失上 FD 检查的**既有伪差**，与重力耦合无关，记录在案后继续。
- **c0 ≡ Pure Ellipse 实证**：`_eval_lsq_c0`（coupling=0）North_150m = 38.7852 m²，
  与既有 Pure Ellipse 表 38.78 一致 → 334dir 下 c0 列冗余（直接用 CLAUDE.md 既有 B_ideal 表）。
- **Phase 2 闭式补偿**：`scripts/lsq_fit_compensated.py` 已产出 `data/init_comp/` 20 镜
  （h\* init + 逐镜 `_anchor.bin` [G 35×35 | G·h\* 35] + comp_summary.csv）。

**加速决策（2026-07-27 起生效）**

- 快速迭代环路（A/B eval、B\* sanity、Phase 3 消融）全部切到 **110dir（110_sundir_paper.txt）
  训练 + 110dir 验证**（原 334dir 单镜 eval 815s → 110dir ≈270s，3× 加速）；
  `data/init_comp/` 已用 110dir 重新生成（均值场移除率 4.4–37.3%，与 334dir 版趋势一致）。
- 334dir 仅保留给 Phase 4 最终全场表（定性结论以 110dir 筛选，定量终值 334dir 过夜跑批）。
- 注意：110dir 下的 B_ideal 基线需同 sun set 重测（c0 列不再冗余，已排入跑批）。

**进行中**

- A/B eval 110dir 三配置跑批（后台）：`_eval_lsq_c0`（B_ideal@110 基线）、`_eval_lsq_c1`（S95_naive）、
  `_eval_comp_c1`（h\* init，测 Δ_envelope）→ 产出 `analysis/real_gravity_penalty_table.md`，
  与 Phase 0 H1 预测（1.14–3.39×）对照。

**首轮跑批暴露并已修复的 2 个新 bug（2026-07-27 下午）**
1. **`lsq_fit_compensated.py` 活塞模态污染**：斜率设计矩阵有一条近零奇异方向
   （σ≈2e-7，对应螺栓整体同升同降——斜率空间不可见），`rcond=None` 的 lstsq 给 h_comp
   叠了 ~1.3×10⁶ mm 的常数分量（h_star_max_abs 达 1346540mm，comp_summary 自己记录却无人检查），
   渲染时镜面等效下移 1.3km → comp_c1 全场 S95=0。
   修复：`rcond=1e-6` 截断 + |h\*|>0.2m sanity 断言；修复后 max|h\*|=33–54mm，
   补偿移除率不变（4–37%）。已用 110dir 重新生成 `data/init_comp/`。
2. **`runValidation` 重力 bin 陈旧**（`src/pipeline.cpp` bolt 路径）：逐方向 eval 只调
   `updateUniforms + forwardRender`，从不重建表面——法线实际用"上一次 `boltForwardSurface`
   的 cos-θ bin"渲染全部 110 方向。coupling=0 时法线与 bin 无关故无影响（c0 结果有效，
   与既有 Pure Ellipse 表一致）；coupling=1 时 init eval（dir0 的 bin）与 iter-0 eval
   （dir109 的 bin）给出两个都错误的数（East_150m：64.26 vs 45.81，且多个镜子得出
   "重力改善 S95 低于无重力理想"的物理不可能结果）。**首轮 c1 数据全部作废。**
   修复：runValidation 内每方向调 `boltForwardSurface(computeCosTheta(sd,...))`。
   注意：该 bug 影响所有 coupling=1 训练运行的周期性验证（bestS95 选择会被带偏），
   修复是 Phase 2/3 跑批的前提。c0 列不重跑（重力高度陈旧 ≤11mm 视差，文档 §0.1 已证可忽略，
   且与 334dir Pure Ellipse 表逐位一致）。

**二轮跑批暴露并已修复的 bug #4（2026-07-27 晚）：Adam tanh 回写静默夹紧 init**

修复 bug #2 后重跑，c1 出现新的 init/iter-0 分裂（North_150m：init 45.63 vs iter-0 95.91，
CPU/GPU 路径逐位一致、20 镜 iter-0 值彼此可疑地接近 ~115）。逐方向 debug 探针
（`BEZIER_DEBUG_EVAL=1`，runValidation 内打印逐 dir S95/level/表面校验和）定位链条：

1. iter-0 所有方向 S95 一致放大 ~2.1×、level 降至 0.54× → 光斑真实变宽（能量重分布），非 MC 噪声；
2. yGrid 逐方向**精确**下降 1.312762mm（恒常活塞，σ=3.5e-7）→ 指向螺栓整体下移；
3. dump `m_boltHeights` 实锤：**4 个角螺栓 50.6mm → 39.96mm（=0.999×hMax）**，其余逐位不变。

根因：`adamUpdateBolt` tanh 路径无条件执行 `h = hMax·tanh(atanh(clamp(h/hMax)))`，
即使 lr=0 也把超出 tanh 界的 init 螺栓投影到 0.999·hMax=39.96mm。
LS/comp init 的角螺栓 ~50.6mm > 默认 `max_bolt_stroke=0.040` → 第一次 adam 调用即"截肢"表面。
**c0 未暴露的原因**：旧二进制 runValidation 用陈旧表面（bug #2），iter-0 eval 恰好读到
adam 之前的表面，夹紧被掩盖——两个 bug 相互隐藏。历史训练配置全部显式设 0.040，
即所有历史优化运行都从这个夹紧瞬态起步（优化器随后在界内恢复，属既定行为）。

修复（双管齐下）：
- `bolt_optimizer.slang`：`lr==0` 时整个 adam update 提前返回（eval 语义严格化）；
- 全部新实验配置 `max_bolt_stroke: 0.06`（> init 最大 54mm，留 tanh 余量）。

对数据有效性的最终裁决：
- **c0 列（B_ideal@110）有效**：其值=原始 LS 螺栓逐方向 eval，与 334dir Pure Ellipse 表一致；
- **c1/comp_c1 的 init 列有效**（原始螺栓+逐方向表面）；iter-0 列因夹紧作废；
- 修复后 init≡iter0，"Best S95" 重新可信（Phase 2/3 训练跑批的前提）。

**Phase 1 A/B 惩罚表完成（2026-07-27 晚，三轮跑批）**：`analysis/real_gravity_penalty_table.md`。

- **H1 成立（趋势），量级为卷积预测的一半**：实测 S95_naive/B_ideal = 1.001–1.539×
  （South_150m 最大 1.539，North 远镜 ≈1.00–1.01）；与 H3 预测的趋势高度一致
  （Pearson 0.913 / Spearman 0.922），但实测/预测均值仅 0.634 → S95 对斜率方差亚二次响应，
  H3 需加 α<2 修正（"可预测光学"的定量结果）。
- **Δ_envelope（h\* init 收益）**：近场显著（South_150m +5.10、South_300m +3.40、East_150m +3.17 m²，
  消去惩罚的 12–18%）；远场与 North ≈0 或略负。补偿后比值仍 1.006–1.440 > 1 →
  结构性地板存在（H2 定性成立）。
- 物理结论：重力惩罚是**近场 South/East/West 镜的问题**；North 远镜可忽略。

**进行中**：B\* 无重力下界跑批 300m NEWS sanity（`_bound_nograv_300m.json`，110dir/200iter）。

**Phase 2 启动与 36dir 转向（2026-07-27 晚）**

- **范围决策（用户指示，今后一律执行）：训练/消融类跑批只跑典型 300m NEWS 四镜，
  不跑全 20 镜**；已启动任务中 600m 及以远样本全部终止。
  全 20 镜的定量结论以已完成的 110dir 惩罚表为准（Phase 1 已产出）。
- B\*\@110 sanity 数据点：North_300m 无重力端到端优化 iter110 S95=50.08 < B_ideal\@110=51.57 ✓
  （B\* ≤ B_ideal sanity 通过，约 −3%）。110dir 训练实测 ~254s/iter（含验证）→ 200iter×20镜不可行，
  **训练类跑批全部转 36dir**（36_sundir_fast.txt，约 3× 加速；基线 eval 同步生成 36dir 版保持同 sun set 可比）。
- 36dir 资产：`_eval_lsq_c0/c1/_eval_comp_c1` 的 `_36` 变体（c1/comp 已裁剪为 300m NEWS）；
  `data/init_comp_36/`（36dir 均值场重算）；`_bound_nograv_300m_36`。
  `_bound_nograv_field_36`（20 镜 B\*）按上述决策弃用。
- 36dir↔110dir 一致性（c0 全 20 镜已完成）：偏差 ±2.4% 以内（远场 <0.5%），合格。
- Phase 3 消融配置已建（36dir、300m NEWS、h\* init、coupling=1、200iter、lr=4e-4、max_bolt_stroke=0.06）：
  `_fw_tanh_a0`（基线）、`_fw_tanh_a1e3/a1e4/a1e5`（anchor 扫描）、
  `_fw_nt_soft1e5`、`_fw_nt_a1e3_soft1e5/soft1e6`（tanh 解除 + 软墙 ± 锚定）、
  `_fw_tanh_a1e3_b1e2`（弯曲能）。注意 shader 中 bend 与 anchor 共用 regGram——
  对 TPS 双调和插值，弯曲能恰为 hᵀGh（斜率 Gram 二次型），物理上一致，非 bug。

**待办**：36dir eval c1/comp（300m NEWS）→ B\*\@36 300m NEWS（过夜）；
Phase 3 消融分组跑批；Phase 4 差距三分解表（300m NEWS + 110dir 全场表）+ FEA 抽查 + CLAUDE.md 更新。

---

## 0. 诊断结论（本次调查的三个决定性事实，已定量验证）

### 0.1 致命结构缺陷：重力在当前渲染器中光学隐身

`shaders/bolt_common.slang:125-127`（`boltSurfaceAtGrid`）：

```glsl
y  = (disableGravity != 0u) ? 0.0f : sampleGravityUY(...);  // 重力进高度
yu = 0.0f;   // ← 重力不进 u 向导数
yv = 0.0f;   // ← 重力不进 v 向导数
```

法线 `nrm`（:143）只由 `yu/yv` 决定，渲染器采样的是 `nGrid`（`forward.slang:129`）。
**重力只改变光线交点高度（≤11mm 视差，300–1200m 距离上可忽略），从不改变反射方向。**

这精确解释了所有历史结果：
- "LS-Fit(重力开) ≡ Pure Ellipse(重力关)"（North_300m 51.61 = 51.61，逐位级一致）；
- 优化结果必然 ≈ 理想椭圆面——S95 损失根本感受不到重力，最优解当然只剩椭球法线场；
- 导师的批评可被机械地证明：proxy/重力链对光学目标的贡献**结构上为零**（不是"近似为零"）。

### 0.2 重力形变以"支撑间凹陷"为主，35 螺栓 TPS 张量结构性无法补偿

对 `data_proxy/gravity_*.bin`（20 角度 bin）的定量分解（脚本见 Phase 0）：

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

### 0.3 固定螺栓只能消去"年均均值场"，θ 变化分量不可约

对 20 面镜 × 334 太阳方向计算倾角分布与重力场统计：

- North 远镜 θ 范围窄（48–77°），θ 变化分量小（irr_slp≈0.34 mrad）；
- East/West 镜 θ 跨越 1–78°，穿越 **46° NLGEOM 变号点**（重力场方向反转），
  θ 变化分量达 2.5–2.9 mrad——固定螺栓对此完全无能为力；
- 全年均值场的最优固定补偿（斜率空间）总移除率仅 **0.2–22%**（因补偿可达性受 0.2 限制）。

**反射 ×2 后的原始重力斜率预算 2.3–8.5 mrad，与 Buie 太阳宽度 2.2 mrad 同量级甚至更大。**
一旦 0.1 的缺陷被修复，重力将从"光学隐身"变为"光学主导项"——这才是真正值得优化的问题。

### 0.4 诊断总结论

> 当前管线中"优化 ≈ 椭圆拟合"不是优化器的失败，而是因为重力从未进入光学目标。
> 要让 proxy 起真正的优化作用，必须：(a) 修复重力→法线耦合（使其成为真实的光学扰动），
> (b) 用 proxy 的线性性给出**闭式均值场补偿**（proxy 显式做功），
> (c) 把不可达部分（凹陷 + θ 变化）定量归因到硬件，并认证可达下界 B_reachable。

---

## 1. 实验总体设计

### 1.1 核心概念

- **B_ideal**：理想椭圆面 + 无重力 + 斜率误差的年均 S95（已有：CLAUDE.md 参考表）。
- **B\***：无重力下端到端螺栓优化的年均 S95（`disable_gravity:1`，新跑）——光学可达性的经验地板。
- **B_reachable**：有重力时 35 螺栓结构性可达的下界 ≈ 由"补偿后残余斜率预算"预测的 S95。
- **差距三分解**（每面镜）：
  `S95_naive(LS螺栓+真实重力) − B* = Δ_envelope(可闭式补偿) + Δ_tune(可微调) + Δ_irreducible(凹陷+θ变化)`

### 1.2 可证伪假设

- H1：修复斜率耦合后，`S95_naive/B_ideal` 显著 >1（预测 1.3–4×，South/East 近距离最大）。
- H2：闭式均值场补偿 + 锚定微调可将差距缩小，但存在由凹陷决定的硬地板 B_reachable > B*。
- H3：实测 S95 与简化卷积模型 `σ_tot² = σ_sun² + (2σ_slope)² + (2σ_grav,res)²` 的预测趋势一致
  （若一致，论文多一张"可预测光学"图；若不一致，说明 S95 对低阶像差更敏感，需修正模型）。
- H4：有形状锚定时，解除 tanh 界不会发散，且收敛更快/行程更物理。

### 1.3 镜像选择与算力预算

- 快速迭代：300m NEWS 四镜（110dir 训练 / 334dir 验证，~15–50 min/镜/200iter）。
- 最终结论：20 面镜（150–1200m × NEWS）全场表。B* 与框架运行的 334dir × 200iter 约 50 min/镜，
  20 镜 ≈ 17 GPU·h，排队过夜可完成；前期全部用 110dir 筛选。

---

## 2. Phase 0 — 数据审计与诊断定量化（0.5–1 天，纯 Python 只读）

**产出脚本** `scripts/gravity_decomposition.py`（把本次调查的即席分析固化）：

1. 每角度重力 bin：PV/RMS/斜率 RMS/三频带分解（仿射/二次/高阶）；平滑性检查
   （中心差分 vs 大模板差分一致性，排除 CSV→网格插值噪声伪高频）。
2. **46° 变号点审计**：从 `data_proxy/ansys_csv/` 原始 CSV 独立重算 44°/48° 附近的
   `w = uy·cosθ + uz·sinθ`，确认 NLGEOM 膜效应变号是物理的而非提取管线 artifact
   （若 ANSYS 可用，补 1–2 个加密角度；不可用则用 CSV 重算 + 文档记录）。
3. 高度-L2 与斜率空间两种投影的重力可补偿率（每角度 + 每镜年均加权）。
4. 每镜：θ 分布、ḡ（年均均值场）、不可约 θ 方差、补偿后残余斜率预算 →
   按 H3 模型预测 `S95_naive/B_ideal` 与 `B_reachable/B_ideal`。
5. 输出 `analysis/gravity_compensability_report.md`（含全部表格 + 预测）。

**通过标准**：报告给出的预测表完整；46° 变号点有明确结论。

---

## 3. Phase 1 — 重力斜率耦合修复（E0）+ 真实重力惩罚测定（1–2 天）

### 3.1 数据生成扩展（`scripts/generate_proxy_model.py`）

- 重力 CSV→bin 步骤扩展为每角度输出 **3 平面 `[w, dw/du, dw/dv]`**（每 bin 3×1024 float32）：
  中心差分（内部）/单边差分（边界），可选 σ=1px 高斯预平滑（`--deriv-smooth`，默认开）。
  平面顺序：`[w 平面][du 平面][dv 平面]`，保持 20 个 bin 文件与绑定 31–50 不变（每 buffer 变 3 倍大）。
  `gravity_angles.json` 增加 `"format": "w_du_dv_v2"` 标记；旧格式读取时回退 legacy 行为。

### 3.2 Shader 修改

- `shaders/bolt_common.slang`：
  - `_readGravity` 改为 `_readGravity3(binIdx, gridIdx) → float3 (w, du, dv)`（平面偏移 0/1024/2048）；
  - `sampleGravityUY` → `sampleGravityField(gridIdx, lo, hi, t) → float3`（三平面分别 lerp）；
  - `boltSurfaceAtGrid` 增加参数 `uint gravityNormalCoupling`：
    `yu += coupling ? gdu : 0; yv += coupling ? gdv : 0`（:125-127 处）。
- `shaders/bolt_forward.slang:6`：`BoltSurfacePC` 增加 `gravityNormalCoupling` 字段并透传。
- 反向路径无需改动：`renderBackwardBolt` 与 forward 共享同一 `nGrid/yGrid`，
  重力导数是**与参数无关的数据**，AD 链 `∂(y,yu,yv)/∂h_b = (φ_b, φ_b^u, φ_b^v)` 不变。

### 3.3 C++ 管线

- `src/pipeline.cpp:496-517`：重力 bin 加载按 3×1024 float/bin 读取（兼容旧格式警告退出）。
- `boltForwardSurfaceCmd` push const 增加 `gravityNormalCoupling`。
- 新配置键（见 §7）：`gravity_normal_coupling`（默认 1；0 = legacy 幻影行为，供消融/历史对比）。

### 3.4 验证

- 强制重编 shader：`rm build/shaders/*.spv && cmake --build build --config Release`。
- `./build/src/Release/bezier_opt.exe --check-grad configs/bolt_optimize_north_200iter.json`
  必须在 coupling=0 与 1 下都通过（FD vs AD）。
- **A/B 差距表**（核心产出）：20 面镜 × LS 螺栓 init × eval 模式（`iterations:1, lr:0`，334dir），
  coupling=0 vs 1 → `analysis/real_gravity_penalty_table.md`。
  与 Phase 0 的 H1 预测对照（验证或证伪卷积模型）。

---

## 4. Phase 2 — 下界建立 + 闭式重力补偿（1–2 天 + 夜间跑批）

### 4.1 下界 B\*（无重力端到端优化）

- 配置：现有优化配置 + `"disable_gravity": 1`，300m NEWS 先行（110dir），随后 20 镜（334dir）。
- 输出：`results_bound/{name}_BEST_bolts.txt` + history；汇总 B\* 表（对照已有 B_ideal 参考表）。

### 4.2 闭式补偿生成器（新脚本 `scripts/lsq_fit_compensated.py`，基于 `lsq_fit_elliptic.py`）

对每面镜计算：

```
h_shape = argmin_h ||Φh − s_ellipse||²                      （现有逻辑）
ḡ(x,z)  = Σ_dirs w_dir · g(θ_dir)(x,z)                     （年均均值场，权重=DNI或均匀）
h_comp  = argmin_h ||∇(Φh) − ∇(−ḡ)||² = −(AᵀA)⁺Aᵀ·∇ḡ       （斜率空间，闭式）
h*      = h_shape + h_comp                                  （框架初始螺栓）
```

- 输入：`data/ellipse.txt`、训练 sundir 文件、`data_proxy/`（phi + phi_u/v + 新 3 平面重力 bin）。
- 输出：
  1. `data/init_comp/{name}_bolt_init.txt`（h\*，直接喂 `bolt_init_dir`）；
  2. **锚定 buffer**（Phase 3 用）：斜率 Gram `G_bb' = ⟨∇φ_b, ∇φ_b'⟩`（35×35）与 `G·h*`（35），
     存 `data/init_comp/{name}_anchor.bin`（35×36 float32）+ JSON 元数据；
  3. 汇总 CSV：每镜 ‖h_comp‖ 行程 PV（预测 0.2–6mm，应远小于 40mm 界）、补偿移除率、残余斜率预算。

### 4.3 补偿有效性快速验证（不动优化器）

- eval 模式对比（334dir，coupling=1）：`LS init` vs `h* init` → S95 差值 = Δ_envelope 实测值，
  与 Phase 0 预测对照。**这一步已经能向导师展示"proxy 闭式做功"的第一张表。**

---

## 5. Phase 3 — 正则项套件 + 解除 tanh（2–3 天）

### 5.1 总损失设计

```
L(h) = L_S95(h) + λ_E·L_energy(h)          （已有 L1，≥900m 保留）
     + λ_s·(h−h*)ᵀ G (h−h*)                【新】R_anchor：斜率度量信任域
     + λ_b·hᵀ K h                           【新】R_bend：弯曲能量（可选）
     + λ_h·Σ_b max(|h_b|−h_max, 0)²         【新】R_soft：软行程墙（替代 tanh）
```

- **R_anchor**：`G_bb' = ⟨∇φ_b,∇φ_b'⟩` 为斜率 Gram——把优化限制在"物理一致的补偿椭球面"附近，
  度量本身即光学相关量（斜率）。梯度闭式：`∇R_anchor = 2λ_s·G(h−h*)`。
  这是"proxy 抵抗重力"在损失层面的表达：锚点 h\* 已含闭式重力补偿。
- **R_bend**：`K_bb' = ⟨∇²φ_b,∇²φ_b'⟩` 弯曲能 Gram，抑制相邻螺栓交替打架（高频螺栓震荡），
  同时防止优化器徒劳追逐结构性不可达的凹陷形状（那会超出线性 proxy 有效域）。
- **R_soft**：单边二次墙；`tanh_bound:0` 时替代 L4 tanh 成为唯一的行程约束——
  检验"有锚定的情形下硬界是否多余"（H4）。`tanh_bound:1` 保持现状（默认，向后兼容）。

### 5.2 实现位置（全部二次型 → 闭式梯度，GPU 开销可忽略）

- `shaders/bolt_optimizer.slang` `adamUpdateBolt`（:28-66）：
  - 新增两个 RO buffer：`regGram`（35×35，按需为 G 或 K 各一份）与 `anchorTarget`（35，= G·h\*）；
  - 每线程(螺栓 b)：读 G 第 b 行与 h 做点积，`grad += 2λ_s((Gh)_b − (Gh*)_b) + 2λ_b(Kh)_b`；
    软墙：`|h_b|>h_max` 时 `grad += 2λ_h(|h_b|−h_max)·sign(h_b)`；
  - `tanh_bound==0` 分支：`ε≡h`，`dh/dε=1`，跳过 atanh/tanh 与 lr/h_max 补偿（lr 语义变为物理步长，
    需在 config 文档与实验记录中注明，lr 初值建议 4e-4×h_max≈1.6e-5 起扫）。
- `src/pipeline.cpp:947-972`（boltAdamStep）：push const 扩展 `{λ_s, λ_b, λ_h, tanh_bound}`；
  初始化时按 `bolt_init_dir` 的 "auto" 约定加载 `{name}_anchor.bin`（λ_s>0 时必需，缺失则报错）。
- 仅 bolt 模式支持；`use_bspline:1` 时打印 WARNING 忽略（v1 范围外）。

### 5.3 λ 标定协议与消融矩阵

- 标定：iter 0 记录 ‖∇L_S95‖，取 λ_s 使 ‖∇R_anchor‖≈ρ·‖∇L_S95‖，ρ∈{0.1,0.3,1,3} 扫描定膝点；
  λ_b 取使 ‖∇R_bend‖≈0.1·‖∇R_anchor‖ 起步；λ_h 取使单螺栓越界 1mm 时墙梯度≈0.3·‖∇L_S95‖。
- 消融（300m NEWS，110dir 训练 / 334dir 验证）：
  `tanh{on,off} × anchor{0,ρ} × bend{0,λ_b}` 共 8–12 组 + λ_s 膝点细扫。
- 记录：最终 S95、收敛曲线、行程 PV/max、面型保真度（与 h\* 的斜率空间距离）、
  能量保持率、各正则项梯度量级占比（论证正则不过载主损失）。
- 选择规则：取"最终 S95 与无锚定差距 <0.5% 内最大的 λ_s"为推荐值。

---

## 6. Phase 4 — 全场验证与差距分解报告（1–2 天 + 跑批）

1. **20 面镜总表**（334dir）：`B_ideal`（已有）→ `B*`（4.1）→ `S95_naive(LS+coupling=1)`（3.4）
   → `S95_framework(h* init + anchor + soft wall, tanh off)` → **差距三分解表**
   （Δ_envelope / Δ_tune / Δ_irreducible，与 Phase 0 预测并列）。
2. FEA 抽查：框架最优螺栓 × {29.5°, 58.5°} × 2 镜（`scripts/post_fea_validation.py` 现有管线），
   确认行程在线性 proxy 有效域内且面型与 FEA 一致。
3. **（可选 Tier-2）布局敏感度**：解析估算 `w∝a⁴`（间距⁴缩放）→ 凹陷斜率 ∝ a³，
   预测 6×6/8×6 布局的 B_reachable 移动；若 ANSYS 可用，`generate_proxy_model.py all-ansys
   --bolt-layout configs/bolt_layouts/6x6.json` 生成对照数据验证 1 个点。
   这是"proxy 做真正优化"的收口论证：**地板由硬件决定，框架能量化并优化这个权衡**。
4. 产出：`analysis/bound_gap_decomposition_report.md` + 更新 `CLAUDE.md`
  （新配置键、重力耦合修复说明、历史结果可比性声明：coupling=1 后旧 S95 不可直接对比）。

---

## 7. 新增配置键汇总

| 键 | 默认 | 说明 |
|---|---|---|
| `gravity_normal_coupling` | 1 | 重力导数是否进入法线（0=legacy 幻影行为，供消融） |
| `anchor_lambda` (λ_s) | 0.0 | 形状锚定强度；>0 时需 `{name}_anchor.bin` |
| `bend_lambda` (λ_b) | 0.0 | 弯曲能量正则强度 |
| `soft_stroke_lambda` (λ_h) | 0.0 | 软行程墙强度（单边二次） |
| `tanh_bound` | 1 | 1=L4 tanh 现状；0=无界物理空间 + 软墙 |

配置改动点：`src/config.h:13-108`（字段）、`src/config.cpp:65-156`（解析）、
`pipeline.cpp:947-972`（Adam push const）、`bolt_optimizer.slang:14-24`（push const 结构体）。

---

## 8. 文件改动清单

| 文件 | 改动 |
|---|---|
| `scripts/generate_proxy_model.py` | 重力 bin 输出 3 平面 [w,du,dv] + 平滑选项 + 格式标记 |
| `scripts/gravity_decomposition.py` | 新建（Phase 0 分析固化） |
| `scripts/lsq_fit_compensated.py` | 新建（h\* init + 锚定 buffer 生成） |
| `shaders/bolt_common.slang` | `_readGravity3` / `sampleGravityField` / `boltSurfaceAtGrid` 耦合开关 |
| `shaders/bolt_forward.slang` | push const 透传 `gravityNormalCoupling` |
| `shaders/bolt_optimizer.slang` | 锚定/弯曲/软墙梯度 + `tanh_bound` 分支 |
| `src/pipeline.cpp` | bin 加载(3×)、push const、anchor buffer 加载 |
| `src/config.h/.cpp` | 5 个新配置键 |
| `configs/_eval_*.json` 等 | 新增若干 eval/消融配置 |
| `CLAUDE.md` | 新机制说明 + 可比性声明（Phase 4 末） |

---

## 9. 验证清单（每步的"完成"判据）

- [ ] Phase 0：补偿率/不可约分量/预测表齐备；46° 变号点有结论。
- [ ] Phase 1：`--check-grad` 在 coupling∈{0,1} 均通过；20 镜 A/B 差距表与 H1 预测对照一致（或解释偏差）。
- [ ] Phase 2：B\* 表 ≤ B_ideal（ sanity：无重力优化不应差于椭圆）；h_comp 行程 PV < 10mm；
      h\* init 的 eval S95 ≤ LS init（Δ_envelope ≥ 0）。
- [ ] Phase 3：λ 扫描 Pareto 图；tanh off + anchor on 组不发散且行程 ≤ 软墙+10%；
      正则梯度占比记录完整（主损失不被淹没）。
- [ ] Phase 4：20 镜差距三分解表；实测 vs 预测趋势一致性结论（H3）；FEA 抽查通过；
      CLAUDE.md 更新。

---

## 10. 预期结果与分支预案

- **最可能**：H1 成立（重力惩罚 1.3–4×），闭式补偿消去其中 5–20%，微调再消去少量，
  剩余为结构性凹陷地板。**这本身就是对导师最硬的回答**：
  "proxy 不仅给出闭式补偿，还精确归因了不可达部分（支撑间距/玻璃刚度），并给出布局改进方向"。
- **若 H1 不成立**（修复后惩罚仍 ≈0，说明渲染器对凹陷法线不敏感或我的斜率分析高估）：
  则重力在该 stylized 面板下确实光学无关，框架转为"下界认证 + 锚定正则改善收敛与稳健性"，
  结论改写为"重力在此支撑设计下可被一次性出厂调节吸收，残余可忽略"——同样由框架定量认证。
- **若 h_comp 行程超界**（预测不会）：退化为斜率空间带权重投影（大权重给小行程螺栓）或对 h_comp
  加 trust-region 截断。
- **若 tanh off 发散**：保留 tanh，报告"硬界在无锚定时必要、有锚定时冗余"的对照结论。

---

## 11. 工作量估计

| Phase | 内容 | 时间 |
|---|---|---|
| 0 | 数据审计 + 诊断报告 | 0.5–1 天 |
| 1 | 斜率耦合修复 + A/B 差距表 | 1–2 天 |
| 2 | B\* 跑批 + 闭式补偿 + eval 验证 | 1–2 天（+过夜跑批 ~17 GPU·h） |
| 3 | 正则套件 + tanh 消融 | 2–3 天 |
| 4 | 全场表 + FEA + 报告 + 文档 | 1–2 天 |
| 合计 | | **约 1–1.5 周**（含跑批） |

快速通道（先与导师对齐）：Phase 0 + 1 + 4.2/4.3（闭式补偿 eval 表），**1.5–2 天出核心结论**。

---

## 进度日志 2026-07-28（投稿规划支线）

- 后台跑批：`_eval_lsq_c1_36` / `_eval_comp_c1_36` 完成（exit=0）；B\*@36 四镜跑批中（North 全量 200 iter + ESW 120-iter 封顶切换方案，cron `10540284` 每小时 13/38 分监控平台早停，预计当晚 ~23:00 全部完成）。
- 36dir 基线定稿（300m NEWS）：ideal(c0) 51.32/65.68/73.51/65.60；naive(c1) 51.31/77.90/98.33/78.07；comp init(c1) 51.75/76.71/94.90/76.83。comp init 仅回收惩罚 10–14%（E/S/W），North 上 comp 反而略差（+0.44 m²，免罚镜补偿即失配）。
- 德令哈 300m NEWS 全年倾角分布已算（110dir）：North θ∈[36.1°,64.5°] 中位 50.9°、35% 时间落 40–50° 低凹陷区；South θ∈[0.2°,56.6°]、24% 时间 θ<20°。几何解释了惩罚非均匀性。
- 投稿规划文档重写：`docs/tvcg_submission_gap_analysis.md` → `docs/submission_strategy_and_outline.md`（README/CLAUDE.md 引用已同步）。结论：硬约束（CCF-A 或中科院一区）下首选 **AEI**（1 区 Top, IF 9.9, 首轮 ~9 周），强备选 Applied Energy（需补全场能量收益）；TVCG 仅剩 CCF-A 通道且 2025 中科院已降 2 区、无能源先例，桌拒风险中高；Solar Energy（2 区非 Top）不再满足硬约束，旧版首发路线作废。识别 5 篇必须精读区分的竞争性先例（canting-DRT 2025、aiming-DMCRT 2025、Inverse-DL-RT 2025×2、Pargmann 2024）。
- NCM Model 调研结论（`D:/Code/heliostat_optimize/NCM Model`）：Fast-NCM 为 7.9 万参数 MLP（非 CNN），输入仅标量 σ_S 高斯斜率误差，无法接收面型空间结构 → 不能用于我们的"理想光斑"逐面型预测；可借鉴其 erf 闭式可微渲染与 Adam 参数拟合管线（`unizar_fit.py`），以及"NN 预测解析光斑参数"作为未来螺栓→S95 代理的模板。
- **计时口径修正**：此前"82s/iter"实为含验证的迭代耗时；North 200 iter 实测总耗时 5901.6s（均值 ~29.5s/iter，验证迭代 ~82s、普通迭代 ~24s）。B\* 四镜总时长从"18h"修正为 ~6.5h，当天即可完成。North 平台期在 iter 100 后出现（best 49.7719@iter100，iter110–190 未再刷新）——验证了 ESW 120-iter 封顶方案恰好砍掉平台尾巴。
- **North B\*@36 = 49.7719**（init 51.3327，−3.0%；vs B_ideal 51.32 低 1.55 m²）。无重力地板显著低于椭圆 LSQ 理想值，差距四层分解的第一块拼图到位。

---

## 进度日志 2026-07-28（二）：B\*@36 四镜齐备，Phase 3 启动

**B\*@36（无重力端到端优化下界）与差距四层分解**（S95 m²，300m NEWS，36dir）：

| 镜 | B_ideal (LSQ无重力) | B_naive (重力) | B_comp (重力闭式init) | B\* (无重力优化) | 重力惩罚 naive−ideal | comp 回收 | 理想→B\* 余量 |
|---|---|---|---|---|---|---|---|
| North | 51.32 | 51.31 | 51.75 | **49.77** (−3.0%) | −0.01 | — | 1.55 |
| East | 65.68 | 77.90 | 76.71 | **65.00** (−1.0%) | 12.22 | 9.7% | 0.68 |
| South | 73.51 | 98.33 | 94.90 | **73.07** (−0.6%) | 24.82 | 13.8% | 0.44 |
| West | 65.60 | 78.07 | 76.83 | **64.68** (−1.4%) | 12.47 | 9.9% | 0.92 |

要点：① 四镜 B\* 均低于 B_ideal（余量 0.44–1.55 m²），300m 处椭圆 LSQ 离无重力地板已很近，真正的战场是重力惩罚段（E/S/W 12–25 m²）；② North init 自洽性校验通过（B\* 跑批 init 51.3327 vs c0 eval 51.32）；③ North 平台期 iter 100 后出现（best@100），据此 ESW 与 Phase 3 均改为 120/150 iter 封顶。
**Phase 3 启动**（任务 bash-0vw59byn）：8 组顺序跑批，300m NEWS、36dir、coupling=1、comp init（data/init_comp_36）、150 iter 封顶、lr=4e-4（已核实 lrComp 分支：tanh 与物理两种模式零点物理步长一致，nt 组无需改 lr；CLAUDE.md 旧建议已修正）。

---

## 进度日志 2026-07-28（三）：Phase 3 首组 a0 出结果——端到端回收率仅 ~15%，地板效应显著

**`_fw_tanh_a0`（tanh、无正则、comp init、重力全开、150iter）四镜结果**：

| 镜 | init | best S95 | 对比 naive | 对比 ideal | 重力惩罚回收率（端到端累计） |
|---|---|---|---|---|---|
| North | 51.75 | 50.34 | 51.31 → 50.34 | 51.32 | —（免罚镜，优化修复了 comp 失配并降至 ideal 之下） |
| East | 76.71 | 76.21 | 77.90 → 76.21 | 65.68 | 13.8%（comp init 单独 9.7%，端到端仅再+4%） |
| South | 94.90 | 94.28 | 98.33 → 94.28 | 73.51 | 16.3%（comp init 单独 13.8%） |
| West | 76.83 | ~76.21 (iter130) | 78.07 → ~76.2 | 65.60 | ~15% |

**关键结论（预注册假设的判决性数据）**：端到端优化在重力下几乎推不动 S95——所有镜 iter ~80 后即硬平台（±0.03 m² 内波动）。comp init + 端到端合计仅回收惩罚的 ~15%，远未达到子空间投影预言的 26–38% 可达斜率方差对应的量。**35 螺栓结构的重力地板是硬约束**，论文叙事从"逼近 B\*"修正为"认证地板 + 解释地板 + 指出结构性出路（支撑布局/刚度，而非螺栓调节）"。North 侧优化降到 50.34（< naive 51.31、< ideal 51.32，距 B\* 49.77 仅 0.57）说明优化器本身工作正常，地板不是优化失败而是物理。

**估算错误更正**：此前"每组 ~1.2h、今晚 23 点完成"系算术错误（把每镜 75 分钟误当每组）。实测 ~30s/iter（coupling=1 无额外开销）→ 每组（4 镜×150iter）≈5h。处置：剩余 7 组已砍至 100 iter（平台证据充分），并新增第 9 组 `_fw_tanh_naiveinit`（LSQ init 端到端，检验地板是否 init 无关，链跑完后补跑）。预计总时长 ~27h（明晚 ~20 点 8 组齐）。


---

## 进度日志 2026-07-29（一）：锚定扫描与 tanh 解除结果；超时事故；双机分工

**新增完成组（36dir，S95 m²）**：

| 组 | N | E | S | W | 结论 |
|---|---|---|---|---|---|
| a1e3（锚定 1e3） | 50.42 | 76.26 | 94.33 | 76.18 | ≈基线（噪声内） |
| a1e4（锚定 1e4） | 50.48 | 76.27 | 94.26 | 76.14 | ≈基线 |
| a1e5（锚定 1e5） | 50.73 | 76.33 | 94.47 | 76.29 | 单调略差——强锚定压制仅存增益，**锚定冗余成立** |
| nt_soft1e5（解除tanh+软墙） | 50.37 | 76.21 | 94.29 | 76.12 | **与 a0 完全一致（East 四位小数相同）——硬界不是地板成因** |

至此五重证据（子空间投影 26–38%、端到端硬平台、锚定扫描、无界化、North 对照）同指**结构性硬地板**。

**事故**：链条 `bash-0vw59byn` 于 09:15 撞 20h 超时被杀（死在 nt_a1e3_soft1e5 开头，无损失）；剩余 3 组以 `bash-xatj04c5`（disable_timeout）重启，预计今晚 ~21:30 收工，随后自动汇总+睡眠。

**双机分工**：笔记本收尾 3 组（nt_a1e3_soft1e5/1e6/tanh_a1e3_b1e2）；台式机接 ① `_fw_tanh_naiveinit`（第 9 组）② `_bound_nograv_300m`（B\*@110，可降 150iter）③ 新建 `_fw_tanh_a0_110`（a0@110 终稿回收率）。结果汇合方案见 `docs/experiment_handoff.md` §5.3（笔记本 push 受限，已生成 bundle 后备）。

---

## 进度日志 2026-07-29（二）：台式机 4 组结果判定无效——幻影重力事故；v2 bins 未提交系根因

**笔记本侧完成**：`_fw_nt_a1e3_soft1e5`（36dir, 100iter, coupling=1）→ N 50.39 / E 76.20 / S 94.24 / W 76.19，12527s，日志含 20 行 `Loaded gravity_*deg.bin (3-plane, ...)`——重力正常生效，与 a0/a1e3 各组一致（地板依旧）。

**台式机事故判定**：其 4 组消融（nt_a1e3_soft1e5/1e6、tanh_a1e3_b1e2、tanh_naiveinit）声称"全组收敛至 B\*、地板系 init 困住优化器、锚定充分"——**全部无效，系幻影重力（phantom gravity）环境下的假象**。判决证据：

1. **init 值出卖环境**：`tanh_naiveinit` 的 LSQ init 四镜 S95 = 51.32/65.68/73.51/65.60，与**无重力** B_ideal 逐位相等。重力真实生效时 LSQ init 必须等于 B_naive（51.31/77.90/98.33/78.07）——E/S/W 相差 12–25 m²，不可能是噪声。
2. **comp init 同样**：台式机 comp init E/S/W = 65.42/73.73/65.04（理想面量级），笔记本同数据同配置下 = 76.71/94.90/76.83。
3. **耗时**：439s/组 vs 笔记本 12527s/组（28×）。幻影重力下问题退化为无重力优化，数十 iter 即收敛触发早停（patience=15），与"全组轻松到 B\*"互洽。

**根因（笔记本侧失误）**：v2 三平面重力 bins（2026-07-27 14:50 本地重生成，12288 B/bin）**从未 commit**——`git status` 中 `data_proxy/gravity_*.bin` 全部为未提交修改，HEAD/66d5048 内仍是旧版 4096 B 单平面 bins。台式机 pull 66d5048 拿到旧 bins，加载器走 legacy 分支（du/dv 补零 → 法线不吃重力斜率 → **重力光学隐形**，即 Phase 1 已修的 normal-coupling bug 在台式机上复活）。台式机日志"更新了 data_proxy/（v2 三平面重力格式）"一句不属实。

**台式机验证口令**（一步坐实）：`grep -m2 "Loaded gravity" logs/_fw_tanh_naiveinit.log`——必显示 `legacy 1-plane, du/dv=0` 而非 `3-plane`。

**附带价值**：台式机 4 组数据恰好构成"重力光学失效签名"的标准样本（init==B_ideal、全组→B\*、早停、~28× 加速），可作为后续任何机器环境自检的对照基线。

**处置**：① 笔记本立即提交 v2 bins（+ansys_csv 更新）；② 台式机 pull 后 `grep` 自检确认 3-plane，再跑其分工任务（`_bound_nograv_300m` / `_fw_tanh_a0_110` / 可选重跑 naiveinit）；③ 台式机原 4 组结论作废，不并入消融表；④ 分叉教训：**凡含 data_proxy 的实验，交接清单必须校验 bins 字节数（12288）与加载日志格式串**。

---

## 进度日志 2026-07-29（三）：Phase 3 消融跑批收尾——8/9 组齐，地板结论终稿

**收尾 3 组结果**（36dir, 100iter, coupling=1, 重力 3-plane 正常加载，各 ~3.5h/组）：

| 组 | N | E | S | W | 结论 |
|---|---|---|---|---|---|
| nt_a1e3_soft1e5 | 50.39 | 76.20 | 94.24 | 76.19 | ≈基线 |
| nt_a1e3_soft1e6 | 50.39 | 76.20 | 94.24 | 76.19 | **与 soft1e5 四位小数逐位相同** → 软行程墙全程未激活，行程约束不是地板成因 |
| tanh_a1e3_b1e2 | 50.46 | 76.24 | 94.34 | 76.15 | ≈基线（弯曲能无额外增益） |

**Phase 3 消融终表**（36dir, 300m NEWS, best S95 m²）：

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
| naiveinit | LSQ init 无正则 | — | — | — | —（台式机待重跑） |

**判决（六重证据闭环）**：全部 8 组 E/S/W 地板锁定在 ~76.2/94.3/76.2 m²（极差 ≤0.13 m²，Monte Carlo 噪声量级），与参数化形式（tanh/无界）、锚定强度（0–1e5）、行程约束（硬界/软墙/无）、弯曲能均无关。E/S/W 重力地板是 **35 螺栓支撑布局的结构性硬约束**，终稿叙事确立为"认证地板 + 解释地板 + 结构性出路（支撑布局/刚度优化）"。

**剩余工作**：① 第 9 组 naiveinit 由台式机修复重力环境后重跑（预期仍落在同一地板，作 init 无关性的最后确认）；② 台式机 110dir 任务（`_bound_nograv_300m`、`_fw_tanh_a0_110`）；③ Phase 4：差距三分解表 + FEA 抽查 + CLAUDE.md 更新。
