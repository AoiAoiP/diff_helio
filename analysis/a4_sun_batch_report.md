# A4 实验报告：多 sun 合批 + vkCmdUpdateBuffer

**日期**: 2026-07-20
**分支**: `feature/a4-sun-batch`（worktree `L:/Code/bezier_opt_a4`，基于 master `0d7a2a6`）
**测试**: North 300m 单镜，36 太阳方向，lr=4e-4 constant，RTX 4070 SUPER
**结论**: **位精确一致；性能中性（收益低于运行间噪声）**

---

## 1. 实现

GPU-S95 路径从"每 sun 一次 submit"（36 submit/iter）改为按 `sun_batch_size`（新增配置键，默认 6）分组 submit：

- 逐 sun 可变数据只有 SunParams UBO（13 floats，仅 sun.direction 逐 sun 变）与 `sunBatchFlat` 重力包（8 floats）；receiver/heliostat/helioPos/aim 四个 UBO 跨 sun 不变，每迭代 host 上传一次（`updateStaticUniforms`，自 `updateUniforms` 拆出）。
- 每组一次 submit 内，逐 sun 以 `vkCmdUpdateBuffer` 注入 UBO + 重力包（录制时拷贝，无 host 往返），sun 间插一条全 `pipelineBarrier`——`boltBackwardPassCmd` 无尾屏障，且流内 UBO 覆写存在"前 sun 读 → 后 sun 写"竞争，必须显式排序。
- λ>0 的 iter-0 需逐 sun 回读 `s95State` 捕获 E_ref → 该迭代自动回退 group=1（36 submit），其余迭代正常分组。
- CPU-S95 / MSE 路径零改动；`BEZIER_S95_GPU=0` 回退不受影响。
- 改动量：`src/config.{h,cpp}`、`src/pipeline.{h,cpp}` 共 +74/−36，无 shader 改动、无新增 GPU buffer。

与旧 Phase 4 的区别：旧尝试用 push constants 传 per-sun 参数且融合 dispatch（寄存器压力，−20% 退步）；本实现保持逐 sun 串行 dispatch，只合并提交边界，数学上可证位精确。

## 2. 一致性验证（主结果）

| 对比 | 结果 |
|---|---|
| 30-iter batch=1/6/36 vs master（`results_merge_smoke`）逐点 | max\|ΔLoss\|=0, max\|ΔS95\|=0（三档全部） |
| 200-iter batch=6 vs master（`results_north_200iter_p0p1`）逐点 | **200/200 点 max\|Δ\|=0** |
| 200-iter `BEST_bolts.txt` / `STROKE_bolts.txt` | **逐字节相同** |

位精确是设计使然：dispatch 序列、数据、顺序与原路径完全一致，仅提交粒度变化。

## 3. 计时 A/B（30-iter 交替，程序自报 optimize 循环总时）

| 运行 | 时间（s） |
|---|---|
| master #1/#2/#3 | 61.7 / 55.3 / 55.7（均值 **57.6**） |
| batch=6 #1/#2/#3 | 61.6 / 48.0 / 64.5（均值 **58.0**） |
| batch=1 | 53.2 |
| batch=36 | 58.4 |

同配置单次散布 ±15~30%（本机运行间噪声一贯如此，见 `p0_validation_report.md` §3），两均值差 0.4s（0.7%）**远在噪声带内——A4 性能中性**。

理论核算与之一致：节省 30 submit/iter × ~0.1ms（fence + cmd 分配 + 提交 + 等待）≈ 3ms/iter，相对 ~1500ms/iter 的 GPU 工作量仅 ~0.2%，低于可测下限。B4 文档预期的 15~25% 建立在"A1 大幅削减 GPU 计算量后 dispatch 开销占比上升"的前提上；A1 实测无损仅 −4.8%，该前提不成立（与 `arcaim_comparison.md` §2.5 的优先级下调判断一致）。

## 4. 处置建议

- 代码保留在 `feature/a4-sun-batch` 分支；收益为零但成本也为零（位精确、无维护负担的配置项）。是否并入 master 取决于是否想要 `sun_batch_size` 这个旋钮——例如未来 GPU 计算量被 A5 大幅削减后，submit 开销占比上升，本项会自动变得有价值（同 B4 原始逻辑）。
- 若并入，建议同时把本结论回写 `arcaim_comparison.md` A4 行（预期 15~25% → 实测中性，附前提条件）。

## 5. 复现

```bash
# worktree L:/Code/bezier_opt_a4, branch feature/a4-sun-batch
./build/src/Release/bezier_opt.exe configs/_tmp_a4_smoke_b{1,6,36}.json  # 30-iter 三档
./build/src/Release/bezier_opt.exe configs/_tmp_a4_200_b6.json           # 200-iter
bash scripts/_a4_ab.sh                                                    # 计时 A/B（master vs 三档）
```
