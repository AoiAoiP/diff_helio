# GPU S95 Cooperative Search —— 消除 CPU↔GPU 来回传

**日期**: 2026-07-19
**状态**: 已完成并验证（200-iter A/B 对比通过，已作为默认路径）
**相关文档**: `analysis/arcaim_comparison.md`（含 Phase 3 教训与 P0/P1 实施结果）、`analysis/failed_experiment_gpu_s95.md`（Phase 3 失败分析）

---

## 1. 问题定位

### 1.1 旧路径（baseline `a62244d`）

`optimize()` 每 iter × 每 sun direction 的执行序列：

```
forward + backward(β)          → submit 1, wait
readFlux()                     → memcpy 1050×1050 float (4.4 MB) GPU→CPU
CPU percentileThreshold(0.95)  → 排序/二分求 S95 阈值
computeS95LossCmd(threshold)   → submit 2, wait   （阈值作为 uniform 传回 GPU）
clearFluxGradient              → submit 3, wait
```

即每个 sun direction **3 次 submit + 1 次 4.4 MB 读回 + 1 次 CPU 阈值计算**。

### 1.2 实测开销（基线插桩，36-sun 快速配置）

`s95cpu` 计时块（readFlux + CPU 阈值 + S95-loss submit 合计）：

```
总耗时: 6117 ms / 200 iter ≈ 30.6 ms/iter
```

占当时 ~161 ms/iter 的约 **19%**。这是纯粹的"为拿一个标量阈值而付的同步税"。

### 1.3 为什么不能直接复用 Phase 3 的 GPU 直方图

`analysis/failed_experiment_gpu_s95.md` 已记录：Phase 3 用 **256-bin 固定范围直方图** 在 GPU 上估 S95 阈值，省掉了读回，但 bin 分辨率引入 ~1.5 W/m² 的系统偏差，梯度方向被污染，最终优化结果变差。教训是：**S95 阈值必须保持与 CPU 二分相同的精度语义**，任何"近似阈值"都不可接受。

---

## 2. 方案：GPU 协作二分（cooperative binary search）

核心观察：程序要的不是"排序"而是"一个阈值标量"。二分查找本身完全可以搬进 GPU——只是从"单线程串行二分"改成"单 workgroup 256 线程协作二分"：

- 每轮迭代，256 个线程各统计一个候选区间的计数（`f > mid`），
- groupshared 归约得到全局计数，与 `0.95 × total` 比较，
- 全员按相同规则收缩区间（`> 0.95` 取上半，否则取下半），
- 20 轮后区间内任意点即为与 CPU 版语义一致的阈值（精度 ~1e-6 相对）。

**语义与 CPU `percentileThreshold` 完全对齐**：相同的 20 轮、相同的 `f > mid` 计数、相同的 `> 0.95` 收缩方向。不存在 Phase 3 的量化偏差。

### 2.1 新执行序列

每 sun direction 合并为 **单次 submit**：

```
forward → backward(β) → computeS95FindLevel → computeS95LossBUF → clearFluxGradient
（一次 submit，一次 wait；中间无任何 CPU↔GPU 传输）
```

- `computeS95FindLevel`：单 workgroup（`numthreads(256,1,1)`，dispatch 1 group），读 flux 缓冲，输出阈值到 `m_s95State`（binding 52，4 floats）。
- `computeS95LossBUF`：从 binding 52 读阈值，定点 ×1e3 原子累加标量 loss 到 `m_lossAccum`（binding 53，1 uint）。两个 buffer 均为 hostVisible，host 侧直接读日志用，无额外传输。

### 2.2 回退开关

`BEZIER_S95_GPU=0` 环境变量可切回旧 CPU 路径（用于 A/B 对比与排障），默认走 GPU 路径。

---

## 3. 实现清单

| 文件 | 改动 |
|---|---|
| `shaders/s95_gpu.slang` | 新增。`computeS95FindLevel` + `computeS95LossBUF` 两条目 |
| `CMakeLists.txt` | SHADER_SOURCES + s95_gpu.slang；SHADER_ENTRIES + 两条目 |
| `src/pipeline.h` | 新管线/缓冲区成员、两个 dispatch 方法声明 |
| `src/pipeline.cpp` | 管线与 descriptor（binding 52/53，writes 50→52）、`optimize()` 主循环合并为每 sun 单 submit、`BEZIER_S95_GPU` 开关 |
| `CLAUDE.md` / `README.md` | 文档同步 |

关键实现细节（都是踩过的坑）：

1. **归约沿用 forward.slang 的 `WaveActiveSum` 模式**（结果仅 wave-0 有效），不用显式树形归约——后者因多一轮 barrier 反而更慢。
2. **"无能量"判定必须用 groupshared 的 `gs_total` 做统一分支**。最初用各线程本地值做早退，导致 workgroup 内分支发散、barrier 两侧线程数不一致 → 挂死/错误结果。所有线程必须走相同的 barrier 路径。

---

## 4. 验证结果

### 4.1 正确性

- **history 曲线对比**（200 iter，36-sun 快速配置，CPU vs GPU 路径）：loss 差 < 0.1%，S95 差 ≤ 0.08 m²，阈值语义一致。
- **Best S95**: CPU 50.0520 m² vs GPU 50.0387 m²（差 0.03%）。
- **stroke**: 36.043 mm vs 35.973 mm。
- **`--check-grad` 回归**：S95 sigmoid sign 一致率 97.1%、cosine 0.96，与文档基线一致，未引入梯度污染（Phase 3 的病灶）。

### 4.2 性能（200-iter 同机 A/B，36-sun 快速配置）

| 路径 | 总耗时 | 每 iter |
|---|---|---|
| CPU 基线（`BEZIER_S95_GPU=0`） | 392.7 s | ~196 ms |
| GPU 协作二分（默认） | 360.5 s | **~180 ms（−8.2%）** |

10-iter 冒烟 A/B 为 −15.6%（短运行中固定开销占比更高，改善更明显）。

> 注：对比是在同机同配置下做的；绝对 iter 耗时随机器负载有波动，但相对差稳定可复现。

---

## 5. 使用方法

```bash
# 默认即 GPU 路径，无需任何配置
./bezier_opt configs/bolt_optimize_north_200iter.json

# 切回旧 CPU 路径（A/B 或排障）
BEZIER_S95_GPU=0 ./bezier_opt configs/bolt_optimize_north_200iter.json
```

无新增配置项；descriptor 布局变化已内部处理（writes 50→52）。

---

## 6. 与 Phase 3 失败教训的对照

| 维度 | Phase 3 直方图 | 本方案 |
|---|---|---|
| 阈值精度 | 256-bin 量化，~1.5 W/m² 偏差 | 与 CPU 二分语义一致，~1e-6 |
| 梯度质量 | 被污染，优化结果变差 | `--check-grad` 与基线一致 |
| 提交/传输 | 省掉读回 | 省掉读回 + 3 submit 合并为 1 |
| 结论 | 放弃 | 采用为默认路径 |
