# Phase 5.3 实验方案：最优 margin 下的螺栓密度扫描

> **状态**：方案设计完成（2026-08-02），待执行。
> **前置**：Phase 5.0（margin=8% 密度扫描）→ 密度轴死亡（+80% 螺栓仅 −4.2% 地板）→ 悬挑定位 → Phase 5.1 margin 扫描 → m\*≈0.04–0.05 最优带。
> **本文档为 Phase 5 补充实验方案，插入 `phase5_structural_optimization.md` §3.10。**

---

## 1. 动机：为什么需要在最优 margin 下重做密度扫描

Phase 5.0 在 **margin=8%** 下扫描了 L1 8×6 (48 栓)、L2 7×7 (49 栓)、L3 9×7 (63 栓)，发现 +80% 螺栓仅降地板 4.2%。空间归因揭示了原因：**margin=8% 时悬挑带贡献 81–91% 的斜率能量**（10°: 81%, 80°: 91%），加密内部螺栓挠不到悬挑这个主损伤源。结论：**在悬挑收敛前，密度轴被悬挑噪声淹没**。

现在 margin 已收敛到 m\*≈0.05，悬挑从 ~1m 缩至 ~0.3–0.6m（悬挑斜率 ∝ a³ 下降 ~68%），内部凹陷分量相对权重上升。两个关键问题悬而未决：

1. **m\* 下密度回归是否显著？**——Phase 5.0 的"密度轴死亡"结论是否受 margin=8% 的悬挑噪声限制？
2. **完整的 2D 设计面（margin × 密度）形态如何？**——当前只有 7×5 的 margin 一维扫描，缺少密度维，无法给出 iso-performance 设计图。

此外，这与颜健等人 [21] 的 N≥11 递减回报结论直接对话——他们的工作在固定间距下发现"螺栓数超过 11 后改善可忽略"，我们可在 S95 域验证这一结论是否在最优 margin 下仍然成立。

---

## 2. 科学问题

| 问题 | 表述 | 可证伪预测 |
|------|------|-----------|
| **Q5（密度回报）** | 在 m\*=0.05 下，N 从 15→35→63→99，S95 地板下降多少？ | H₀：与 Phase 5.0 类似，<5%（密度轴即使在最优 margin 下也弱）<br>H₁：显著回报（>15%），悬挑收敛后内部凹陷成为主导，密度→跨距³→显著降地板 |
| **Q6（递减规律）** | 密度回报在哪一点进入递减区？是否与颜健 [21] 的 N≥11（≈5×3 网格，每排 5 栓）一致？ | 颜健的 N≥11 在 5×3 附近，若本实验 5×3→7×5 改善明显（>10%），则颜健结论不适用于斜面重力+多排布局 |
| **Q7（二维设计面）** | (margin, N) → S95 的 iso-surface 形态？是否存在鞍点/平面区？ | 预测：margin 轴在 N 小时更陡峭（悬挑大），N 大时两轴均平缓（全频覆盖） |

---

## 3. 实验设计

### 3.1 布局参数

固定 margin = **0.05**，扫描 4 个螺栓网格密度。

板尺寸：12.84 × 9.45 m，半宽 6.42 m，半长 4.725 m。Margin 5% = 边缘缩进 0.321 m (x) / 0.236 m (z)。

| 布局 | 螺栓数 | Δx (m) | Δz (m) | 单栓面积 (m²) | 相对 7×5 |
|------|--------|--------|--------|---------------|---------|
| **D1** 5×3 | 15 (−57%) | 3.050 | 4.489 | 8.07 | 稀疏探针 |
| **D2** 7×5 | **35 (基线)** | 2.033 | 2.245 | 3.47 | 已有（`_fine` bins） |
| **D3** 9×7 | 63 (+80%) | 1.525 | 1.496 | 1.93 | 密度上限 |
| **D4** 11×9 | 99 (+183%) | 1.220 | 1.122 | 1.22 | 渐近线探针 |

布局 JSON 路径：`configs/bolt_layouts/density/{5x3,7x5,9x7,11x9}_margin05.json`。

### 3.2 与 Phase 5.0 的关键差异

