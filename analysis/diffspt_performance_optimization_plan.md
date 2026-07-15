# bezier_opt_desktop 性能优化方案（参考 diffspt）

## 背景

diffspt 在 RTX 4070 SUPER 上实现了 **13.5 亿光线/秒** 的吞吐量：
- 6,282 定日镜（126 亿光线）：GPU 计算 923 ms
- 27,135 定日镜（1007 亿光线）：GPU 计算 7594 ms
- 光线吞吐量在两个规模间保持稳定，线性扩展性良好

bezier_opt_desktop 的瓶颈分析见 `L:\Code\diffspt-main\experiment_report.md` 与两份代码的 shader 对比。

核心差距来自五个维度：调度策略、裁剪机制、单样本计算复杂度、反向传播参数数量、随机数生成方式。详见下文。

---

## 一、GPU 计算加速

### 1. [P0 · 高收益] 前向 pass 增加解析协方差裁剪

**现状**：前向 pass（`forward.slang:101`）仅有粗粒度的半面裁剪：

```hlsl
if (normP.x * cullDir.x + normP.z * cullDir.y <= 0.0f) return;
```

这会处理 ~50% 的接收器像素。每个像素 × 1024 样本全量计算，不存在 per-facet 级别的空间裁剪。

**方案**：参考 diffspt 的 `passesRaytracerCovarianceCull`（`common.slang:276-369`），在 receiver pixel 和 heliostat 之间增加基于高斯椭圆近似的快速预判：

1. 对当前太阳方向，计算 heliostat facet 在 receiver 图像平面上的投影协方差椭圆
2. 检查 receiver pixel 的 Mahalanobis 距离是否在椭圆截断半径内
3. 落在椭圆外的 (pixel, sample) 对直接跳过

预期裁剪 **80–95%** 的无效 (pixel, sample) 对。可直接从 diffspt 的 `common.slang:276-369` 移植核心逻辑。

**参考代码**：`L:\Code\diffspt-main\diffspt\shaders\common.slang:276-369`

---

### 2. [P0 · 高收益] 反向 pass 分离 Bezier 求值与光学计算

**现状**：`backward.slang` 的 `computePixelEnergy` 把 Bezier 曲面求值（16 个控制点 → y, yu, yv → 法向量）和玻璃光学（折射、反射）揉在一个函数里，Slang AD 对整个计算图求导。结果是每条光线生成 16 个控制点梯度，计算图包含数百个节点。

**方案**：利用链式法则将梯度分解为两阶段：

```
dL/d(CP) = dL/d(y, yu, yv) · d(y, yu, yv)/d(CP)
```

- **阶段 1（光学 AD）**：用 `bwd_diff` 求 `dL/d(y, yu, yv)`，只输出 3 个标量。计算图只包含曲面位置→法向量→光学→能量的路径，不涉及 Bernstein 基函数展开。成本 ≈ 1× forward。
- **阶段 2（解析 Jacobian）**：`d(y, yu, yv)/d(CP_ij)` 是纯解析的——Bernstein 基函数对控制点的导数就是 `bernstein3(i,v) * bernstein3(j,u)` 自身。可以直接在 shader 中写出闭式，无需 AD。

反向 pass 的 AD 计算图从 16 输出缩减为 3 输出，AD 开销减少 **~80%**。

**注意**：bolt 模式（`bolt_backward.slang`）已经在做类似的事——`computePixelEnergyBolt` 只对 `(y, yu, yv)` 求导。Bezier 模式尚未做此优化。

**参考代码**：
- `L:\Code\bezier_opt_desktop\shaders\bolt_backward.slang:47-100`（bolt 模式的 3 参数 AD）
- `L:\Code\bezier_opt_desktop\shaders\backward.slang:82-143`（当前 Bezier 模式的 16 参数 AD）

---

### 3. [P0 · 高收益] 全场批量 dispatch

**现状**：`pipeline.cpp:891` 每次 dispatch 只处理一个定日镜：

```cpp
m_app.dispatch(pass.cmd, tileCount, m_totalPixels, 1);
// tileCount = 4, totalPixels = 7850 → 仅 1 个定日镜
```

27,135 面定日镜意味着 27,135 次独立的 dispatch，每次都有 uniform 上传、pipeline barrier 和 GPU 启动延迟。

**方案**：将多个定日镜的数据打包到 buffer 中，单次 dispatch 处理：

