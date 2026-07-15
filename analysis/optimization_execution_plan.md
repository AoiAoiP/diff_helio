# bezier_opt_desktop 优化执行计划

**制定日期**: 2026-07-15（Phase A 完成后修订）
**当前基线**: master `9a6b8d7` — **实测 ~2.1s/iter 均值（626.6s / 300 iter），S95 = 52.3465 m²**
> ⚠️ 原文档基线 "1.8s/iter" 为 stale-shader 失真数据（渲染了半个接收器），
> 已被 [phase_a_experiment_report](./phase_a_experiment_report.md) §0 修正。
**GPU**: RTX 4070 SUPER
**综合来源**: [worktree_baseline_fixed_analysis](./worktree_baseline_fixed_analysis.md) · [remaining_optimization_opportunities](./remaining_optimization_opportunities.md) · [failed_experiment_gpu_s95](./failed_experiment_gpu_s95.md) · [gradient_decomposition_analysis](./gradient_decomposition_analysis.md) · [diffspt_performance_optimization_plan](./diffspt_performance_optimization_plan.md) · [phase_a_experiment_report](./phase_a_experiment_report.md)

---

## 0. 现状快照

已合入 master 并验证的优化（相对原始基线 `ff1f48d` 7.6s/iter 已 4.2×）：

| Phase | 内容 | 效果 |
|:---:|------|------|
| 1 | 内联 Wang hash + Box-Muller | −1.5 GB gaussianPool，−11.6B 全局读/iter |
| 2 | Command Buffer 合批 (RawComputePass) | vkQueueSubmit 288→72/iter |
| 5 | InterlockedAdd 定点数归约 | 368 MB boltGradPartial → 12 KB |

当前每 sun 耗时分布：Forward batch ~52%，Backward batch ~40%，readFlux+S95 ~4%，CPU 上传 ~4%。
**显存问题已基本解决**，剩余优化全部是时间维度；主要开销集中在 renderForward / renderBackwardBolt 两个大 dispatch（合计 ~80%）与 CPU↔GPU 同步。

---

## 1. 负面清单（已证伪，不再尝试）

| 方案 | 实验结果 | 结论 |
|------|------|------|
| CAS 浮点原子加 (Wave B2) | 8.5s/iter（恶化 2.7×），高争用 CAS loop | ❌ 永久排除；含 `bwd_diff` 的 shader 中 `InterlockedCompareExchange` 不可用 |
| GPU S95 固定 bin 直方图 (Phase 3) | ~1.5 W/m² 系统偏差 → sigmoid 饱和 | ❌ 精度不合格 |
| **GPU S95 自适应 1024-bin (2026-07-15 实验)** | 精度达标 (0.01%) 但**性能零收益**；readFlux 仅占 <0.5% 时间 | ❌ 已回退。移出主线路线图 |
| Forward+Backward 单 submit 合并 | 5.0s/iter（退步 2×），pipeline 序列化 | ❌ 2-submit 结构允许 GPU 排空 pipeline，合并反而有害 |
| Push constants 传多 sun 参数 (Phase 4) | ~20% 退步 | ❌ 改用 structured buffer（见 Phase B） |
| **host-visible buffer 改 vkCmdUpdateBuffer** (Phase A 实验) | persistent-mapped 的 uploadBuffer 本是零同步 memcpy，改内联反多付 transfer+barrier | ❌ vkCmdUpdateBuffer 只用于 device-local 小 buffer |
| **热路径 GPU 读 host-visible buffer** (Phase A 实验) | activePixelList 误建 host-visible → 每 workgroup 一次 PCIe 读，+1s/iter | ❌ 热路径只读 buffer 一律 device-local |

## 1.1 范围外（明确不做，非实验证伪而是需求决策）

| 方向 | 排除理由 |
|------|------|
| **降低 SPP** (32²→28²/25²) | 势必增加蒙特卡洛噪声、影响实验精度。**精度优先，SPP 保持 32² 不动** |
| Bezier 模式相关优化（梯度分解、gradPartial 定点化等） | Bezier 模式对当前项目无优化意义 |
| 全场（多定日镜）批量 dispatch | 当前无全场仿真需求 |
| reflection-only 快速路径 | 对当前项目无意义（需要完整的 2 层玻璃光学） |

> **对 15:08 路线图的修正**：`remaining_optimization_opportunities.md` 中的 B2（GPU S95）已被 16:33 的实验证伪——它假设 readFlux 是显著瓶颈，实测占比 <0.5%。其"合并 submit"收益改由 Phase B（多 sun 批量 + 保留 CPU S95）实现。

---

## 2. Phase A — 移植已验证优化 ✅ 已完成（2026-07-15，结果低于预期）

