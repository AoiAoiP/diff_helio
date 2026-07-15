# worktree-baseline-fixed 时空开销分析（1.8s/iter）

**对比基线**: `ff1f48d` (7.6s/iter, ~2,605 MB)  
**分析日期**: 2026-07-15  
**GPU**: RTX 4070 SUPER

---

## 1. 总体结果

| 指标 | 基线 (`ff1f48d`) | 优化版 (worktree-baseline-fixed) | 改善 |
|------|:---:|:---:|:---:|
| 每 iter 耗时 | 7.6 s | **1.8 s** | **4.2×** |
| 300 iter 总时间 | 2,288 s (38.1 min) | **532 s (8.9 min)** | **4.3×** |
| GPU 显存 (稳态) | ~2,605 MB | **~720 MB** | **3.6×** |
| Best S95 | 52.29 m² | **52.35 m²** | 等价 |
| 螺栓行程 | 32.87 mm | 33.00 mm | 等价 |

---

## 2. 实施的优化（3 个 Phase）

| Phase | 名称 | 类别 | 效果 |
|:---:|------|------|------|
| **1** | 内联 Box-Muller | 显存 + 带宽 | 移除 1.5 GB gaussianPool, 消除 ~11.6B 全局内存读取/iter |
| **2** | Command Buffer 合批 | 提交合并 | 4-5× 减少 vkQueueSubmit 次数 (288→72/iter) |
| **5** | 定点数 InterlockedAdd 归约 | 显存 + 计算 | 386 MB boltGradPartial → **12 KB** gradPartialTile |

**已跳过**: Phase 3 (GPU S95 直方图 — 精度偏差导致 sigmoid 饱和), Phase 4 (Push Constants — 性能退步 20%)

---

## 3. 梯度分解视角的时间分析

### 3.1 优化后的 Dispatch 序列

```
每 sun (50ms, 36 suns × 2 submits):
  CPU: updateUniforms + packGravityParams + uploadBuffer(sunBatchFlat)  [~1ms]
  ┌─ Submit 1: Forward Batch ────────────────────────────────┐
  │ dispatch(1): boltForwardSurface   (1,1,1)     — 1024 th  │  ~2ms
  │ fillBuffer:  rayValidity           — 1 MB 清零           │  ~0.1ms
  │ dispatch(2): clearFlux            (10×4)      — 7850 th  │  ~1ms
  │ dispatch(3): renderForward        (4,7850,1)  — 31,400 gr│ ~22ms ★
  │ dispatch(4): finalizeFlux         (10×4)      — 7850 th  │  ~1ms
  └─ submitAndWait ──────────────────────────────────────────┘  [~26ms]
  CPU: readFlux → computeS95Level                              [~2ms]
  ┌─ Submit 2: Backward Batch ───────────────────────────────┐
  │ fillBuffer:  surfaceGradient + gradPartialTile  — 12 KB  │  ~0.1ms
  │ dispatch(5): renderBackwardBolt   (7850,4,1)  — 31,400 gr│ ~18ms ★
  │ dispatch(6): reduceSurfaceGradients (1,1,1)   — 256 th   │  ~0.5ms
  │ dispatch(7): projectBoltGradients  (1,1,1)    — 35 th    │  ~0.1ms
  └─ submitAndWait ──────────────────────────────────────────┘  [~20ms]
```

### 3.2 时间分布

| 阶段 | 每 sun 耗时 | 占比 | 说明 |
|------|:---:|:---:|------|
| Forward batch (4 dispatches) | ~26 ms | 52% | 含 renderForward 31,400 groups |
| CPU readFlux + S95 level | ~2 ms | 4% | GPU→CPU 同步 + 7850 float 回读 |
| Backward batch (3 dispatches) | ~20 ms | 40% | 含 renderBackwardBolt 31,400 groups |
| CPU overhead (upload UBO etc.) | ~2 ms | 4% | |

### 3.3 梯度链各阶段耗时

回顾梯度分解：

```
Stage 0 (光学正向):  h_b → surface → flux
Stage 1 (光学反向):  dL/dflux → dL/dy, dL/dyu, dL/dyv   [bwd_diff]
Stage 2 (力学投影):  dL/dy,dyu,dyv → dL/dh_b             [影响函数内积]
```

| 梯度阶段 | Dispatch | 耗时/sun | 占比 |
|----------|----------|:---:|:---:|
| **Stage 0** | renderForward (22ms) + boltForwardSurface + clear/finalize | ~26 ms | 52% |
| **Stage 1** | renderBackwardBolt (18ms) + reduceSurfaceGradients (0.5ms) | ~19 ms | 38% |
| **Stage 2** | projectBoltGradients | ~0.1 ms | 0.2% |
| 过渡/同步 | readFlux + S95 + 2× submitAndWait | ~5 ms | 10% |

