# 梯度分解视角下的时间/空间开销分析

**基线版本**: `ff1f48d` (S95 ≈ 53.2 m², North 300m, 300 iter, RTX 4070 SUPER)  
**分析日期**: 2026-07-15

---

## 1. 梯度链分解

Bolt 模式下，总损失对螺栓高度的梯度由以下链式法则给出：

$$\frac{dL}{dh_b} = \sum_{\text{sun}} \sum_{p} \left[ \frac{\partial L}{\partial\text{flux}} \cdot \left( \frac{\partial\text{flux}}{\partial y} \cdot \phi_b + \frac{\partial\text{flux}}{\partial y_u} \cdot \frac{\partial\phi_b}{\partial u} + \frac{\partial\text{flux}}{\partial y_v} \cdot \frac{\partial\phi_b}{\partial v} \right) \right]$$

该梯度链可分解为三个独立阶段：

```
Stage 0 (光学正向):   h_b → y/y_u/y_v → flux        [无梯度, 损失评估]
Stage 1 (光学反向):   dL/dflux → dL/dy, dL/dyu, dL/dyv   [G1: bwd_diff 自动微分]
Stage 2 (力学投影):   dL/dy,dyu,dyv → dL/dh_b              [G2: 影响函数内积]
```

**关键洞察**: Stage 2 的计算量（35 螺栓 × 1024 网格点 = 35,840 次乘加）与 Stage 1（~8M 光线 × 2 层玻璃折射的 bwd_diff 重放）相差约 **4 个数量级**。梯度计算的时间瓶颈完全在光学反向，力学投影几乎免费。

---

## 2. 时间开销分析

### 2.1 基线总览 (ff1f48d)

| 指标 | 数值 |
|------|------|
| 总耗时 (300 iter) | 2,288 s (**38.1 min**) |
| 每 iter 均值 | **7.6 s** |
| 每 iter 中位数 | 8.3 s |
| 每 sun 均值 | ~211 ms |
| 光线吞吐量 | ~76 M rays/s |

### 2.2 每 Sun Dispatch 序列与耗时分解

基线中每个太阳方向的 dispatch 序列（**4 次独立 pass，含 readFlux GPU→CPU 回读**）：

```
Pass 0: (CPU) updateUniforms        — UBO 上传  (~0.5ms)
Pass 1: (CPU) clearRayValidity      — CPU→GPU 上传  (~0.5ms)
┌─ Pass 2: beginComputePass ────────────────────────────────┐
│ 1. computeBoltSurface  (1,1,1)     — 1024 threads          │  ~4ms
│ 2. clearFlux            (10×4)      — 7850 threads         │
│ 3. renderForward        (4,7850,1)  — 31,400 groups, ~8M rays │ ~55% ★
│ 4. finalizeFlux         (10×4)      — 7850 threads         │
└─ endComputePass ──────────────────────────────────────────┘
  (GPU) vkQueueSubmit + wait
  (CPU) readFlux ←── 7850 floats GPU→CPU 回读  ★ 瓶颈
  (CPU) computeS95Level ←── 二分搜索 7850 像素
  (CPU) clearFluxGradient
  (CPU) computeS95Loss
┌─ Pass 3~6: boltBackwardPass (4次独立 begin/end pass) ─────┐
│ 5. clearSurfaceGradient (12 groups) — 3072 threads         │
│ 6. renderBackwardBolt   (7850,4,1) — 31,400 groups        │ ~35% ★
│    每线程: gaussianPool 读取 + bwd_diff 重放光学路径       │
│    每 group: groupshared 归约 1024 网格点梯度              │
│    输出: boltGradPartial (368 MB)                          │
│ 7. reduceSurfaceGradients (1,1,1) — 1 thread 归约 31,400  │
│    group → surfaceGradient[3072]                           │
│ 8. projectBoltGradients   (1,1,1) — 35 threads 内积       │
└─ endComputePass ──────────────────────────────────────────┘
```

### 2.3 瓶颈分布

