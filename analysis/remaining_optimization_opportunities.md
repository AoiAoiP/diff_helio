# diff_helio 剩余优化空间分析

**当前基准**: master (= worktree-baseline-fixed, `9a6b8d7`): **1.8s/iter, ~200 MB VRAM**  
**已废弃**: 旧 master (`8dfa29a`, Wave A1–C2): 3.1s/iter, ~650 MB  
**分析日期**: 2026-07-15  
**GPU**: RTX 4070 SUPER

---

## 0. 当前状态

当前 master 包含 3 个已验证的优化 Phase：

| Phase | 名称 | 效果 |
|:---:|------|------|
| 1 | 内联 Box-Muller | 消除 1.5 GB gaussianPool, 消除 ~11.6B 全局内存读取/iter |
| 2 | Command Buffer 合批 (RawComputePass) | 4-5× 减少 vkQueueSubmit 次数 |
| 5 | InterlockedAdd 定点数归约 | 消除 368 MB boltGradPartial, 替换为 12 KB gradPartialTile |

**当前缺失**（旧 master 有但未移植到当前 master）：

| 特性 | 旧 master commit | 状态 | 价值 |
|------|:---:|------|:---:|
| 稀疏像素剔除 | Wave C2 (`201b623`) | 未移植 | ★★★ ~49% workgroup 减少 |
| GPU S95 直方图 | Wave A1 (`12c8f24`) | 有精度 bug | ★★ 消除 readFlux 同步 |
| vkCmdUpdateBuffer | Wave C1 (`4f55635`) | 未移植 | ★ 消除 CPU uploadBuffer |

---

## 1. 优化机会（按优先级排列）

### B1. 移植稀疏像素剔除 (Wave C2) ★★★

**来源**: 旧 master `201b623 Wave C2: Sparse pixel culling via active pixel list`

**原理**: 接收器是圆柱面，只有约 49% 的像素面向定日镜。通过预计算 `activePixelList`，forward 和 backward dispatch 仅处理有效像素。

**当前代码路径**:
```cpp
// 当前: dispatch 全部 7850 像素
m_app.dispatch(cmd, m_totalPixels, tileCount, 1);  // X=7850
```

**优化后**:
```cpp
// 优化: 仅 dispatch 活跃像素 (~3850)
m_app.dispatch(cmd, m_activePixelCount, tileCount, 1);  // X≈3850
```

**需要移植的文件**:
- `shaders/culling.slang` (旧 master 有, 当前 master 无)
- `src/pipeline.cpp`: `buildActivePixelList()`, 相关 dispatch 修改
- `src/pipeline.h`: `m_activePixelList`, `m_activePixelCount` 成员

**预期效果**: forward + backward 的 workgroup 数减半 → **1.8s → ~1.1s/iter**

**风险**: 低。纯正向优化，不影响梯度计算精度。旧 master 已验证正确性。

### B2. 修复并移植 GPU S95 ★★

**来源**: 旧 master `12c8f24 Wave A1: GPU S95 level computation via histogram`

**当前瓶颈**: 每 sun 需要 `readFlux()` (GPU→CPU 回读 7850 floats) 来计算 S95 level。这导致：
- 每 sun 2 次 submit（无法合并 forward + backward）
- 36 suns × 2 submits = 72 次 fence wait/iter

**旧 GPU S95 的问题**: 256-bin 固定范围 (0-800 W/m²) 直方图产生 ~1.5 W/m² 系统偏差。S95 sigmoid 损失函数对 level 极其敏感，偏差导致 sigmoid 饱和，loss 过早归零。

**修复方案**:

*方案 A (推荐): GPU 精确前缀和*
不依赖固定 bin 宽度。直接在 GPU 上计算精确的 95% 能量阈值：
1. parallel reduction 计算 total energy
2. 按 flux 值排序或使用更细粒度直方图 (1024 bins, 动态范围)
3. 前缀和扫描找到 95% 阈值

*方案 B: 混合方案*
GPU 计算 flux 统计量 (max, sum)，CPU 做最终二分搜索。只需回读 ~10 floats 而非 7850。

**预期效果**: 
- 消除 readFlux 同步
- Forward + S95 + Loss + Backward → 单次 submit/sun
- Submit 次数: 72 → 36/iter
- **1.1s → ~1.0s/iter**（结合 B1 后效果递减，主要节省在 submit 合并）

**风险**: 中。需要验证 GPU S95 与 CPU S95 的一致性（差值 <0.1 W/m²）。

### B3. 移植 vkCmdUpdateBuffer (Wave C1) ★

**来源**: 旧 master `4f55635 Wave C1: vkCmdUpdateBuffer/vkCmdFillBuffer/transferBarrier infrastructure`

**当前代码路径**: 每 sun 用 CPU `uploadBuffer` 更新 sun UBO 和 sunBatchFlat：
```cpp
// 当前: CPU 端上传 (需要 CPU→GPU 传输)
m_app.uploadBuffer(m_sunBatchFlat, batch.data(), 8 * sizeof(float));
```

**优化**: 在 command buffer 内用 `vkCmdUpdateBuffer` 直接更新：
```cpp
// 优化: GPU 端内联更新 (无 CPU 往返)
m_app.cmdUpdateBuffer(cmd, m_uboSun, 0, 13 * sizeof(float), &allSunUBO[si * 13]);
m_app.cmdUpdateBuffer(cmd, m_sunBatchFlat, 0, 8 * sizeof(float), &allSunBatch[si * 8]);
```