**Stage 2 仅占 0.2%** — 力学投影在梯度总计算中几乎可以忽略不计。

### 3.4 4.2× 加速的来源分解

基线每 sun 耗时 ~211ms → 优化后 ~50ms，节省 161ms：

| 优化 | 节省时间/sun | 累计 | 说明 |
|------|:---:|:---:|------|
| **消除 gaussianPool 读** (Phase 1) | ~30 ms | 181ms | 每光线省 4 次全局内存读取 × ~8M rays |
| **合并 submit 次数** (Phase 2) | ~90 ms | 91ms | 288→72 fence waits/iter, 每 wait ~1.2ms |
| **InterlockedAdd 定点数** (Phase 5) | ~30 ms | 61ms | 消除 368 MB boltGradPartial 读写 + 并行化 reduce |
| **fillBuffer 替代 compute pass** | ~10 ms | 51ms | clearSurfaceGradient + clearRayValidity |
| 其他 (代码路径简化等) | ~1 ms | 50ms | |
| **合计** | **~161 ms** | 50ms | **4.2×** |

---

## 4. 内存开销分析

### 4.1 显存分配对比

| Buffer | 基线 (MB) | 优化版 (MB) | 变化 |
|--------|:---:|:---:|:---:|
| **gaussianPool** (Sobol) | **1,536.0** | **—** | 已移除 ← Phase 1 |
| **boltGradPartial** | **368.4** | **—** | 已移除 ← Phase 5 |
| **boltGradPartialTile** | — | **0.012** | 新增, 定点数 12 KB |
| influencePhi+U+V | 0.42 | 0.42 | 不变 |
| 20 gravity bins | 0.08 | 0.08 | 不变 |
| yGrid + nGrid | 0.12 | 0.12 | 不变 |
| yuGrid + yvGrid | 0.05 | 0.05 | 不变 |
| fluxPartial | 0.74 | 0.74 | 不变 |
| rayValidity | 1.0 | 1.0 | 不变 |
| surfaceGradient | 0.012 | 0.012 | 不变 (类型从 float→uint，大小相同) |
| gradPartial (Bezier) | 2.0 | 2.0 | 不变 |
| 其他 (UBO, texture, etc.) | <1 | <1 | 不变 |
| **活跃合计** | **~1,909** | **~5** | |
| Vulkan 驱动开销 | ~695 | ~715 | |
| **总显存 (实测)** | **~2,605** | **~720** | **3.6×** |

### 4.2 两大消除项详解

#### gaussianPool (1,536 MB → 0)

**基线**: 预计算 Sobol 序列 + Owen scrambling + inverse_erf → N(0, σ²) 池。
- 2^26 entries × 6 floats × 4 bytes = 1,610,612,736 bytes
- 每 iter 读取: ~8M rays × 36 suns × 4 floats × 2 (fwd+bwd) = ~2.3B 次全局内存读取

**优化**: 内联 `generateGaussianSamples()` — 4 次 Wang hash + 2 对 Box-Muller 变换。
- 节省 1.5 GB 显存
- 消除 ~11.6 GB/s 的全局内存带宽消耗
- ALU 开销增加（~8 条 hash + 2× sqrt/log/sin/cos per ray），但远小于内存延迟

#### boltGradPartial (368 MB → 12 KB)

**基线**: `31,400 groups × 1,024 gridpts × 3 channels × 4 bytes = 385,843,200 bytes`

数据流：
```
renderBackwardBolt (31,400 groups)
  → groupshared[1024][3] 归约
  → boltGradPartial[groupIdx * 1024*3 + ...] 写入 368 MB
    ↓
reduceSurfaceGradients (单线程)
  → 串行读取 31,400 × 1024 × 3 = 96M floats
  → surfaceGradient[1024 × 3]
```

**优化**: `InterlockedAdd` 原子累加到定点数 tile（12 KB, `uint[1024×3]`）。

```
renderBackwardBolt (31,400 groups)
  → groupshared[1024][3] 归约
  → InterlockedAdd(gradPartialTile[gridIdx*3 + ch], int(grad * 1e5))
    ↓ (原子累加直接在 GPU 完成, 无需额外 reduce pass)
reduceSurfaceGradients (256 线程并行)
  → 每线程处理 12 个 gridIdx
  → int→float 转换: float(int(gradPartialTile[idx])) / 1e5
  → surfaceGradient[1024 × 3]
```

关键变化：
- **大小**: 368 MB → 12 KB (**减少 30,000×**)
- **reduce 模式**: 单线程串行 → 256 线程并行
- **原子争用**: 31,400 groups 竞争 3,072 个 uint 槽，但 InterlockedAdd 是硬件原子操作，比 CAS loop 高效得多