1. 将 `heliostatPosition`、`aimPoint` 从 ConstantBuffer（单值）改为 StructuredBuffer（数组）
2. Shader 中增加 `heliostatIndex` 维度，类似 diffspt：
   ```hlsl
   uint workItemIndex = tileIndex * kFWGroupSize + localIndex;
   uint heliostatIndex = workItemIndex / spp;
   uint sp = workItemIndex % spp;
   ```
3. dispatch 维度改为 3D：`(tiles, active_pixels, heliostat_batches)`

预期消除 **N×** 倍的 dispatch 启动开销。

**参考代码**：`L:\Code\diffspt-main\diffspt\shaders\planar.slang:227-292`

---

### 4. [P1 · 中收益] Slang 编译期特化替代运行时分支

**现状**：shader 中的太阳类型、Fresnel 模式等通过 uniform buffer 在运行时判断：

```hlsl
float ssVal = computeSunshape(st, shapeP, shapeType);  // 内部 switch/if-else
```

**方案**：参考 diffspt 的模板参数模式，用 Slang 的 `let` 泛型常量在编译期选择代码路径：

```hlsl
// diffspt 模式: 零分支开销
void renderForward<let SUNSHAPE_TYPE : uint, let FRESNEL_MODE : uint, ...>(...) {
    float ss = computeSunshape<SUNSHAPE_TYPE>(sunTheta, ...);
}
```

为 (sunType ∈ {Buie, Pillbox, Gaussian}) × (fresnelMode ∈ {Off, Split}) × (gridSize ∈ {25, 32}) 预编译少量特化变体，消除热路径上的所有运行时分支。对 GPU 占用率和指令发射效率有显著提升。

**参考代码**：`L:\Code\diffspt-main\diffspt\shaders\planar.slang:47`（模板参数列表）

---

### 5. [P1 · 中收益] 前向 pass reflection-only 快速路径

**现状**：forward.slang 对每条光线都执行完整的 2 层玻璃折射计算：

```hlsl
// 折射进入 → 反射 → 折射退出，含 TIR 检查
float3 d2 = normalize(etaE * dir - (etaE * ndi + sqrt(kEnter)) * nor1);
float3 d3 = normalize(reflect(d2, nor2));
float kExit = 1.0f - etaX * etaX * (1.0f - ndx * ndx);
// ...
```

**方案**：增加一个 "reflection only" 快速路径（类似 diffspt 的 `REFLECTION_ONLY` 模板参数）：

```hlsl
if (REFLECTION_ONLY) {
    outRay = normalize(reflect(dir, nor1));
    ratio = area * dot(normP, dir) * dot(nor1, outRay) / (rayLen^2) * attenuation;
} else {
    // 完整的 2 层玻璃折射（仅在需要偏振/精确 Fresnel 时使用）
}
```

在只关心能量分布的场景下，可加速前向 pass **~3–5×**。

**参考代码**：`L:\Code\diffspt-main\diffspt\shaders\planar.slang:67-91`

---

### 6. [P2 · 低收益] 用查表替代运行时 Box-Muller

bezier 项目的 Phase 1 已将 1.5 GB Gaussian pool 改为内联 Box-Muller。如果显存充裕（RTX 4070 SUPER 有 12 GB，当前峰值利用率 ~23%），可以恢复较小规模的预计算池（如每个 heliostat 独享的 16 KB 扰动池），将 `log+sqrt+sin+cos`×4 替换为 1 次内存读取。

---

## 二、显存与空间优化

### 7. [P1 · 高收益] gradPartial buffer 使用固定点原子累加

**现状**（`pipeline.cpp:246`）：

```cpp
m_gradPartial = m_app.createBuffer(
    m_totalBackwardGroups * 16 * sizeof(float), ...);
// = 31,400 × 16 × 4 = 2.0 MB
```

每个 pixel-group 分配 16 个 float 用于部分梯度累加，之后还需要一个 `reduceBackwardGradients` pass 来汇总。

**方案**：bolt_backward.slang 的 Phase 5 已经做了此优化——使用 `InterlockedAdd` 将梯度以定点数（×1e5 缩放）直接原子累加到 `gradPartialTile`（`1024 × 3 × 4 = 12 KB`）。将 Bezier 模式改为同样的方案：

- 16 个控制点梯度 buffer 直接作为原子累加目标
- 消除 `gradPartial` 中间 buffer 和 `reduceBackwardGradients` pass
- 节省 2 MB 显存 + 1 个 compute pass

