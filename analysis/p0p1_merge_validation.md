# P0+P1 合并树验证纪要

**日期**: 2026-07-20
**分支**: `feature/p1-specialization-tanh-seed`（基于 master `26f1d2e`，含 P0 再集成）
**测试**: North 300m 单镜，36 太阳方向，lr=4e-4 constant，RTX 4070 SUPER

---

## 1. 合并树构成

P1 会话的工作树在四项 P1 改动（A2 编译期特化 / L3 逐迭代种子 / L4 tanh 参数化 / A3 reflection-only）之上，已再集成 P0 两项（A1 逐光线预裁剪、L1 效率项）的 config / common.slang / forward.slang / pipeline.cpp 部分，UBO 槽位按协调版分配（`sunp[10]=iterationSeed`，`sunp[11]=cullCosCutoff`）。合并审查发现 **P0 的 `s95_gpu.slang` L1 效率项 shader 实现缺失**（C++ 侧 push constants 已就位但 shader 未消费，`lambda_energy>0` 会成为静默空操作），本次从 `feature/p0-raycull-effloss` 补移植（`S95LossPC` + eff 梯度/份额逻辑）。

A3（reflection-only 快速路径）经 P1 会话评估后**放弃**：配置项仍解析但光路固定全折射（`common.slang` / `pipeline.cpp` 中 `was reflectionOnly` 标注）。

## 2. 验证结果

| 检查 | 结果 | 结论 |
|---|---|---|
| 全量编译（6 个新特化 SPIR-V 入口 + L1 push constants） | 通过 | — |
| 30-iter 冒烟（cull=1, λ=0）iter 0 vs `results_s95gpu` iter 0 | Loss=52239.953125 / S95=227.3420，**两侧完全一致** | 前向+损失路径数值零漂移 |
| 同配置 iter ≥1 vs 历史轨迹 | 微小偏离（iter1 48584.5 vs 48587.8） | L4 tanh 按设计改变轨迹，零点邻域步长等价 |
| λ=0.1（30-iter）vs λ=0 | iter-0 相同（λ 按设计在 iter 0 关闭）；iter-1 loss 偏移 **+28,265** ≈ 理论 λ·M·E_ref/E = +28,260 | L1 在合并树精确生效 |
| 200-iter 全量参考（默认开关：cull=1, λ=0, tanh on, 固定种子） | Best S95 = **50.0476 m²**（init 227.3464，−78.0%），max stroke 35.7 mm | 与 pre-P1 参考 50.0387 一致（Δ=0.02%），tanh 界（40 mm）未触 |
| 背靠背计时 A/B（30-iter 交替各 2 次） | 合并树 50.7/45.9 s，P0-worktree 48.5/54.0 s | 均值 48.3 vs 51.3 s，**差在运行间噪声内**（±10%）；P1 各项性能中性 |

200-iter 参考运行曾录得 412.6 s（vs P0 隔离验证 296.8 s），经 A/B 判定为环境噪声（GPU 争用/时钟波动）而非合并树回退——与 `p0_validation_report.md` 记载的运行间 ±25% 噪声一致。

## 3. 备注

- P1 会话 11:52 的基线运行失败（`results_p0_baseline` 中 ERROR）原因为当时 build 未完成（无 exe），非代码缺陷；本次从头编译后全部运行正常。
- `data_ansys_20bin/` 与 `data_vsm_mnvn_tik32/` 已归档至 `data_proxy_old/`（现行数据为 `data_proxy/`，无配置引用旧路径）。
- 行为变化：L4 tanh 参数化始终启用，iter ≥1 优化轨迹与 pre-P1 不同；逐位复现历史结果需回退 `26f1d2e`。

## 4. 复现

```bash
./build/src/Release/bezier_opt.exe configs/_tmp_merge_smoke.json    # 30-iter, cull=1, λ=0
./build/src/Release/bezier_opt.exe configs/_tmp_merge_eff.json      # 30-iter, cull=1, λ=0.1
./build/src/Release/bezier_opt.exe configs/_tmp_north200_p0p1.json  # 200-iter 参考
```