> 实测详情见 [phase_a_experiment_report](./phase_a_experiment_report.md)。
> **要点**：数值逐位等价（S95=52.3465、行程 32.997mm 与基线完全一致）；
> 交替对照中位加速 **~15%**（63s vs 76s @30iter），远低于原预期 1.6×。
> 原因：被剔除像素在基线中本就被半面剔除早退（近零成本空转组），
> "旧 master 已验证 1.8→1.1s" 的说法经考古证伪——稀疏剔除从未接线到 shader。
> 额外收获：发现并修复 stale-shader 构建缺陷（影响所有历史性能数据）。

### A1. 稀疏像素剔除 ✅

CPU 预计算 `activePixelList`（精确复刻 shader 半面剔除判据，over-inclusive
容差），forward/backward dispatch 7850→3950。数值逐位等价。

### A2. vkCmdUpdateBuffer 内联更新 ✅（精细版）

**仅**对 device-local 的 `sunBatchFlat` 使用（消除每 sun 一次 staging
submit + vkQueueWaitIdle，36 次/iter）；host-visible mapped UBO 保持
memcpy 上传（本就零成本，改内联反而负优化）。

---

## 3. Phase B — 多 sun 批量提交，减少 GPU/CPU IO（中期，3–5 天）

**核心洞察（对旧方案的两处修正）**：
1. 传参用 **structured buffer**（现有 `sunBatchFlat` binding 51 扩容为 6×per-sun 参数数组），不用 push constants（已证伪）；
2. **不依赖 GPU S95**——保留 CPU S95，但按 batch 分摊同步：

```
┌─ Submit 1: 6 个 sun 的 forward 批量 ──────────────────┐
│ boltForwardSurface (1,1,6)  — 6 sun 并行               │
│ renderForward ×6 (或 Z 维=6) → fluxPartial[6 sun 段]   │
└─ submitAndWait ───────────────────────────────────────┘
CPU: readFlux ×1 (6×7850 floats, 一次回读) → 6 次 S95 二分
┌─ Submit 2: 6 个 sun 的 loss + backward 批量 ──────────┐
│ computeS95Loss ×6 → renderBackwardBolt ×6 → reduce/project │
└─ submitAndWait ───────────────────────────────────────┘
```

- **前提**：`fluxPartial`(6 sun 段)、`yGrid`/`nGrid`(kSunBatchSize=6) 等 buffer 本就按 batch 分配，基础设施现成
- **预期**：submit 72→12/iter，fence wait 节省 ~72ms/iter；readFlux 同步 36→6 次/iter；6 sun 的 workgroup 合并提升 GPU 占用率 → **~1.05s → ~0.85s/iter**
- **风险**：中。①寄存器压力（Phase 4 退步的另一嫌疑），需 profile 确认 occupancy；②backward 的 gradPartialTile 原子累加跨 sun 共享目标槽，天然可行（梯度本来就对 sun 求和），但需验证定点数量程不溢出（6 sun 累加 vs 当前 1 sun，缩放因子 1e5 需复核）
- **回退线**：若 6-sun 批量退步，退到 2-sun 或 3-sun 批量，收益/风险按比例缩放

**Phase B 验收标准**：同 Phase A；额外核对逐-iter loss 曲线与串行版本一致（浮点求和顺序变化允许 <0.1% 漂移）。

---

## 4. Phase C — 解析协方差裁剪 + 剩余 IO 削减（长期，1–2 周）

Phase A/B 收敛后，剩余时间几乎全部在 renderForward / renderBackwardBolt 的逐 (pixel, sample) 计算上。本阶段沿两条已确认保留的思路深化：

### C1. 解析协方差裁剪（移植 diffspt）★★★ 本阶段主项

A1 的稀疏剔除是**二值的**（像素是否面向定日镜，裁 ~51%）；协方差裁剪是**连续的**——对每个 (pixel, sample) 对做高斯椭圆预判，把落在能量椭圆截断半径之外的对直接跳过：

1. 对当前太阳方向，计算定日镜面元在接收器图像平面上的投影协方差椭圆
2. 检查 receiver pixel 的 Mahalanobis 距离是否在椭圆截断半径内
3. 椭圆外的 (pixel, sample) 对直接 return，不进入玻璃光学计算

- **参考实现**：`L:\Code\diffspt-main\diffspt\shaders\common.slang:276-369`（`passesRaytracerCovarianceCull`）
- **适用点**：forward 与 backward 共用同一判据（backward 的 bwd_diff 重放路径同样受益），预期裁剪 80–95% 的无效对
- **预期**：叠加在 A1 之上，render 两个大 pass 再降 2–5×（保守估计，需实测椭圆命中率）→ **~0.85s → ~0.3–0.5s/iter**
- **精度保障**：裁剪阈值（截断半径，如 4σ）作为可配参数；用 S95 收敛曲线对照验证阈值不引入偏差，必要时放宽到 5σ。**这是纯裁剪，不降 SPP，命中的样本仍是全精度计算**
- **风险**：中。椭圆参数计算需针对本项目的 bolt 变形曲面调整（diffspt 是刚性 facet）；每 iter 螺栓高度变化会改变曲面法向分布，椭圆需按 iter 重算（成本极低，1 次小 dispatch）
- **工作量**：~1 周（含阈值标定实验）