| 维度 | Phase 5.0 (2026-07-30) | 本实验 (Phase 5.3) |
|------|------------------------|---------------------|
| margin | **8%**（固定） | **5%**（最优，固定） |
| 悬挑 flap | x 1.03m, z 0.76m | x 0.32m, z 0.24m |
| 悬挑能量占比 | 81–91% | 预测 ~30–50%（悬挑三次方缩小） |
| 密度轴敏感度预期 | **极低**（被悬挑淹没） | **中等**（内部凹陷权重大） |
| 布局数 | 3（8×6, 7×7, 9×7） | 4（5×3, 7×5, 9×7, 11×9） |
| 子步 | **粗子步**（NSUBST 1,10,1） | **细子步**（NSUBST 50,500,50） |

### 3.3 实验流水线

#### Step 1：生成螺栓布局 JSON

为 5×3、9×7、11×9 各生成 m=0.05 布局文件（7×5 已有 `7x5_margin05_fine`）。

```python
# 螺栓坐标 = linspace(-half*(1-margin), +half*(1-margin), n)
# x: linspace(-6.099, 6.099, nx)
# z: linspace(-4.489, 4.489, nz)
```

#### Step 2：ANSYS 重力场 + TPS 影响函数

```bash
# 每布局 × 20 角度，细子步
python scripts/ansys_gravity.py \
    --bolt-layout configs/bolt_layouts/density/5x3_margin05.json \
    --output-dir data_proxy_density/5x3_margin05_fine/ \
    --nsubst 50,500,50

python scripts/ansys_gravity.py \
    --bolt-layout configs/bolt_layouts/density/9x7_margin05.json \
    --output-dir data_proxy_density/9x7_margin05_fine/ \
    --nsubst 50,500,50

python scripts/ansys_gravity.py \
    --bolt-layout configs/bolt_layouts/density/11x9_margin05.json \
    --output-dir data_proxy_density/11x9_margin05_fine/ \
    --nsubst 50,500,50

# TPS 影响函数（每布局）
for layout in 5x3 9x7 11x9; do
    python scripts/generate_proxy_model.py tps \
        --bolt-layout configs/bolt_layouts/density/${layout}_margin05.json \
        --output-dir data_proxy_density/${layout}_margin05_fine/
done
```

**机时**：3 布局 × 20 角度 × ~15 min = ~15 h（可并行，实际 ~4–5 h 若 4 核同跑）。

7×5 已有 `data_proxy_margin/7x5_margin05_fine/`，无需重出。

#### Step 3：缝隙分析（斜率分解 + 可补偿率，零 GPU）

每布局在 4 个探针角度（10°, 30°, 58°, 80°）做三频带分解与 TPS 子空间投影，产出：

- 悬挑/内部斜率 RMS 比 → 验证"悬挑权重重分配"预测
- 可补偿率（斜率空间最优投影）→ 验证"N 增大 → 可补偿率上升"预测
- 与 Phase 5.0 的 10° 对比：5×3 vs 7×5 vs 9×7 vs 11×9 的地板变化

#### Step 4：端到端 S95 优化（GPU）

每布局 × NEWS 四镜（300m）@ 110dir paper 模式：

```bash
# 生成配置（模板：configs/bolt_optimize_north_200iter.json）
# 关键键：num_bolts_x/z, bolt_margin, influence_data_path, gravity_data_path
for layout in 5x3 9x7 11x9; do
    for mirror in North East South West; do
        ./build/src/Release/bezier_opt.exe \
            configs/density_opt_${layout}_${mirror}.json
    done
done
```

**GPU 机时**：3 布局 × 4 镜 × ~20 min = ~4 h。

7×5 已有 `results_final_m05/`（或在 `results_g5truth/rerun_m05_fine/`），无需重跑。

#### Step 5：334dir 终评

对最优 (margin, N) 组合跑 334dir balanced 评估。
**机时**：1 布局 × 4 镜 × ~50 min = ~3.5 h。

---

## 4. 假想结果与判读框架

### 情景 A：密度回报显著（H₁ 成立）

```
布局    螺栓      S95 (North)    四镜合计        vs 7×5
5×3     15        ~80+           ~400+           −  (地板崩塌)
7×5     35        57.0           291.3           baseline
9×7     63        ~52            270             −7.3%
11×9    99        ~50            262             −10.1%
```

**判读**：m\*=0.05 下悬挑已收敛至亚主导，内部凹陷成为新的瓶颈 → 密度补偿有效。**与 Phase 5.0 形成关键对比**——margin 的首要性被确认，但"密度无用"的 Phase 5.0 结论被修正为"仅在 margin 远未收敛时密度无用"。

### 情景 B：密度回报仍然微弱（H₀ 成立）