| 阶段 | 耗时占比 | 每 sun 耗时 | 说明 |
|------|:---:|:---:|------|
| **readFlux** (GPU→CPU) | ~25% | ~53 ms | 回读 7850 floats + 隐式同步 |
| renderForward | ~35% | ~74 ms | 8M 光线, 2 层玻璃折射 + Buie sunshape |
| renderBackwardBolt | ~23% | ~49 ms | bwd_diff 重放 + groupshared 归约 |
| reduceSurfaceGradients | ~8% | ~17 ms | 单线程串行归约 31,400 组 × 3072 槽 |
| 其他 (clear, finalize, project, S95) | ~9% | ~19 ms | 小 dispatch + CPU 计算 |

**为什么 readFlux 是最大瓶颈？**

`readFlux()` 每 sun 调用一次 → 300 iter × 36 sun = **10,800 次 GPU→CPU 同步**。每次：
1. `vkQueueSubmit` + `vkQueueWaitIdle`（隐式同步）
2. `vkCmdCopyImageToBuffer`（texture → staging buffer）
3. `memcpy` 7850 floats（31.4 KB 数据量小，但同步开销大）

31.4 KB 的数据传输本身只需 ~2μs（PCIe 4.0 x16），但 GPU pipeline drain + 重新填充的开销约为 **50ms**。

### 2.4 与优化版 (master) 对比

| 指标 | 基线 (ff1f48d) | 优化版 (master) | 改善 |
|------|:---:|:---:|:---:|
| 每 iter 耗时 | 7.6 s | ~3.1 s | **2.45×** |
| readFlux | 每 sun 回读 7850 floats | 仅 S95 level (2 floats) | 消除 |
| S95 计算 | CPU 二分搜索 | GPU histogram | 消除同步 |
| backward pass 结构 | 4 次独立 pass | 单次 cmd buffer | 合并提交 |
| 随机数来源 | gaussianPool (1.5 GB) | 内联 Wang hash + Box-Muller | 省带宽 |
| 梯度累积方式 | groupshared → boltGradPartial → reduce | CAS 原子加 (→ 已回退) | — |

---

## 3. 内存开销分析

### 3.1 基线显存分配全景

| Buffer | 绑定 | 大小 (MB) | 状态 | 说明 |
|--------|:---:|:---:|:---:|------|
| **gaussianPool** | 9 | **1,536.0** | ★ 活跃 | Sobol 序列 + Owen scrambling, 2^26 × 6 floats |
| **boltGradPartial** | 11 | **368.4** | ★ 活跃 | 31,400 groups × 1024 网格点 × 3 ch |
| fluxPartial | 10 | 0.74 | 活跃 | 6 sun × 7850 px × 4 tile |
| influencePhi+U+V | 19-21 | 0.42 | 活跃 | 35 bolts × 1024 pts × 3 files |
| 20 gravity bins | 31-50 | 0.08 | 活跃 | 20 × 1024 × 4B |
| yGrid + nGrid | 6-7 | 0.12 | 活跃 | 6 sun × 1024 float/float4 |
| yuGrid + yvGrid | 23-24 | 0.05 | 活跃 | 6 sun × 1024 |
| surfaceGradient | 25 | 0.012 | 活跃 | 1024 × 3 ch |
| rayValidity | 29 | 1.0 | 活跃 | 8M rays / 8 bits |
| renderedFlux | 8 | 0.03 | 活跃 | 157×50 texture |
| fluxGradient | 12 | 0.03 | 活跃 | 157×50 texture |
| 其他 (UBO, Adam, etc.) | — | <1 | 活跃 | |
| **活跃合计** | | **~1,908** | | |
| — | | | | |
| gradPartial (Bezier) | 11 | 2.0 | 闲置 | Bezier 路径用, bolt 模式未使用 |
| **总分配** | | **~1,910** | | |
| Vulkan 驱动开销 | | ~695 | | 含 swapchain, 命令池等 |
| **总显存 (实测)** | | **2,605** | | 匹配 baseline.json 数据 |

### 3.2 最大单块浪费：gaussianPool

gaussianPool 占用了 **1.5 GB**（总优化显存的 80%），但在 bolt 模式中仅被 `renderBackwardBolt` 的 `samplePoolOffset()` 读取。每个 ray 读取 4 个 float（2 个扰动向量 × 2 分量）。

**为什么这么大？**