### C2. 剩余 GPU/CPU IO 清点与削减 ★（条件触发）

Phase B 之后每 iter 剩余的 CPU↔GPU 往返：

| IO 点 | 频次/iter | 现状 |
|------|:---:|------|
| readFlux（6×7850 floats） | 6 | Phase B 已分摊，保留（CPU S95 是精度锚点） |
| boltHeightGradient 回读（35 floats） | 1 | 供 CPU 端 Adam 更新 |
| 螺栓高度上传（35 floats） | 1 | Adam 更新后回传 GPU |
| sun UBO / sunBatchFlat 上传 | 6 | A2 已改 vkCmdUpdateBuffer |

可选深化：**GPU 端 Adam**——35 个参数的 Adam 更新移到 GPU（1 个 35 线程的小 dispatch），消除梯度回读+高度上传两次往返，metric 记录改为异步低频回读。

- **触发条件**：仅当 C1 落地后 profile 显示这两次往返 ≥5% 每 iter 时间才做（方法论第 1 条；当前估计 <1%，大概率不触发）
- **风险**：低，但收益也低——列在此处是为了完整覆盖"减少 GPU/CPU IO"这条思路的终点，防止后续重复调研

**Phase C 验收标准**：同 Phase A；C1 额外要求裁剪阈值扫描实验（4σ/4.5σ/5σ）证明 S95 收敛与不裁剪版本等价。

---

## 5. 里程碑与预期

> ⚠️ 原表的历史对比链（7.6s → 1.8s → …）建立在 stale-shader 失真数据上，已废弃。
> 下表以 2026-07-15 实测真基线为唯一参照；后续阶段预期在动手前须先 profile 重估。

| 阶段 | 实测/预期 | 相对真基线 | 状态 |
|------|:---:|:---:|:---:|
| **master `9a6b8d7` 真基线** | **626.6s / 300 iter（~2.1s/iter）** | 1× | ✅ 实测 |
| + Phase A（稀疏剔除 + sunBatch 内联更新） | 中位 −15%（交替对照 63s vs 76s @30iter） | ~1.15× | ✅ 实测 |
| + B 多 sun 批量 | 待 profile 后重估（72 fence waits/iter 仍在） | ? | 待做 |
| + C1 协方差裁剪 | 待 profile 后重估（依赖椭圆命中率实测） | ? | 待做 |

全程 SPP 保持 32²，收敛精度不做任何妥协（Phase A 已验证逐位等价可达成）。

---

## 6. 方法论约束（来自失败实验的教训）

1. **动手前先测瓶颈占比**。readFlux 教训：占比 <0.5% 的环节做 GPU 化不可能有收益。每项优化启动前，先用 GPU timer / Nsight 确认目标环节 ≥5% 总时间。
2. **每步以收敛质量为硬门槛**：300 iter，S95 = 52.35 ± 0.1 m²，螺栓行程等价。速度回归但收敛劣化 = 失败。
3. **不以牺牲精度换速度**：SPP 固定 32²；一切裁剪必须是保守裁剪（椭圆阈值可配、可验证），命中样本全精度计算。
4. **含 `bwd_diff` 的 shader 禁用 `InterlockedCompareExchange`**（Slang 下行为不可预测）；原子累加一律 `InterlockedAdd` 定点数。
5. **submit 合并不是默认收益**：合并前后都要 profile；当前 2-submit 结构允许 GPU 在 CPU 处理期间排空 pipeline，盲目合并会序列化。
6. **每项优化独立分支、独立计时、独立验收**，避免多项混合后无法归因（Wave 系列的经验）。
7. **热路径 GPU 读取的 buffer 必须 device-local**（Phase A 教训：host-visible 列表 buffer 每 workgroup 一次 PCIe 读 → +1s/iter）。
8. **host-visible persistent-mapped buffer 的 uploadBuffer 是零成本 memcpy**，不要改成 vkCmdUpdateBuffer；内联更新只对 device-local 小 buffer 有意义。
9. **性能对比必须交替短跑取中位**：本机背景负载噪声可达 ±40%（同版本 66→104s），单次长跑对比会得出错误结论（Phase A 曾被误判为 −30% 回归）。
10. **改 shader 后核对 `shaders/*.spv` 与 `build/shaders/` 一致性**（stale-shader 构建缺陷已修复，但这是所有历史数据失真的根源，保持警惕）。
