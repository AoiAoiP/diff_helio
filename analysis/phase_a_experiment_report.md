# Phase A 实验记录：稀疏像素剔除 + 内联 buffer 更新

**日期**: 2026-07-15
**基线**: master `9a6b8d7`（工作区未提交修改，见 diff 清单）
**GPU**: RTX 4070 SUPER
**结论**: ✅ 数值逐位等价，中位 ~15% 加速（远低于计划预期 1.6×，原因见 §2）

---

## 0. 重大意外发现：stale-shader 构建缺陷（已修复）

`loadSpv` 从 cwd 相对路径 `shaders/*.spv` 加载，但 `src/CMakeLists.txt` 的
POST_BUILD 只把 **4 个 bolt shader** 从 `build/shaders/` 拷回源 `shaders/`
（Phase 5 遗留 hack）。**其余 shader（含 renderForward.spv）自 Jul 13 起从未更新**。

### 影响（严重）

1. **文档基线数据全部失真**：`worktree_baseline_fixed_analysis.md` 的
   1.8s/iter、S95≈52.35、init S95≈97.5 都是 **旧 renderForward.spv** 跑出来的。
   经 md5 对照与 init flux 指纹验证，旧 spv 渲染的接收器能量
   （sumF=189498）恰为正确值（sumF=415047）的一半——**半个接收器**。
2. **真实基线**（正确 shader 重新实测，300 iter 同配置）：

| 指标 | 文档数据（失真） | 实测真基线 |
|---|:---:|:---:|
| 300 iter 总时间 | ~532s (1.8s/iter) | **626.6s (~2.1s/iter)** |
| init flux sumF | 189,498 | **415,047** |
| init S95 | 97.5 m² | **227.36 m²** |
| 收敛 S95 | 52.35 m² | **52.3465 m²** |
| 螺栓行程 | 33.00 mm | **32.997 mm** |

   收敛 S95/行程几乎不变（优化解对渲染哪半接收器不敏感），但性能与
   init 数值全部需要以真基线为准。**此前所有 phase 的加速比需要重新解读。**

### 修复

`src/CMakeLists.txt` POST_BUILD 改为 `copy_directory` 全量拷贝
`build/shaders/ → shaders/`。今后任何 shader 源码修改都会真实生效。

---

## 1. 实施内容

### A1: 稀疏像素剔除（binding 55 `activePixelList`）

- CPU 端 `buildActivePixelList(hp)` 精确复刻 forward.slang:100 的半面剔除判据
  （over-inclusive 容差 -1e-4，shader 端剔除保留为 source of truth → 逐位等价）
- `renderForward` / `renderBackwardBolt` 经 `activePixelList[gid]` 间接寻址；
  dispatch 维度 7850 → 3950 (50%)
- 缺省 identity 列表，未调用 buildActivePixelList 的路径行为不变
- **教训 1**：list buffer 初版误建为 host-visible → GPU 每 workgroup 读一次
  走 PCIe，~+1s/iter。改 device-local 后恢复。**热路径 GPU 读的 buffer 必须
  device-local。**

### A2: vkCmdUpdateBuffer 内联更新（精细版）

- 新增 `VulkanApp::updateBufferCmd`（vkCmdUpdateBuffer + transfer→compute barrier）
- **仅用于 device-local 的 `m_sunBatchFlat`**：原 `uploadBuffer` 对它每 sun 走一次
  staging buffer 创建 + submit + `vkQueueWaitIdle` + 销毁 → 消除 36 次隐式提交/iter
- **教训 2**：`m_uboSun` 等 host-visible persistent-mapped buffer 的 uploadBuffer
  是**零同步 memcpy**，改 vkCmdUpdateBuffer 反而多付 transfer+barrier —— 计划文档
  B3 的假设（"CPU uploadBuffer 需要 CPU→GPU 传输"）对 mapped buffer 不成立。
  **A2 只对 device-local 小 buffer 有意义。**

---

## 2. 验收结果

### 数值等价（300 iter 完整）

基线与 Phase A：init S95 227.3553 / 收敛 S95 **52.3465** / 螺栓行程 32.997mm /
逐 iter Loss 序列 —— **全部逐位一致**。剔除是纯保守的，无精度损失。

### 性能（30-iter 交替对照，排除时段噪声）

本机有强背景负载噪声（同版本波动可达 66→104s），单次长跑对比不可靠，
改用交替短跑：

| 轮次 | 基线 | Phase A |
|:---:|:---:|:---:|
| 1 | 104s | 78s |
| 2 | 66s | 63s |
| 3 | 76s | 63s |
| **中位** | **76s** | **63s** |

**Phase A 每轮均快于紧邻基线，中位加速 ~15%**（保守区间 5–17%）。

### 为什么远低于计划预期的 1.6×

计划预期"workgroup 减半 → 时间减半"的前提是被剔除组与活跃组成本相同。
实际上被剔除像素在基线 shader 中本就被半面剔除（forward.slang:100）与
rayValidity 检查**早退**，是近零成本的"空转组"。A1 省掉的只是空转组的调度
开销。1.6× 的预期源自旧 master "Wave C2 已验证" 的说法——考古发现
**旧 master 的稀疏剔除从未接线到 shader**（只建了 CPU 列表），该预期从未
被真实验证过。

---

## 3. 修改清单

| 文件 | 改动 |
|---|---|
| `src/CMakeLists.txt` | POST_BUILD 全量拷贝 spv（修复 stale-shader 缺陷） |
| `shaders/common.slang` | +binding 55 `activePixelList` |
| `shaders/forward.slang` | renderForward 经列表间接寻址 |
| `shaders/bolt_backward.slang` | renderBackwardBolt 经列表间接寻址 |
| `src/pipeline.h/.cpp` | `buildActivePixelList` + buffer/descriptor/dispatch 接线；`fillSunParams` 提取 |
| `src/vulkan_app.h/.cpp` | +`updateBufferCmd` |

---

## 4. 对后续计划的影响

1. **所有历史加速比需重新校准**：真基线为 ~2.1s/iter 均值（626.6s/300iter），
   非 1.8s。修正见 [optimization_execution_plan](./optimization_execution_plan.md)。
2. **Phase B（多 sun 批量）的收益预期需重估**：A2 已消除 sunBatchFlat 的 36 次
   staging 提交/iter；剩余每 sun 2 次 submitAndWait 仍在（72 fence waits/iter），
   Phase B 的合批收益依然成立，但绝对数字要按真基线重算。
3. **新增方法论**：④ 热路径 GPU 读 buffer 必须 device-local；
   ⑤ host-visible mapped buffer 的 memcpy 上传是零成本，勿改 vkCmdUpdateBuffer；
   ⑥ 改 shader 后核对 `shaders/*.spv` 时间戳/md5 与 `build/shaders/` 一致
   （构建缺陷已修，但养成核对习惯）。

## 相关文档

- [优化执行计划](./optimization_execution_plan.md)（基线与预期已按本实验修正）
- [基线性能分析](./worktree_baseline_fixed_analysis.md)（其性能数据受 stale-shader 影响，见 §0）