```cpp
// 基线代码: pipeline.cpp:230-300
uint32_t minSize = m_totalRays * 6;    // 8,038,400 × 6 = 48,230,400
while ((1u << pow) < minSize) pow++;   // → pow=26
m_samplePoolSize = 1u << 26;           // 67,108,864 entries
// 每个 entry 含 6 floats (3D perturb × 2)
totalFloats = 67,108,864 × 6 = 402,653,184
Size = 402,653,184 × 4 bytes = 1.61 GB
```

实际上是 **1.54 GB**（1,536 MiB），因为 `2^26 × 6 × 4 = 1,610,612,736 bytes`。

### 3.3 第二大块：boltGradPartial

```
totalGroups = 7850 pixels × 4 tiles = 31,400
boltGradPartial = 31,400 × 1024 × 3 × 4 = 385,843,200 bytes ≈ 368 MB
```

此 buffer 作为 per-group per-grid-point 的中间归约存储，是 **梯度链 G1 → G2 的桥梁**：
- `renderBackwardBolt`: 每个 group（256 rays）计算该 group 内的 surface gradient → 写入 boltGradPartial
- `reduceSurfaceGradients`: 将所有 group 贡献求和 → surfaceGradient[3072]
- `projectBoltGradients`: surfaceGradient → boltHeightGradient[35]

### 3.4 梯度缓冲区的数据流

```
Stage 1: renderBackwardBolt  (31,400 workgroups)
  gaussianPool[randOffset] → 随机扰动向量
  bwd_diff(computePixelEnergyBolt) → dL/dy, dL/dyu, dL/dyv
  groupshared 累积 → boltGradPartial[groupIdx * 1024*3 + gridIdx*3 + ch]
                    ↓
Stage 1b: reduceSurfaceGradients  (单线程循环归约)
  boltGradPartial → surfaceGradient[1024×3]  (单槽, 最终累加)
                    ↓
Stage 2: projectBoltGradients  (35 线程)
  surfaceGradient × influencePhi/U/V → boltHeightGradient[35]
```

---

## 4. 从梯度分解视角看优化空间

### 4.1 什么是可优化的

梯度链的三个阶段各有不同的优化机会：

| 阶段 | 计算特征 | 优化潜力 | 方向 |
|------|----------|:---:|------|
| **Stage 0** (正向渲染) | 8M 光线 × 玻璃光学 + sunshape | ★★★ | 稀疏 culling, 减少 SPP, 瓦片化 |
| **Stage 1** (光学反向) | Slang bwd_diff 重放 + 梯度累积 | ★★★ | 消除中间 buffer, 减少归约轮次 |
| **Stage 2** (力学投影) | 35 × 1024 次乘加 | ☆ | 已是最优, 无需优化 |

### 4.2 五个具体优化方向

#### 方向 1: 消除 readFlux（Stage 0 → Stage 1 过渡）

**问题**: 每 sun 回读 7850 floats 用于 CPU 端 S95 计算，造成 GPU pipeline drain。

**方案**: GPU 端 S95（已实现于 master: `computeS95Histogram` + `computeS95FindLevel`），仅回读 2 floats（S95 level + total energy）。

**预期收益**: 消除 ~25% 的每 sun 耗时（~53ms/sun → ~0ms）。

**实现状态**: ✅ 已在 master 实现 (Wave A1, commit 12c8f24)。

#### 方向 2: 合并 backward 多个 pass（Stage 1 内部）

**问题**: 基线 `boltBackwardPass` 中 4 个 stage（clear → renderBackward → reduce → project）各自独立 `begin/endComputePass`，每次都是独立的 `vkQueueSubmit`。

**方案**: 将所有 backward 相关 dispatch 放入同一 command buffer 中执行（已在 master 实现: Wave A2/C1）。

**预期收益**: 减少 ~4× `vkQueueSubmit` per sun × 36 sun = 144 次提交/iter → ~5% 加速。

**实现状态**: ✅ 已在 master 实现。

#### 方向 3: 消除 gaussianPool（Stage 1 输入）

**问题**: 1.5 GB Sobol pool 占用显存且消耗带宽。每个光线读 4 floats × 8M rays = 32M 次随机读取 per sun。

**方案**: 内联 Wang hash + Box-Muller 生成 N(0, σ²) 扰动（已在 master 实现: Wave B1）。