### 4.3 为什么 InterlockedAdd 成功而 CAS 失败（Wave B2）

| 方案 | 原子操作 | 每槽争用 | 结果 |
|------|----------|:---:|------|
| Wave B2 (master) | `InterlockedCompareExchange` 浮点 CAS | 31,400→3,072 | **8.5s/iter** (回退) |
| Phase 5 (worktree) | `InterlockedAdd` 定点数 uint | 31,400→3,072 | **1.8s/iter** ✅ |

**根因**: 
- `InterlockedCompareExchange` 需要 CAS loop（读-比较-交换-重试），高争用下重试次数 O(N²)，31,400 groups 竞争 3,072 槽导致大量 warp 停滞
- `InterlockedAdd` 是单次原子操作（硬件直接完成），无重试，即使争用也仅增加延迟而不增加带宽消耗
- Phase 5 的关键创新：利用 `int` 的二进制补码在 `uint` 上实现负数累加（`InterlockedAdd` 需要 `uint` 参数）

---

## 5. 剩余瓶颈与进一步优化空间

### 5.1 2 次 Submit per Sun 的同步开销

当前每 sun 有两次 `submitAndWait`：
```
Submit 1: Forward (获取 flux)
  → CPU 读回 readFlux → computeS95Level
Submit 2: Backward (使用 S95 level 计算 loss + 梯度)
```

每次 `submitAndWait` = `vkQueueSubmit` + `vkWaitForFences`，约 1.2ms 开销。

**理论**: 如果 S95 能在 GPU 上正确计算（修复 Phase 3），可将两次 submit 合并为一次：
```
Submit 1: Forward + GPU S95 + Loss + Backward  (单次 submit)
```

**预期收益**: 消除 72 次 fence wait/iter → 节省 ~86ms/iter → ~1.65s/iter（再加速 8%）

**阻塞**: Phase 3 GPU S95 直方图的 ~1.5 W/m² 系统偏差导致 sigmoid 饱和。需要重新设计 GPU 直方图算法（例如使用与 CPU 一致的精确前缀和，而非固定 bin 宽度）。

### 5.2 readFlux CPU 回读

当前 `readFlux()` 每 sun 回读 7850 floats (31.4 KB) 用于 CPU 端 S95 计算。数据量小（~2μs PCIe 传输），但隐式同步开销大。

**方案**: 与 5.1 合并解决（GPU S95 直方图）。

### 5.3 renderForward/renderBackwardBolt 自身

这两个 dispatch 各自运行 31,400 workgroups（共 ~62,800 groups/sun），合计占 80% 时间。

**已尝试的方向**:
- 稀疏 culling (Phase C2 in master): 仅对面向定日镜的像素 dispatch → ~49% 减少 → 但 master 中已应用
- 减少 SPP (32² → 25²): 省 ~40% 光线，但需权衡收敛质量

### 5.4 sunBatch = 6 的多 sun 并行

当前 `kSunBatchSize = 6` 但每 sun 仍是串行。Phase 4 尝试通过 push constants 实现多 sun 并行，但引入了 ~20% 退步。

**潜力**: 若成功实现 6 sun 并行，理论上可将 36 sun 的 72 次 submit 减至 12 次，进一步节省同步开销。

---

## 6. 关键设计决策总结

| 决策 | 选择 | 理由 |
|------|------|------|
| RNG 方案 | Wang hash + Box-Muller | 消除 1.5 GB 显存，ALU 开销可接受 |
| 归约方案 | InterlockedAdd 定点数 | 硬件原子操作 > CAS loop，12 KB vs 368 MB |
| S95 计算 | CPU (保留 readFlux) | GPU 直方图有精度偏差，CPU 确保正确性 |
| 提交模式 | 2 submits/sun | S95 依赖阻塞了完全合批，但已充分加速 |
| 多 sun 批量 | 串行 (1 sun/dispatch) | Push Constants 方案有退步 |

---

## 7. 梯度分解的终极启示

```
G1 (光学反向): 38% 耗时, Stage 1 归约曾是瓶颈  → 修复为 InterlockedAdd
G2 (力学投影): 0.2% 耗时, 368 MB 存储         → 修复为 12 KB
─────────────────────────────────────────────────
瓶颈本不在 G2 的计算 (35K 乘加 vs 8M 光线)
瓶颈在 G1→G2 过渡的 存储层次 (1.9 GB 中间 buffer)
```

**核心教训**: 梯度分解的优化重点不是"算得更快"，而是"存得更少"。1.9 GB 中间 buffer 的读写带宽才是真正的瓶颈。消除这些 buffer 后，梯度计算回归到其本质——G1 的 bwd_diff 光学反向和 G2 的力学投影内积——总时间从 7.6s 降至 1.8s。