**参考代码**：`L:\Code\bezier_opt_desktop\shaders\bolt_backward.slang:176-187`

---

### 8. [P2 · 中收益] yGrid/nGrid sun batch 动态分配

**现状**（`pipeline.cpp:215-216`）：

```cpp
m_yGrid = m_app.createBuffer(kSunBatchSize * gridPts * sizeof(float), ...);
m_nGrid = m_app.createBuffer(kSunBatchSize * gridPts * 4 * sizeof(float), ...);
// kSunBatchSize = 36, gridPts = 1024
```

对于单太阳 Bezier 模式，实际只需要 1× 大小。按实际 `sunBatchCount` 动态分配，Bezier 模式下节省 35/36 ≈ 97% 的这两个 buffer。

---

### 9. [P2 · 低收益] rayValidity 清零使用 vkCmdFillBuffer

**现状**（`pipeline.cpp:1343`）：

```cpp
void BezierPipeline::clearRayValidity() {
    std::vector<uint32_t> zeros(numUints, 0u);
    m_app.uploadBuffer(m_rayValidity, zeros.data(), ...);  // CPU→GPU 传输 + 同步
}
```

**方案**：Phase 2 的 `clearRayValidityCmd` 已实现 GPU 端清零。把 Bezier 模式的老代码路径统一到 `vkCmdFillBuffer`，消除每次迭代的 CPU-GPU 同步。

---

### 10. [P2 · 低收益] 合并 gravity bin buffer

bolt_common.slang 有 20 个独立的 gravity bin buffer（bindings 31–50），每个仅 `1024 × 4 = 4 KB`。可以合并为一个 `StructuredBuffer<float>` + offset 索引，将 descriptor 数量从 20 减少到 1。

---

## 三、优先级排序

| 优先级 | 优化项 | 预期加速 | 实现难度 |
|--------|--------|---------|---------|
| **P0** | 解析协方差裁剪 | 5–20× 前向 | 中（移植 diffspt 代码） |
| **P0** | 分离 Bezier 求导/光学求导 | 5–10× 反向 | 中（重构 AD 函数） |
| **P0** | 全场批量 dispatch | N× 启动开销 | 高（重构 shader 接口） |
| **P1** | Slang 编译期特化 | 1.5–2× | 低（改泛型参数） |
| **P1** | reflection-only 快速路径 | 3–5× 前向 | 低（加 if 分支） |
| **P1** | gradPartial 固定点累加 | 消除中间 pass | 中 |
| **P2** | vkCmdFillBuffer 替代 CPU upload | 消除同步 | 低（统一代码路径） |
| **P2** | yGrid/nGrid 动态分配 | 节省显存 | 低 |
| **P2** | 合并 gravity bin buffer | 减少 descriptor | 低 |

**如果只做 P0 三项**：前向 5–20× + 反向 5–10× + 调度 N× → 综合预期加速 **50–200×**，将单镜迭代时间从秒级降到毫秒级。

---

## 四、参考文件索引

| 文件 | 用途 |
|------|------|
| `L:\Code\diffspt-main\experiment_report.md` | diffspt 性能基准数据 |
| `L:\Code\diffspt-main\diffspt\shaders\common.slang:276-369` | 协方差裁剪实现 |
| `L:\Code\diffspt-main\diffspt\shaders\planar.slang:47-103` | 特化参数 + reflection-only 快速路径 |
| `L:\Code\diffspt-main\diffspt\shaders\planar.slang:227-292` | 全场批量 forward dispatch |
| `L:\Code\diffspt-main\diffspt\shaders\planar.slang:513-577` | 全场批量 backward dispatch |
| `L:\Code\diffspt-main\diffspt\shaders\forward_common.slang` | 前向 dispatch 参数 + 规约 |
| `L:\Code\diffspt-main\diffspt\core\gpu_context.h:94-97` | Shader 特化加载函数签名 |
| `L:\Code\bezier_opt_desktop\shaders\bolt_backward.slang:47-100` | bolt 模式 3 参数 AD（参考实现） |
| `L:\Code\bezier_opt_desktop\shaders\bolt_backward.slang:176-187` | 固定点原子累加（Phase 5） |
| `L:\Code\bezier_opt_desktop\shaders\backward.slang:82-265` | 当前 Bezier 模式 16 参数 AD（待优化） |