**实现状态**: ✅ 已在 master 实现 (commit 88133a3)。

**注**: 但 gaussianPool buffer 仍被分配（1.5 GB），需清理。

#### 方向 4: 消除 boltGradPartial（Stage 1 → Stage 2 过渡）

**问题**: boltGradPartial (368 MB) 作为 per-group per-grid-point 中间存储。`reduceSurfaceGradients` 用单线程串行遍历 31,400 组 × 1024 网格点 = **32M 次读取**。

**方案 A** (已尝试): CAS 原子加直接写入 surfaceGradient（Wave B2, commit f7e99e0）。  
→ **已回退**: 31,400 workgroup 竞争 3,072 原子槽，CAS 重试导致 8.5s/iter（恶化 2.7×）。

**方案 B** (改进): 保留 boltGradPartial 但用多线程并行归约替代单线程循环。当前 `reduceSurfaceGradients` 的 `for (uint g = 0u; g < totalGroups; g++)` 循环完全串行。

```hlsl
// 当前: 单线程遍历 31,400 组
for (uint g = 0u; g < totalGroups; g++) { sumY += gradPartial[...]; }

// 改进: 256 线程并行归约 (类似 reduceBackwardGradients)
// 每线程处理 totalGroups/256 组, 然后 WaveActiveSum 合并
```

**方案 C**: 分层归约——先在 warp/block 级别做第一层归约，将 31,400 → ~490（每 64 group 一次局部归约），然后再全局归约。这样 boltGradPartial 大小从 368 MB → ~5.8 MB（减少 63×）。

**预期收益**:
- 方案 B: 将 reduce 阶段从 ~17ms → <1ms，总体 ~5-6% 加速
- 方案 C: 同上 + 释放 ~362 MB 显存

#### 方向 5: 稀疏光线剔除深化（Stage 0 + Stage 1）

**问题**: 基线中 `renderForward` 和 `renderBackwardBolt` 都在 `m_totalPixels = 7850` 像素上 dispatch，但只有 ~49% 像素面向定日镜（baseline.json: `sparse_culling_active_pct: 49.0`）。

**方案**: 预计算 active pixel list，只在有效像素上 dispatch（Wave C2, commit 201b623）。

**预期收益**: forward + backward 时间减半（~55% + ~35% → ~27% + ~17%），理论上可达 **1.8× 加速**。

**实现状态**: ✅ 已在 master 实现。

### 4.3 累积优化预期

| 优化 | 类别 | 预期加速 | 显存节省 |
|------|------|:---:|:---:|
| D1: GPU S95 (消除 readFlux) | 同步消除 | 1.33× | — |
| D2: 合并 backward pass | 提交合并 | 1.05× | — |
| D3: 消除 gaussianPool | 显存+带宽 | ~1.0× (带宽) | **1,536 MB** |
| D4-B: 并行 reduce boltGradPartial | 计算 | 1.06× | — |
| D4-C: 分层归约 boltGradPartial | 计算+显存 | 1.06× | **362 MB** |
| D5: 稀疏 culling 深化 | 计算 | 1.8× | — |
| **累积** | | **~2.7×** | **~1,898 MB** |

基线 7.6s/iter → 目标 ~2.8s/iter（300 iter → 14 min）。显存从 ~2,600 MB → ~700 MB。

---

## 5. 当前 master 与基线的差距

master 已实现 D1/D2/D3(代码)/D5，但：

1. **gaussianPool 仍被分配**（1.5 GB 闲置）— 需在 bolt 模式下跳过分配
2. **boltGradPartial 仍被分配**（368 MB 闲置）— Wave B2 回退后未清理
3. **CAS 原子加方案不稳定** — 需要新的低争用归约策略
4. **S95 损失 path 仍有 2 次 submit per sun** (CMD1: forward + S95, CMD2: loss + backward) — 可合并为 1 次

**当前 master 实测**: 3.1s/iter（相比基线 7.6s 已改善 2.45×），但距离理论最优 (~2.8s) 仍有约 10% 空间，主要是：
- 2 次 submit per sun 的同步开销
- 未清理的闲置 buffer 虽不直接消耗时间但占用显存
