# ARCAim (diffspt) 方法论对比分析

**日期**: 2026-07-20
**对比对象**: `L:\Code\diffspt-main`（ARCAim：全镜场瞄准点可微优化）vs 本项目（镜面面型物理可实现可微优化）
**参考材料**: 论文《ARCAim: Hardware-accelerated differentiable ray tracing for adaptive heliostat aiming》（Visual Informatics 2026, DOI: 10.1016/j.visinf.2026.100349）、diffspt 源码、`diffspt-main/experiment_report.md`

**两个项目的定位差异**：diffspt 优化的是**每面镜的瞄准点**（全场数千面镜，每镜 2 个自由度），本项目优化的是**单镜面型的螺栓调节量**（35 螺栓 → TPS 物理代理 → 面型变形）。两者共享同一技术底座：接收面驱动的收集式 Monte Carlo + Vulkan compute + Slang 自动微分。

---

# 一、diffspt 代码如何实现论文第三章方法论

## 1.1 章节 → 代码映射总览

| 论文章节 | 内容 | 代码落点 |
|---|---|---|
| §3.1 问题陈述与目标函数 | 能量尺度不变形状先验 + 效率项 | `diffspt/core/metrics.cpp:150-176`、`diffspt/shaders/loss.slang:22-76` |
| §3.2 管线总览 | 有界参数化→Vulkan 前向→混合目标→缓存路径反向→Adam | `diffspt/core/app.cpp:1164-1243`（`submit_optimization_step`，单 command buffer 一次提交） |
| §3.3 硬件加速 RFDD 仿真 | 接收面驱动逆向 MCRT + Vulkan ray query + BLAS/TLAS | `diffspt/shaders/planar.slang:294-316`、`diffspt/core/geometry.cpp`、`diffspt/shaders/ray_query.slang` |
| §3.4 缓存路径可微优化 | tanh 有界参数化 + 可见性门控 + 路径重放反向 | `diffspt/shaders/loss.slang:358-395`、`planar.slang:513-577` |

## 1.2 §3.1 目标函数的实现（loss 设计核心）

论文式 (8)：ℒ = ℒ_shape(**F**,**P**)² + λ/η。代码对应两部分：

**形状项**（`metrics.cpp:150-176`）：

```cpp
// L_shape = ||F||²||P||²/⟨F,P⟩² − 1，即 tan²∠(F,P)
const auto shape_loss = flux_norm_sq * prior_norm_sq / (flux_prior_dot * flux_prior_dot) - 1.0;
return max(0.f, shape_loss) + lambda_loss * reference / actual;   // + λ/η
```

实现的是 tan²θ 形式（式 4 的平方），与论文式 (8) 的 ℒ_shape² 一致。当 **P** = **1** 时退化为 RSD²（变异系数平方）。**能量尺度不变**的数学本质：对 F 乘任何正系数，形状项不变——太阳位置、DNI、云遮改变绝对能流时目标不失效。这是相对 DiffNEG 等"绝对目标匹配"方法的核心卖点（云遮实验：ARCAim RSD=0.204 vs DiffNEG 0.803）。

**形状先验 P 的构造**（`metrics.cpp:92-148` `build_ideal_flux`）：沿接收面高度方向中间 `evenly_ratio`（0.7~0.85）比例平顶、两端高斯尾巴（FTG），圆周方向均匀；总量归一化到 `reference_flux_sum`（初始瞄准的前向总能量）。AFD 模式下（`metrics.cpp:63-88`）二分搜索 σ 使峰值 ≤ afd_max——**物理约束只用于生成先验，不进梯度**。

**GPU 端逐像素梯度**（`loss.slang:22-37`）的数值技巧：

```slang
// Keep the reported loss normalized, but scale the backprop seed back up so
// f32 gradients do not collapse under Adam's epsilon floor.
dLoss *= max(lossParams.referenceFluxSum, 1.0f);
```

反向种子整体乘 referenceFluxSum（~1e5），防止 f32 梯度被 Adam 的 epsilon 地板吞掉。

**效率项** `λ · reference/actual`：总通量越小惩罚越大，等价于惩罚溢光。λ 是唯一权衡旋钮（论文 λ 扫描：λ=0 时 RSD 0.050/OE 0.593，λ=1.6 时 0.205/0.654，主实验取 λ=1.0）。

## 1.3 §3.3 硬件加速 RFDD 仿真的实现

