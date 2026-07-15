# 失败案例：GPU S95 直方图替代 CPU readFlux

**日期**: 2026-07-15  
**基线**: `9a6b8d7` (worktree-baseline-fixed, 1.8s/iter, S95≈52.35)  
**结论**: 已回退，未合并到 master

---

## 目标

用 GPU 端 S95 计算替代 `readFlux()`（每 sun 从 GPU 回读 7850 floats → 仅回读 3 floats），消除 GPU→CPU 纹理同步，为进一步合并 forward+backward 为单次 submit 铺路。

## 实现

1. **`shaders/loss.slang`** — 新增两个 shader entry point:
   - `computeS95GPU`: 256-thread 单 workgroup，1024-bin 自适应直方图（范围 [0, maxFlux]），并行 reduction 计算 totalEnergy + maxFlux，找 95% 能量阈值，并行计算 sigmoid loss
   - `computeS95LossBUF`: 从 buffer 读取 S95 level（替代 push constant），用于单 submit 模式

2. **`src/pipeline.cpp`** — 新增 pipeline、binding 53 buffer (3 floats)、优化循环 dispatch

3. **`CMakeLists.txt`** — 新增 2 个 shader entry point

## 结果

| 指标 | 原始 (CPU S95) | GPU S95 (2-submit) | GPU S95 (1-submit) |
|------|:---:|:---:|:---:|
| S95 收敛 | 52.35 | **52.83** (+0.9%) | — |
| 每 iter 耗时 | 2.5-4.2s | 2.8-3.0s | **5.0s** |
| S95 计算精度 | 精确 (CPU 二分) | ~0.01% 偏差 | ~0.01% 偏差 |

## 失败原因

### 1. 性能无提升

GPU S95 消除了每 sun 的 `readFlux()`（~0.1ms）和 CPU 二分搜索（~0.1ms），但新增的 `computeS95GPU` dispatch 引入了 GPU 端开销（1024-bin 直方图 + 并行 loss reduction + 额外 pipeline barrier），基本抵消了节省的时间。

根本原因：**CPU 端 S95 计算占每 iter 总时间的比例极小（<0.5%），GPU 优化的天花板极低。**

### 2. 单 submit 合并失败

尝试将 forward + GPU S95 + loss + backward 合并为单次 submit，反而导致 5.0s/iter（退步 2×）。原因未完全查明，可能与：
- `pipelineBarrier` 过多导致 GPU pipeline 序列化
- `computeS95GPU` 的 histogram atomic 操作打断了 forward→backward 的流水线重叠

### 3. 复杂度增加

新增 2 个 shader、2 个 pipeline、1 个 descriptor binding (53)、修改了 descriptor set layout，增加了代码维护负担。

## 教训

1. **在优化前应先分析瓶颈分布**：`readFlux` 只占 0.5% 时间，优化它不可能产生显著收益。瓶颈分析应在动手编码之前完成。

2. **GPU 原子操作在 Slang 中的行为不可预测**：`InterlockedCompareExchange` 在包含 `bwd_diff` 的 shader 中不工作（Wave B2 的教训），而 `InterlockedAdd` 虽可工作但引入其他局限。

3. **单 submit 合并不总是有益的**：当前 2-submit 结构允许 GPU 在 CPU 处理期间排空 pipeline。合并后 GPU 工作序列化反而降低了吞吐。

4. **1024-bin 自适应直方图精度足够**（与 CPU 差异 0.01%），这是本次实验唯一有价值的技术发现。

## 相关文档

- [梯度分解分析](./gradient_decomposition_analysis.md)
- [优化空间分析](./remaining_optimization_opportunities.md)
- [基线性能分析](./worktree_baseline_fixed_analysis.md)
