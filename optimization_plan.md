# 分阶段性能优化方案

**基线**: North 300m, 300 iter, RTX 4070 SUPER — 7.60s/iter, ~2.6 GB GPU 开销, 38.1 min 总耗时, S95=52.3 m²

---

## 最终实施结果（2026-07-15）

### 修复版 vs 基线对比

| 指标 | 基线 (`ff1f48d`) | 修复版 (`worktree-baseline-fixed`) |
|------|:---:|:---:|
| Best S95 | 52.29 m² | **52.35 m²** |
| 螺栓行程 | 32.87 mm | 33.00 mm |
| 每迭代耗时 | 3.9s (稳态) | **1.8s** |
| 300 iter 总时间 | 1167s (19.5 min) | **532s (8.9 min)** |
| GPU 显存 | ~2,605 MB | **~720 MB** |
| Sobol 池 (1.5 GB) | ✅ 已分配 | ❌ 已移除 |
| gradPartial (386 MB) | ✅ 已分配 | ❌ 替换为 12 KB gradPartialTile |
| Loss 饱和 | 否 | 否 ✅ |
| S95 收敛 | 正常 (227→52.3) | 正常 (227→52.3) ✅ |

### 实施的分阶段优化

| 阶段 | 名称 | 状态 | 说明 |
|:---:|------|:---:|------|
| — | 基线 | ✅ | S95=52.29, 3.9s/iter, ~2.6 GB VRAM |
| **1** | 内联 Box-Muller | ✅ 已应用 | 移除 1.5 GB gaussianPool，Wang hash + Box-Muller 替代 |
| **2** | Command Buffer 合批 | ✅ 已应用 | RawComputePass + submitAndWait，消除 per-dispatch fence |
| **3** | GPU 端 S95 | ❌ 已跳过 | **回归根因**：GPU 直方图 ~1.5 W/m² 偏差导致 sigmoid 饱和 |
| **4** | 多太阳基础设施 | ❌ 已跳过 | Push constants 引入 ~20% 性能退步 |
| **5** | gradPartial 归约 | ✅ 已应用 | InterlockedAdd 定点数累加，386 MB → 12 KB |

### 关键修复：Phase 3 GPU S95 回退

**问题**：Phase 3 引入的 `computeS95LevelGPU()` 使用 256-bin 固定范围 (0-800 W/m²) 直方图计算 S95 阈值，与 CPU 二值搜索 `computeS95Level()` 相比产生 ~1.5 W/m² 的系统偏差。

S95 sigmoid 损失函数 `σ(6·(f/level − 1))` 对 level 极其敏感。1.5 W/m² 的 level 偏高导致 sigmoid 参数向负方向偏移，σ → 0，Loss 在 iter 20-40 归零，后续优化无有效梯度信号。

**表现**：
- Loss 从 200K（基线 52K）开始，iter 33 归零
- S95 止步于 ~115 m²（vs 应有 52.3 m²）
- 螺栓行程仅 11.7 mm（vs 应有 32.9 mm）

**修复**：保留 CPU 端 S95 计算路径（`readFlux()` + `computeS95Level()`），确保 S95 阈值与 sigmoid 损失函数一致。`readFlux` 每 sun 仅增加 ~0.5ms 开销，对总时间影响可忽略。

### Phase 5 实现细节：InterlockedAdd 定点数累加

Slang 的 `InterlockedCompareExchange` (CAS) 在包含 `bwd_diff` auto-diff 的 shader 中生成的 SPIR-V 不执行（编译器 bug），但 `InterlockedAdd` 可以正常工作。

利用 `InterlockedAdd` + 定点数方案：
1. `renderBackwardBolt` 将梯度 × 1e4 转为整数，通过 `InterlockedAdd` 原子累加到 `gradPartialTile[gridIdx]`（`RWStructuredBuffer<uint>`, 12 KB）
2. `reduceSurfaceGradients` 读取 int，经 `int()` 恢复二进制补码负值，÷1e4 转回 float，写入 `surfaceGradient`
3. 负数通过二进制补码在 uint 上正确累加
4. 1e4 倍率下最大累加值 ~1.3e8 < int32 上限 2.1e9，无溢出

### 已跳过的阶段

| 阶段 | 跳过原因 |
|:---:|------|
| Phase 3 (GPU S95) | GPU 直方图 S95 偏差导致 sigmoid 饱和，需重新设计 GPU 直方图算法 |
| Phase 4 (Push Constants) | 引入 ~20% 性能退步，且 per-sun S95 依赖阻塞了完全合批 |

### 可验证性

| 指标 | 验证方式 | 结果 |
|------|------|:---:|
| S95 收敛 | 300 iter 完整优化 | 52.35 m² ✅ |
| 梯度一致性 | `--check-grad` | sign 57.1%, cosine 0.482 (匹配基线) ✅ |
| Loss 不饱和 | Loss 曲线 | Loss=12,703 at iter 290 ✅ |
| 螺栓行程 | 最终螺栓分布 | 33.00 mm ✅ |

### 关键源文件变更

| 文件 | 变更 |
|------|------|
| `shaders/bolt_common.slang` | `surfaceGradient`: `float` → `uint` |
| `shaders/bolt_backward.slang` | 移除 `gradPartial` (binding 11)；新增 `gradPartialTile` (binding 11, `RWStructuredBuffer<uint>`)；`renderBackwardBolt` 用 `InterlockedAdd` 替换直接写入；`reduceSurfaceGradients` 改为 int→float 转换；`projectBoltGradients` 用 `asfloat` 读取 |
| `shaders/common.slang` | `generateGaussianSamples()` 替换 `samplePoolOffset()` + gaussianPool |
| `shaders/forward.slang` | 移除 `gaussianPool` (binding 9)，使用内联 Box-Muller |
| `shaders/backward.slang` | 同上 |
| `src/pipeline.h` | 移除 `m_gaussianPool`、`m_boltGradPartial`；新增 `m_boltGradPartialTile` |
| `src/pipeline.cpp` | 移除 Sobol 池生成；CPU S95 路径；`fillBufferCmd` 清零 surfaceGradient + gradPartialTile；`boltBackwardPassCmd` 批量化 |
| `src/vulkan_app.h/cpp` | 新增 `RawComputePass`、`beginComputePassRaw()`、`submitAndWait()`、`fillBufferCmd()` |
| `src/CMakeLists.txt` | post-build 复制 SPIR-V 到源目录 |