**采样结构**：`scene.cpp:168` 定义 `ray_count = receiver_pixels × spp × heliostat_count`——对每个（接收像素, 镜子, 样本）三元组评估一条光路，是**接收面收集式 Monte Carlo**，与本项目同构。每条光路的能量（`planar.slang:44-103`）：瞄准点+太阳方向决定镜面法向（`normalize(aimV+sunDir)`）→ 几何因子 `area·cos/r²·大气衰减` → 反射方向与日轮中心角距 → Buie/pillbox/Gaussian 日轮亮度加权。

**硬件 RT 的精确角色**：RT core **只做遮挡查询**——每条光路两次 inline ray query（`ray_query.slang:5-28`：太阳方向阴影 + 反射方向阻挡，按 InstanceID 排除自身）。**不用 ray tracing pipeline shader，全部能量计算在 compute shader 里**，避免 shader table 开销。加速结构：`geometry.cpp:411-433` 每类几何一份 BLAS（27,135 镜场仅 1~3 份），每轮迭代由 compute shader 重算实例变换后**仅重建 TLAS**（`geometry.cpp:266-298`）。

**两级零贡献裁剪**（吞吐关键）：
- tile 级：CPU 预计算每面镜在接收面的角度 footprint，只 dispatch 覆盖的 tile（`geometry.cpp:591-625`）；
- 逐光线级：`passesRaytracerCovarianceCull`（`common.slang:276-369`）把镜面孔径+日轮+斜率误差合成像平面二维高斯，接收像素落在 4σ×3 椭圆外直接跳过。

**采样**：预生成 2^20 加扰 Sobol→逆误差函数转高斯的样本池（`sampling.cpp:83-126`），shader 内 Wang-hash 按 (ray, heliostat, pixel, spp, seed) 索引；**每轮迭代只换 seed（哈希偏移），池不变**——前后向采样严格一致（相关采样，降梯度方差），迭代间又是随机优化步（论文 Algorithm 1 第 4 行"刷新 Sobol 偏移"）。

## 1.4 §3.4 缓存路径可微优化的实现

**可微边界**：前向能量函数标 `[Differentiable]`，backward 用 Slang `bwd_diff`（`planar.slang:562-568`）。**唯一可微输入是 aimWorldPoint（float3）**；采样位置、高斯扰动、位置等全部 `no_diff`。可见性（0/1 二值门控）被 AD 天然当常数——不连续处零梯度。即"连续部分精确 AD + 不连续 detach"路线，**不做** edge sampling/reparameterization，工程上零额外光线。

**缓存路径反向（Path Replay 的 SPT 适配）**：前向把"这条光路有贡献"用 `InterlockedOr` 写进 bitmask（`planar.slang:281-284`），反向只处理置位光路、**不重发 ray query**（`planar.slang:534-537`）。反向种子是 dL/dF 纹理，逐光线导数 × 像素 loss 梯度，wave 归约按镜累积。

**两个对效果关键但未写进论文细节的工程手段**：
1. **通量先滤波再算 loss**：可分离高斯 σ=4.9px/r=14 滤波 MC 通量（`filter.slang:16-17`，注释明言"不是美颜模糊"，是 MC 噪声重建）；**dL/dF 用同一核再滤波一次**（对称核滤波是自伴算子，数学上严格等价于"先滤波再算 loss"的伴随），把梯度支撑从亮斑扩散到邻域——这是 spp=1 也能收敛、瞄准点略偏出接收面也能收到拉回梯度的关键。
2. **Pillbox 日轮替代梯度**（`sunshape.slang:32-47`）：前向保持精确硬截断，反向换成 smoothstep 斜坡，并留 1e-16 微小正值让前向 validity cache 覆盖整个替代梯度支撑集——`hard + smooth - no_diff(smooth)` 让前向值不变、反向走平滑支路。

**有界参数化与优化器**：Adam 变量是 2 维无约束 ε，经 tanh 窗口映射到接收面（式 9，`loss.slang:358-365`）——**边界内建于参数化，无投影无罚函数**。Adam 全在 GPU（`loss.slang:367-395`），超参 **β1=0.6**（动量极短，配合 MC 梯度噪声）、x/y 学习率分离（0.04/0.16）。链式最后一环 d(world)/d(ε) 用 eps=1e-3 中心差分（`loss.slang:376-381`）——全链唯一数值微分。

**全流程零回读**：loss 统计（sum/sumSq/dot/normSq）全 GPU 归约，CPU 每轮只经环形 buffer 异步读 48 字节 metrics；单 command buffer 提交 + fence 异步 + 协程日志线程，GPU 不等 CPU。

## 1.5 性能数字（experiment_report.md + 论文）