```
布局    螺栓      S95 (North)    四镜合计        vs 7×5
5×3     15        ~73            ~380           −  (地板崩塌)
7×5     35        57.0           291.3           baseline
9×7     63        ~56            286            −1.8%
11×9    99        ~55            282            −3.1%
```

**判读**：即使 margin 收敛到 5%，内部凹陷的物理尺度仍不足以使密度成为有效杠杆（跨距³ 效应不够陡，或 TPS 影响函数的单位分解性使增加螺栓后每栓影响力稀释）。**颜健的 N 递减回报结论被推广到 S95 域**。设计指南：固定 35 栓 + margin≈5% 即是成本-性能 Pareto 最优点。

### 情景 C：5×3 已足够（地板主要由 margin 决定）

```
布局    螺栓      S95 (North)    四镜合计        vs 7×5
5×3     15        ~58            ~294           +1.0%
7×5     35        57.0           291.3           baseline
9×7     63        ~56            ~288           −1.1%
11×9    99        ~56            ~287           −1.5%
```

**判读**：在最优 margin 下，15 栓已覆盖重力场的主要子空间——**螺栓密度轴死亡在所有 margin 下成立**。强烈支持"margin >> density"的设计优先级。工程启示：与其加螺栓，不如进一步减 margin（代价是制造约束和 NLGEOM 稳定性）。

---

## 5. 论文叙事中的位置

| 情景 | 叙事定位 |
|------|---------|
| **A**（密度显著） | "密度轴被 Phase 5.0 错误地宣告死亡——根因是 margin=8% 时的悬挑噪声淹没。在 m\* 下，密度成为二级杠杆：二维设计面 (margin, N) → S95，给出完整 Pareto 前沿。" |
| **B**（密度微弱） | "Phase 5.0 的'密度轴死亡'结论在最优 margin 下经受住了压力测试——即使悬挑收敛后，固定 35 栓的跨距仍足以使密度成为递减回报项。7×5 + m\*≈0.05 即近 Pareto 最优。" |
| **C**（5×3 足够） | "出乎意料：15 栓在最优 margin 下已逼近地板。螺栓数不是瓶颈——TPS 影响函数的单位分解性使少量螺栓的线性叠加已覆盖主导子空间。增加螺栓数的价值在统计上不可区分。" |

**所有三种情景均产生可发表的结果**——不存在"做出来没东西写"的风险。关键是对比 Phase 5.0（margin=8% 密度无用），无论本实验结果是密度有用/无用/部分有用，都是对密度-悬挑交互作用的知识增量。

---

## 6. 执行清单

### 立即执行（零阻塞）

- [ ] 创建 4 个 layout JSON：`configs/bolt_layouts/density/{5×3,7×5,9×7,11×9}_margin05.json`
- [ ] 7×5 验证 → 与已有 `7x5_margin05_fine` 坐标一致（干跑确认）

### ANSYS 批次（需许可证，可并行）

- [ ] D1 5×3 @m05：20 角度细子步 → `data_proxy_density/5x3_margin05_fine/`
- [ ] D3 9×7 @m05：20 角度细子步 → `data_proxy_density/9x7_margin05_fine/`
- [ ] D4 11×9 @m05：20 角度细子步 → `data_proxy_density/11x9_margin05_fine/`
- [ ] TPS 影响函数：各 3 套

### 分析（零 GPU）

- [ ] 缝隙分析脚本：4 布局 × 4 探针角度 → 三频带 + 可补偿率
- [ ] 对比 Phase 5.0 10° 数据 → 密度-悬挑交互定量

### 渲染（需 GPU）

- [ ] 配置生成：3 布局 × 4 镜 = 12 个 JSON
- [ ] 110dir 优化：每镜 100 iter × Adam
- [ ] 最优组合 334dir 终评

### 文档

- [ ] 更新 `phase5_structural_optimization.md` §3.10
- [ ] 更新 `draft.md` §5.8 加入二维设计面数据

---

## 7. 时间估计

| 阶段 | 人时 | 机时（并行后） |
|------|------|---------------|
| layout JSON + 脚本适配 | 1 h | — |
| ANSYS (3 布局) | 30 min 监控 | ~5 h（4 核并行） |
| TPS + 缝隙分析 | 1 h | <5 min |
| 110dir 优化 | 1 h 配置 | ~4 h GPU |
| 334dir 终评 | 30 min | ~3.5 h GPU |
| 数据分析 + 写文档 | 2 h | — |
| **合计** | **~6 h 人时** | **~12 h 机时** |

> 可在一日内完成（上午发 ANSYS → 下午跑渲染 → 晚上分析）。