**预期效果**: 减少每 sun 的 CPU→GPU 同步开销。在 B1+B2 之后再评估，效果可能较轻微 (~5% 加速)。

### B4. 多 sun 批量 dispatch ★★

**来源**: 旧 master Phase 4 (`aa5510d`)

**当前**: `kSunBatchSize = 6`，但每 sun 独立 dispatch。36 sun 串行处理。

**目标**: 将 6 个 sun 的前向渲染合并为一次 dispatch：
- `boltForwardSurface`: `(1,1,6)` — 6 sun 并行
- `renderForward`: 共享接收器几何计算

**旧尝试的问题**: 旧 master Phase 4 使用 push constants 传递 per-sun 参数，引入了 ~20% 性能退步。退步原因可能是 push constants 在每个 dispatch 间切换的开销，以及 sun batch 导致的寄存器压力增加。

**改进方向**: 使用结构化 buffer 而非 push constants 传递 per-sun 参数（当前 master 已有 `sunBatchFlat` binding 51，只需扩展使用）。

**预期效果**: submit 次数进一步减少（36 → 6 或更少），**1.0s → ~0.8s/iter**。

### B5. 减少 SPP ★

| SPP | 光线/sun | 预期/iter | 备注 |
|:---:|:---:|:---:|------|
| 32² (1024) | 8.0M | 1.0s | 当前 |
| 28² (784) | 6.2M | 0.8s | 需验证 S95 收敛 |
| 25² (625) | 4.9M | 0.7s | 需验证 S95 收敛 |

**风险**: SPP 减少会增加蒙特卡洛噪声，可能降低 S95 收敛稳定性。

---

## 2. 优化路线图

```
当前: master 9a6b8d7 — 1.8s/iter, ~200 MB VRAM
 │
 ├─ B1. 移植稀疏 culling (Wave C2)  ──→ ~1.1s/iter  [1 天]
 │   从旧 master 12c8f24..8dfa29a 提取 culling 相关代码
 │
 ├─ B2. 修复 GPU S95 精度             ──→ ~1.0s/iter  [2-3 天]
 │   精确 GPU 端 S95 计算，消除 readFlux + 合并 submit
 │
 ├─ B3. 移植 vkCmdUpdateBuffer        ──→ ~0.95s/iter [1 天]
 │   内联 buffer 更新，减少 CPU-GPU 同步
 │
 └─ B4. 多 sun 批量 dispatch          ──→ ~0.8s/iter  [3-5 天]
    6 sun 并行，结构化 buffer 传参

B5. SPP 32²→25² (可选)               ──→ ~0.6s/iter  [实验验证]
```

---

## 3. 累积预期

| 阶段 | 每 iter | 300 iter | VRAM | 对比基线加速 |
|------|:---:|:---:|:---:|:---:|
| 基线 (ff1f48d) | 7.6s | 38.1 min | 2,605 MB | 1× |
| **当前 master** | **1.8s** | **8.9 min** | ~200 MB | **4.2×** |
| + B1 (稀疏 culling) | ~1.1s | ~5.5 min | ~205 MB | 6.9× |
| + B2 (GPU S95 修复) | ~1.0s | ~5.0 min | ~210 MB | 7.6× |
| + B4 (多 sun 批量) | ~0.8s | ~4.0 min | ~220 MB | 9.5× |
| + B5 (SPP 25², 可选) | ~0.6s | ~3.0 min | ~220 MB | 12.7× |

---

## 4. 当前 master 的数据流（per sun）

```
CPU: uploadBuffer(sunBatchFlat)  [8 floats]
CPU: uploadBuffer(uboSun)        [13 floats]
┌─ Submit 1: RawComputePass ────────────────────────────┐
│ boltForwardSurfaceCmd  (1 dispatch)                    │  ~2ms
│ clearRayValidityCmd    (vkCmdFillBuffer)               │  ~0.1ms
│ forwardRenderCmd       (3 dispatches: clear+render+finalize) │ ~22ms
└─ submitAndWait ───────────────────────────────────────┘  ~26ms

CPU: readFlux()           ← GPU→CPU 7850 floats
CPU: computeS95Level()    ← 二分搜索

┌─ Submit 2: RawComputePass ────────────────────────────┐
│ clearFluxGradientCmd   (1 dispatch)                    │  ~1ms
│ computeS95LossCmd      (1 dispatch)                    │  ~1ms
│ boltBackwardPassCmd    (3 dispatches: clear+render+reduce+project) │ ~18ms
└─ submitAndWait ───────────────────────────────────────┘  ~22ms
```

**B1 效果**: Submit 1 的 renderForward 从 7850→3850 groups (~22ms→~12ms), Submit 2 的 renderBackwardBolt 同样减半 (~18ms→~10ms)

**B2 效果**: Submit 1 + Submit 2 合并为单次 submit（GPU 直接计算 S95 level 并传给 loss kernel，无需 CPU 介入），省去中间 readFlux + submitAndWait + 第二个 submit 的开销

---

## 5. 不需要做的：旧 master 中已验证失败的方案

| 方案 | 失败原因 | 结论 |
|------|------|:---:|
| Wave B2: CAS 原子加 (float) | `InterlockedCompareExchange` loop 高争用, 8.5s/iter | ❌ 不采用 |
| Phase 3: 固定 bin GPU S95 | 256-bin 0-800 W/m² 直方图有 ~1.5 W/m² 偏差 | 需重新设计 |
| Phase 4: Push Constants 多 sun | ~20% 性能退步 | 改用结构化 buffer |