- 前向吞吐稳定 **13.3~13.7 亿光线/秒**（RTX 4070 SUPER），镜数 4.3×/光线 8× 时吞吐不变——线性扩展；
- 优化单轮：6282 镜（spp=1）0.03~0.15 s；27135 镜（spp=4）**~0.75 s/轮**，其中前向+TLAS 重建 ~700 ms 占绝对主导，反向仅 ~15 ms（validity 缓存的功劳），Adam ~5 ms；
- 论文 Table 2：50k 镜场相似光线预算下吞吐为 SolTrace/OptiX 的 **~43×**，显存 1/28（275 MiB vs 7,779 MiB）；
- 在线优化：6282 镜 **6.3 s**、27,135 镜 **11.9 s**（30 迭代，RTX 3090），两个场上均快于 DiffNEG / DiffMCRT / GA 数个量级；
- 优化质量（Table 1）：三个太阳时刻同时优于 GA 的均匀性与可微基线的光学效率，峰值始终低于 AFD 上限。

---

# 二、bezier_opt 的进一步优化空间

## 2.1 当前状态对齐（避免重复建议）

| diffspt 手段 | bezier_opt 状态 |
|---|---|
| tile 级稀疏剔除 | ✅ 已做（activePixelList，~3950 像素） |
| loss 全 GPU、CPU 微量回读 | ✅ 已做（GPU 协作二分 S95，每 iter 回读 4 字节） |
| 免原子/定点归约 | ✅ 已做（gradPartialTile 12 KB） |
| command buffer 合批 | ✅ 已做（每 sun 单次 submit） |
| 可见性位缓存、反向零遮挡查询 | ✅ 已做（rayValidity bitmask，`shaders/bolt_backward.slang:149`） |
| 逐光线协方差裁剪 | ❌ **未做（最大缺口）** |
| 编译期特化 | ❌ 未做（sun_type 等运行时分支） |
| 低 spp + 滤波降噪 | ❌ 未做（仍是 32×32=1024 确定性网格积分） |
| 有界参数化约束 | ❌ 未做（螺栓行程无约束） |
| 效率/能量损失项 | ❌ 未做（`energy_target` 是配置里的死字段，src 中无任何引用） |

## 2.2 Loss 设计空间（6 条，按价值排序）

### L1. S95 损失的能量尺度盲区 → 加效率项（最重要，直接借鉴式 8）

当前损失 L = Σσ(6·(f/S95_level − 1)) 与 ARCAim 的形状项有同样的数学性质：**对 F 乘任意正系数，level 同比缩放，损失不变**——只度量形状紧凑度，对总截获能量无感知。当前螺栓行程较小（~36 mm）时溢光变化不大，盲区未暴露；但若未来优化自由度增大（更多螺栓、更大行程、多镜协同），优化器完全可能通过牺牲截获能量来缩小 S95。`configs` 里的 `energy_target: 1.0` 字段在 `src/` 中没有任何引用，说明此项曾规划但未落地。

建议形式（照 ARCAim 的量纲设计）：

```
L = S95_loss / (M·σ(6))  +  λ · E_ref / E_actual
```

第一项归一化为"超阈值像素占比"（无量纲 ∈[0,1]），E_ref 用零初始化面的总通量，E_actual 为当前总通量（GPU 上 finalizeFlux 已有，归约一个 sum 几乎免费）。λ 作为可解释的运行点参数扫描（ARCAim 用 λ∈[0,1.6]），可直接为论文多一张 Pareto 图。

### L2. 梯度只在 sigmoid 阈值带内非零 → 借鉴"平滑三件套"，但需谨慎

S95 sigmoid 损失的本质缺陷：只有 f ≈ level 附近的像素 |σ′| 显著非零，深斑内和远场外像素梯度≈0。diffspt 的解法是三件套：通量高斯滤波（σ=4.9px）+ dL/dF 同核伴随滤波 + 截断处替代梯度。本项目 Buie 日轮天然光滑（不需要第三件），但前两件可以考虑——**然而有本项目自己的教训作约束**：GPU 直方图 1.5 W/m² 偏差就导致 sigmoid 饱和（`optimization_plan.md` Phase 3 回退），说明 S95 对通量扰动极度敏感，滤波引入的偏差必须先量化。

可行的折中：只在反向路径上滤波 dL/dF（前向 S95 仍用原始通量），不改变 loss 语义、只加宽梯度支撑集，数学上不再严格但偏差可控，是低风险的 A/B 实验。

### L3. 冻结噪声 vs 每迭代换种（diffspt Algorithm 1 第 4 行）

`shaders/common.slang:8` 的 `kSamplingSeed = 12345u` 是编译期常量——斜率误差高斯扰动在所有迭代中是**同一组实现**。这带来梯度稳定（无迭代间 MC 噪声），但把单一噪声实现的偏差烤进了最优解：每个网格点的"专属"斜率误差固定，优化可能过拟合这个特定实现。diffspt 的做法是池不变、每轮迭代 seed = base + iteration（相关采样保前反向一致，迭代间随机化）。

建议：加一个 per-iteration seed（UBO 传 iteration 号混入 `random01` 的 seed 参数），然后做对比：同一组最终螺栓，用多个不同 seed 重算 S95 取平均——如果换 seed 后 S95 变差，说明当前结果确实存在噪声过拟合。对论文的稳健性论证也是加分项。

### L4. 物理可实现约束未参数化 → tanh 有界参数化 + 行程正则

本项目的卖点是"物理可实现优化"，但目前：螺栓行程**无任何硬约束**（`shaders/bolt_optimizer.slang` 中无 clamp），33~37 mm 的行程是优化自然停下来的，不是被限制的；也没有行程/斜率正则项。ARCAim 式 (9) 的 tanh 参数化可直接搬用：

```
h_b = h_max · tanh(ε_b)
```

边界内建于参数化，无需投影、梯度在边界处自然软化。再叠加一个小的行程正则 λ_h·||h||²，就能把"S95 vs 执行器成本"做成显式 Pareto 权衡——这正是 ARCAim 用单一 λ 管理"形状 vs 能量"的同一哲学，对"物理可实现"的叙事是强化而非旁枝。

### L5. 多工况加权

当前 36 个太阳方向等权平均。已有 `data/738_sundir_year.txt` 全年数据——按年 DNI/出现频率加权 loss（w_sun·L_sun），优化目标从"36 工况均匀最优"变成"年发电量期望最优"，物理意义更强，实现只改梯度累加权重。

### L6. 前期 warm-start 平滑代理（可选）

S95 是非平滑序统计量类指标，前期梯度信号稀疏。可借鉴 ARCAim"形状先验"的思想，前 N 轮用参与率（participation ratio）PR = (ΣF)²/ΣF² 这类**处处有稠密梯度、且同样能量尺度不变**的紧凑度度量做 warm-start，再切到 S95。当前收敛已经不错（50~80 轮收敛），此项收益限于迭代数压缩，优先级最低。

## 2.3 程序加速空间（按优先级）

### A1. [P0] 逐光线零贡献裁剪——当前最大的加速缺口

前向是接收像素 × 1024 个确定性镜面网格点（`shaders/forward.slang:119-136`），但对任一接收像素，**绝大多数网格点的反射方向根本不在日轮内**（贡献严格为零或 ~1e-30），却仍走完整个双层玻璃折射（3 次 normalize + sqrt + TIR 分支）+ Buie 求值。diffspt 的 `passesRaytracerCovarianceCull` 就是干这个的。

曲面使精确协方差椭圆更难算，但有更朴素的版本：**先用宏观曲面法向（不含玻璃、不含斜率扰动）算一次 reflect，若反射方向与日轮中心角距 > θ_max + k·(斜率误差 + 玻璃偏折余量)，直接 skip**。玻璃偏折上界可离线估一个保守值。`analysis/diffspt_performance_optimization_plan.md` 估计可裁 80~95% 的 (pixel, sample) 对——**前向 5~20× 的加速全部来自这里**，反向同理（validity 缓存已帮反向跳过无效光路的 AD，但前向找出这些无效光路本身仍花了全价）。这是唯一一个量级级的剩余机会。

### A2. [P1] 编译期特化

`sun_type`、fresnel 路径、glass 开关等经 uniform 运行时分支（`shaders/forward.slang:112` `getSunShapeType()` 后的分派）。按 diffspt 的 Slang 泛型模式（`planar.slang:47`），为 (sun_type × reflection 模式 × grid_size) 预编译少数特化，消除热循环分支，预期 1.5~2×。

### A3. [P1] reflection-only 快速路径（带保真度权衡）

双层玻璃折射是前向单光线成本的大头。diffspt 的 `REFLECTION_ONLY` 模板参数在只关心能量分布时给 3~5×。本项目的物理论述里双层玻璃可能是卖点之一，建议做成配置开关：**优化内循环用 reflection-only，最终 S95 评估与论文数据用全模型**——先量化两者 S95 偏差再决定。

### A4. [P1] 多 sun 合批 + vkCmdUpdateBuffer

已有文档（`analysis/remaining_optimization_opportunities.md` B3/B4）：36 sun 串行 submit → 结构化 buffer 传参合批（旧 Phase 4 用 push constants 退步 20%，教训是走 buffer 不走 push constant）。配合 A1 后 GPU 计算量大减，dispatch/同步开销占比上升，本条价值随之放大。预期合计再省 15~25%。

### A5. [P2] 课程式网格精度（类双后端思想）

diffspt 用 raytracer（高保真）+ covariance（解析高斯散射，106 s→36 s 而 CV 仅差 0.4%）双后端。本项目的等价物不必是解析卷积模型（工作量大），可以是**网格分辨率课程**：前 60% 迭代用 16×16 网格积分（单光路成本降为 1/4），后 40% 切 32×32 精修。梯度噪声早期本来就大，粗网格积分误差会被 Adam 平均掉。实现只需 grid_size 可中途切换 + yGrid/nGrid 重算，风险低，预期总时间再省 30~40%。

### A6. [P2] Adam β1 随噪声特性调整

若采纳 L3（每迭代换种），梯度 MC 噪声增大，届时可借鉴 diffspt 的 β1=0.6（短动量抗噪）；当前冻结噪声下 0.9 合理，不必动。

## 2.4 不建议照搬的 diffspt 设计

- **硬件 RT / TLAS 重建**：diffspt 每轮 ~700 ms 的大头是 TLAS 重建+遮挡查询，因为它要处理 27k 镜间阴影。本项目是单镜（或少量镜）面型优化，镜间遮挡不在模型内，引入 ray query 是纯成本。**注意**：若未来扩到全场面型优化，遮挡不可回避，届时直接照抄 `ray_query.slang` 的双查询 + BLAS/TLAS 分层即可。
- **2^20 Sobol 大池**：本项目已删掉 1.5 GB 池改内联 Box-Muller，这是对的——采样点是确定性网格，只需要高斯扰动，hash 生成比池读取更省。
- **27k 批量 dispatch 维度**：问题规模不同，本项目的瓶颈在单镜 1024 采样内层，不在 dispatch 次数。

## 2.5 汇总优先级

| 优先级 | 项 | 预期收益 | 风险/成本 |
|---|---|---|---|
| P0 | A1 逐光线角度预裁剪 | 前向+反向 3~10× | 中（需保守余量验证 S95 不变） |
| P0 | L1 效率项（λ/η） | 防能量牺牲解；论文多一张 Pareto 图 | 低（GPU 上加一次归约） |
| P1 | L4 tanh 行程约束 + 行程正则 | 强化"物理可实现"叙事 | 低 |
| P1 | A2 编译期特化 | 1.5~2× | 低 |
| P1 | L3 每迭代换种 + 多种子验证 | 稳健性论证（论文向） | 低，需 A/B |
| P1 | A3 reflection-only 开关 | 3~5× 前向（内循环） | 需先量化保真偏差 |
| P2 | A4 多 sun 合批 + cmdUpdateBuffer | 15~25% | 中 |
| P2 | L2 dL/dF 反向滤波 | 收敛域加宽 | 中（S95 敏感教训） |
| P2 | A5 网格课程 16²→32² | 30~40% 总时间 | 低 |
| P3 | L5 年 DNI 加权 / L6 warm-start | 物理意义/迭代数 | 低 |

---

## 三、一句话总结

**加速上最大剩余杠杆是逐光线零贡献裁剪（A1）**——diffspt 的 43× 吞吐优势有相当部分来自同类机制；**loss 上最值得移植的是 ARCAim 式 (8) 的"无量纲形状项 + λ/η 效率项"双项结构（L1）和 tanh 有界参数化（L4）**——前者补上 S95 的能量盲区，后者把"物理可实现"从结果属性变成内建约束。

---

## 参考文件索引

| 文件 | 用途 |
|------|------|
| `L:\Code\diffspt-main\experiment_report.md` | diffspt 性能基准（用户实测） |
| `L:\Code\diffspt-main\diffspt\shaders\common.slang:276-369` | 协方差裁剪实现 |
| `L:\Code\diffspt-main\diffspt\shaders\planar.slang:47-103` | 特化参数 + 能量计算 |
| `L:\Code\diffspt-main\diffspt\shaders\loss.slang:22-76, 358-395` | loss 梯度 + tanh 参数化 + GPU Adam |
| `L:\Code\diffspt-main\diffspt\core\metrics.cpp:150-176` | 形状先验 loss CPU 参考实现 |
| `analysis/diffspt_performance_optimization_plan.md` | 本项目此前的 diffspt 对比加速方案 |
| `analysis/remaining_optimization_opportunities.md` | 本项目剩余优化项（B1~B5） |
| `optimization_plan.md` | 已实施 Phase 1/2/5 与 Phase 3 GPU S95 回退教训 |
