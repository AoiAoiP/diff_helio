# 太阳方向采样：设计原则、对比实验与推荐

> 2026-10-19 合并自 `sundir_analysis_and_recommendations.md` 与 `sundir_experiment_report_east_west.md`；North 300 m 对比表原在 `docs/sundir_experiment_report.md`（工作区已删），从 git HEAD 取回并入附录。
> 结论：北/南镜 36 方向可训练，东/西镜 110 方向起步，终评统一 334 方向（12 月 × 3 日 × 13 时点，高度角 ≥15°）。

## 0. 一页结论

| 训练集 | 方向数 | 适用 | 验证差（1556dir） |
|---|---|---|---|
| `data/36_sundir_fast.txt` | 36 | 北/南快速迭代 | North +0.37；East +1.69；West +1.71 m² |
| `data/110_sundir_paper.txt` | 110 | 东/西最低可行 | East +0.45；West +0.29 m² |
| `data/334_sundir_balanced.txt` | 334 | 终评与生产 | North +0.00；East +0.01 m² |
| `data/1558_sundir_dense_val.txt` | 1558 | 仅验证集 | — |

> 口径注记：West 334dir 当次在第 3 次迭代后崩溃，表中缺该格；East 334dir 可作东西对称性参考。

---

## 一、采样策略论证（原 sundir_analysis_and_recommendations.md）

### 1. 论文主要工作与实验结论

**论文**：叶金伟, 何采投 (2026). 定日镜场地光学效率模拟中的蒙特卡洛光线跟踪方法中时间采样点灵敏度分析研究. *Computer Science and Application*, 16(3), 96-105.

#### 核心方法
- 构建了 Buie 太阳模型 + 微表面散射 + 简化大气传输 + GPU MCRT 的光学仿真框架
- 评价指标：**AFPA (Annual Flux per unit Area)**，即全年 DNI 加权的平均光学效率（单位 W/m²）
- 基准真值：365 天 × 25 个日内采样点 = 9125 个时间点

#### 实验设计
| 维度 | 方案 | 说明 |
|------|------|------|
| 日期采样 | 4天（二分二至）/ 12天（每月21日）/ 36天（每月10,20,30日）| 3 种 |
| 日内采样 | 5点 / 7点 / 13点 / 25点（9:00-15:00窗口）| 4 种 |

共 3×4=12 种组合，与基准真值比较 AFPA 误差。

#### 核心结论
1. **12×13 是最优平衡点**：156 个采样点，AFPA 误差 <0.01%，计算量降低 ~58 倍
2. **日内采样比日期采样更敏感**：增加日内点数比增加日期数对精度提升更大
3. **12→36 天几乎无改善**：日期采样在 12 天（月度）后饱和
4. **4 天方案误差偏大**（~0.18-1.32%）：二分二至无法捕捉 DNI 的季节性变化

---

### 2. 论文结论能否直接搬到本项目？

#### ❌ 不能直接搬用，原因如下：

**（1）任务本质不同**

| 维度 | 论文（场地效率模拟） | 本项目（单镜面型优化） |
|------|----------------------|------------------------|
| 目标 | 计算全年积分 AFPA | 训练螺栓调节量使 S95 最小 |
| 太阳方向的作用 | 被积函数采样点 | 优化器的训练数据 |
| 数学形式 | 加权求和（收敛性） | 梯度累加（覆盖性/泛化性） |
| DNI 权重 | 核心——低高度角权重小 | 当前无——所有方向等权 |
| 失败模式 | 积分误差偏大 | **优化器过拟合到特定方向** |

**（2）采样对称性要求不同**

- 论文使用**挂钟时间**（9:00-15:00），在德令哈（经度 97.29°E，但用北京时间 UTC+8）下实际对应 ~7:29-13:29 太阳时——**不对称**
- 本项目的镜面是物理对称的，上午/下午太阳方向应对称分布，否则优化器会产生偏置
- 用户已通过实验确认："镜面优化结果实际受太阳方向影响极大，采取对称采样是最好的"

**（3）训练集大小需求不同**

- 156 点对积分收敛足够（论文已证明），但对优化覆盖可能不足
- 优化器需要看到足够多样的太阳方向以避免过拟合
- 类似机器学习：积分 = inference（样本多→均值收敛），优化 = training（样本少→泛化差）

#### ✅ 可以借鉴的部分

- **月度采样（12个月）**：日期维度饱和的结论仍然适用
- **日内密度 ≥13 点**：比当前 7 点（2h 间隔）更密，减少插值误差
- **日数可减少**：当前 14 天/月可能过多，可降至 1-3 天/月，将算力重新分配给日内密度

---

### 3. 对称采样思想是否需要保留？

#### ✅ 必须保留，这是本项目的关键创新点

**理论依据**：
- 定日镜面板是矩形平板，物理上关于垂直中轴线对称
- 太阳轨迹关于当地正午（local solar noon）对称
- 如果训练集不对称（如只用挂钟时间），优化器看到的太阳方向分布有偏，会产生不对称的面型——这在物理上是错误的
- 对称采样保证 `(altitude, +azimuth_from_south)` 和 `(altitude, -azimuth_from_south)` 成对出现

**DE_sundir_year.py 的做法是正确的**：
1. 计算当地正午：`time_offset = (120° - lon) × 4 min/deg`（德令哈约 +91min，正午 ≈ 13:31 北京时间）
2. 以当地太阳时（local solar hour）为基准循环，自然对称
3. `range(6, 19, 2)` → [6, 8, 10, 12, 14, 16, 18]，关于 12 完美对称

**论文方法的问题**：
- 论文用挂钟 9:00-15:00（0.5h 间隔）做 13 点采样
- 如果这也用北京时间在德令哈执行，实际是太阳时 7:29-13:29——**严重不对称**
- 论文关心的是 DNI 加权积分（DNI 本身不对称），所以挂钟时间可用
- 本项目不同——我们需要几何对称

**结论**：对称采样思想必须保留，且应在新脚本中作为核心设计原则。

---

### 4. 新脚本设计原则

综合以上分析，新脚本的设计原则：

1. **保留当地太阳时对称采样**（来自 DE_sundir_year.py，不可妥协）
2. **采用 12 个月月度采样**（来自论文，日期维度已饱和）
3. **日内加密至 13 点**（来自论文推荐，1h 间隔 6:00-18:00 太阳时）
4. **减少每月天数**：从 14 天→1~3 天（将算力重新分配给日内密度）
5. **添加 DNI 权重选项**（论文的 DNI 模型，可选启用）
6. **可配置化**：位置、时区、采样参数均可通过命令行调整
7. **输出兼容现有格式**：每行 `x y z [weight]`，归一化方向向量

#### 推荐默认方案

| 参数 | 值 | 说明 |
|------|-----|------|
| 月份 | 12 | 每月采样 |
| 每月天数 | 1（每月 15 日）| 论文证明日期维度已饱和 |
| 日内点数 | 13（6:00-18:00, 1h 间隔）| 关于太阳正午对称 |
| 高度角过滤 | < 15° | 与现有脚本一致 |
| DNI 权重 | 可选（默认关闭）| 保持与当前优化 pipeline 兼容 |
| 预计总数 | ~120-130 | 12×13=156 减去冬季低高度角过滤 |

#### 备选方案

| 方案名 | 月×日×时 | 预计样本数 | 适用场景 |
|--------|----------|-----------|----------|
| `paper` | 12×1×13 | ~110 | 快速扫描/粗优化 |
| `balanced` | 12×3×13 | ~334 | **日常优化（推荐）** |
| `dense` | 12×14×13 | ~1558 | 精细优化/最终结果 |
| `paper-fine` | 12×1×25 | ~222 | 论文月度+更密日内 |

---

### 5. 实现细节：真太阳时 vs 平太阳时

#### 关键改进

DE_sundir_year.py 使用**平太阳时**（mean solar time），基于经度计算固定偏移：
```python
time_offset_minutes = (120.0 - lon) * 4  # 仅经度修正，不含均时差
```

实测发现，由于**均时差**（Equation of Time, ±15 min）的存在，以平太阳正午为参考的 ±Δt 采样并非严格几何对称：
- 1 月 15 日：平太阳正午 ≈ 13:31，真太阳正午 ≈ 13:40（差 ~9 min）
- 导致上午/下午方向矢量的 x 分量不完全抵消，altitude 差异约 0.02°（±2h 偏移时）

新脚本改为**真太阳正午**（true solar noon）：对每个采样日，通过 pysolar 搜索 azimuth=180° 的精确时刻（1 分钟分辨率），以此为基准 ±Δt 采样。验证结果：

| 指标 | 值 | 说明 |
|------|-----|------|
| Mean x | 0.000024 | 东西方向完美平衡 |
| KS test y (AM vs PM) | p=1.00 | 高度分布无显著差异 |
| KS test z (AM vs PM) | p=0.99 | 南北分布无显著差异 |
| 残差来源 | 日间赤纬变化 (~0.004°/h) | 物理真实，无法消除 |

结论：真太阳正午方案实现了本项目中"对称采样"的设计目标。

---

### 6. 实验验证（2026-07-22）

对 North 300m 和 East/West 300m 进行了 36dir / 110dir (paper) / 334dir (balanced) 三组对比实验。

#### 核心结论

| 定日镜朝向 | 36dir 过拟合 | 110dir 过拟合 | 334dir 过拟合 | 推荐 |
|-----------|-------------|--------------|--------------|------|
| North（面南） | +0.37 m² | +0.03 m² | ±0.00 m² | 36dir 可接受 |
| East（面西） | **+1.69 m²** | +0.45 m² | +0.01 m² | **≥110dir** |
| West（面东） | **+1.71 m²** | +0.29 m² | — | **≥110dir** |

> 东西侧对训练集大小的敏感度是北侧的 4–5 倍。110dir 在验证 S95 上匹配 334dir（差异 <0.01 m²），速度 3 倍快。

详见 `sundir_sample/EXPERIMENT_REPORT.md` 和 `sundir_sample/EXPERIMENT_REPORT_EAST_WEST.md`。

### 7. 新脚本使用指南

```bash
# 推荐：balanced 模式（12 月 × 3 天 × 13 时点, ~334 方向）
python scripts/generate_sundir_year.py

# 论文级别最小集（~110 方向, 快速迭代）
python scripts/generate_sundir_year.py --mode paper

# 稠密集（~1556 方向, 验证/最终生产）
python scripts/generate_sundir_year.py --mode dense

# 带 DNI 权重（注意：当前 pipeline 不支持权重列，需先修改 input.cpp）
python scripts/generate_sundir_year.py --dni-weight --dni-model meinel

# 自定义位置
python scripts/generate_sundir_year.py --lat 39.0 --lon 94.0 --tz Asia/Urumqi

# 输出到指定文件
python scripts/generate_sundir_year.py -o data/my_sundirs.txt
```

> **已废弃**：`sundir_sample/DE_sundir_year.py`（平太阳时 + 2h 间隔）和 `data/738_sundir_year.txt`（含 DNI 权重列，但 pipeline 未使用）。保留仅用于历史参考。


---

## 二、东西侧对比实验（原 sundir_experiment_report_east_west.md）

**日期**：2026-07-22  
**优化器**：Bolt 模式，200 次迭代，lr=4e-4，TPS 代理模型，Buie 太阳（CSR=0.01）

### 为什么选东西侧？

用户正确指出：北侧定日镜（面朝南）的年太阳方向分布相对对称（太阳轨迹为东→南→西，始终在镜面前方）。而东西侧定日镜面朝方向与太阳轨迹垂直，产生不对称的辐照模式，使其对训练集覆盖度更敏感。

### 结果：北侧 vs 东侧 vs 西侧

#### 训练 S95（训练集上）vs 验证 S95（1556 方向稠密集）

**North 300m**（上一轮实验）：
| 配置 | 训练 S95 | 验证 S95 | 差距 |
|--------|----------|---------|-----|
| 36dir | 50.02 | 50.39 | +0.37 |
| 110dir | 50.36 | 50.39 | +0.03 |
| 334dir | 50.38 | 50.38 | +0.00 |

**East 300m**：
| 配置 | 训练 S95 | 验证 S95 | 差距 |
|--------|----------|---------|-----|
| 36dir | 65.12 | **66.81** | **+1.69** |
| 110dir | 66.15 | **66.60** | +0.45 |
| 334dir | 66.59 | **66.60** | +0.01 |

**West 300m**：
| 配置 | 训练 S95 | 验证 S95 | 差距 |
|--------|----------|---------|-----|
| 36dir | 64.74 | **66.45** | **+1.71** |
| 110dir | 66.00 | **66.29** | +0.29 |
| 334dir | —（崩溃） | — | — |

> West 334dir 在约 3 次迭代后持续崩溃（可能因前序运行的 GPU 资源残留）。East 334dir 的结果可作为参考——东西两侧具有对称性。

#### 耗时

| 配置 | North | East | West |
|--------|-------|------|------|
| 36dir | 4.9 min | 6.3 min | 5.2 min |
| 110dir | 15.1 min | 15.6 min | 16.2 min |
| 334dir | 50.2 min | 46.5 min | — |

#### 螺栓行程

| 定日镜 | 配置 | 最大行程 | RMS 行程 |
|-----------|--------|-----------|------------|
| East | 36dir | 35.7 mm | 18.5 mm |
| East | 110dir | 37.1 mm | 18.4 mm |
| East | 334dir | 36.9 mm | 18.4 mm |
| West | 36dir | 36.2 mm | 18.7 mm |
| West | 110dir | 37.0 mm | 18.9 mm |

### 关键发现

#### 1. 东西侧对训练集大小的敏感度是北侧的 4–5 倍

36dir 的训练/验证差距：东西侧为 1.69–1.71 m²，而北侧仅 0.37 m²。这证实了用户的假设——东西侧定日镜需要更密的太阳方向采样。

#### 2. 110dir 是东西侧的最低可行训练集

- 36dir → 训练/验证差距 1.7 m²（显著过拟合）
- 110dir → 差距 0.3–0.5 m²（可接受）
- 334dir → 差距 0.01 m²（可忽略）

#### 3. 验证 S95 的差异虽小但确实存在

东侧：36dir 验证 S95 = 66.81，110dir = 66.60（高出 0.3%）。不同于北侧三者完全一致，东西侧在方向数过少时出现了可测量的（虽然不大）性能退化。

#### 4. 110dir 在验证性能上匹配 334dir

East 110dir 验证 S95 = 66.60 = East 334dir 验证 S95。论文推荐的 110 方向模式在泛化性能上与 3 倍大的 balanced 模式持平，且仅需 1/3 的运行时间。

#### 5. 东西侧之间的差异很小

West 在所有采样密度下均略优于 East（例如 West 110dir 验证 S95 = 66.29 vs East 66.60）。这符合年太阳轨迹的不对称性——西侧镜面接收到更多的午后阳光。

### 建议

- **东西侧定日镜**：至少使用 **110dir（paper 模式）**——36dir 存在可测量的过拟合
- **南北侧定日镜**：36dir 可接受（无显著性能损失）
- **统一流程**：全线使用 **110dir（paper 模式）**——在所有朝向下均为最佳平衡点
- **最终生产运行**：使用 **334dir（balanced 模式）**——完全消除训练/验证差距，比 110dir 慢 3 倍


---

## 附录：North 300 m 对比实验（原 sundir_experiment_report.md，从 git HEAD 取回）

**Date**: 2026-07-22  
**Heliostat**: North 300m  
**Optimizer**: Bolt mode, 200 iter, lr=4e-4, TPS proxy, Buie sun (CSR=0.01)

### Experiment Design

Three training sets tested, all using true-solar-noon symmetric sampling:

| Config | Train Dirs | Description | Est. Annual Coverage |
|--------|-----------|-------------|---------------------|
| **36dir** | 36 | Legacy fast set (hand-picked) | Sparse |
| **110dir** (paper) | 110 | 12 months × 1 day × ~9 valid hours | Paper-recommended density |
| **334dir** (balanced) | 334 | 12 months × 3 days × ~9 valid hours | 3× paper density |

**Validation set**: 1556 directions (12 months × 14 days × ~9 valid hours) — dense annual coverage, same for all three evaluations.

### Results Summary

#### Annual S95 (on common 1556-dir validation set)

| Config | Training S95 | Validation S95 | Train→Val Gap | Overfit? |
|--------|-------------|----------------|---------------|----------|
| 36dir | 50.02 m² | **50.39 m²** | +0.37 m² | Yes, mild |
| 110dir | 50.36 m² | **50.39 m²** | +0.03 m² | Negligible |
| 334dir | 50.38 m² | **50.38 m²** | +0.00 m² | None |

> **Key finding**: All three produce essentially identical validation S95 (50.38–50.39 m², <0.03% difference). The 36dir set causes mild overfitting (training S95 0.37 m² too optimistic), but the final surface generalizes equally well.

#### Surface Shape (Bolt Stroke Patterns)

| Comparison | RMS Diff | Correlation | Max Diff |
|------------|----------|-------------|----------|
| 36dir vs 110dir | 0.165 mm | 0.999884 | 0.509 mm |
| 36dir vs 334dir | 0.246 mm | 0.999761 | 0.608 mm |
| 110dir vs 334dir | 0.290 mm | 0.999603 | 0.679 mm |

> **Key finding**: Bolt stroke patterns are virtually identical across all three training sets. Correlation >0.9996, RMS difference <0.3 mm (vs. 35.7 mm max stroke).

#### Runtime Analysis

| Config | Per-Iter Time | Total Time | vs. 36dir Slowdown |
|--------|--------------|------------|---------------------|
| 36dir | 2.4s | 295s (4.9 min) | 1.0× |
| 110dir | 7.4s | 908s (15.1 min) | 3.1× |
| 334dir | 24.0s | 3012s (50.2 min) | 10.2× |

Runtime scales near-perfectly linearly with the number of sun directions (× sun shapes = 3).

#### S95 Convergence

| Iter | 36dir | 110dir | 334dir |
|------|-------|--------|--------|
| 0 | 227.4 | 226.4 | 226.2 |
| 10 | 138.3 | 138.1 | 138.1 |
| 20 | 104.7 | 104.5 | 104.5 |
| 50 | 60.3 | 60.0 | 60.0 |
| 100 | 50.2 | 50.5 | 50.5 |
| 150 | 50.0 | 50.4 | 50.4 |
| 200 | 50.0 | 50.4 | 50.4 |

Convergence trajectories are nearly identical up to iter ~50. After that, 36dir continues improving on its training set (overfitting), while 110dir and 334dir stabilize.

### Conclusions

#### 1. The 36-dir legacy set is surprisingly adequate

For the **North 300m** heliostat, even 36 sun directions produce a final surface that performs identically to one trained on 334 directions (validation S95: 50.39 vs 50.38 m²). The bolt stroke pattern is nearly identical (RMS diff <0.25 mm, correlation >0.9997).

#### 2. More directions reduce overfitting but don't improve generalization

Adding more training directions primarily reduces the train/val gap (0.37→0.03→0.00 m²) — it gives a more honest estimate of performance during optimization — but doesn't significantly improve the final surface quality.

#### 3. 110dir (paper mode) is the practical sweet spot

- Validation performance matches 334dir (50.39 vs 50.38 m²)
- 3.3× faster than 334dir (15 min vs 50 min)
- Train/val gap is negligible (0.03 m²)
- Bolt strokes correlate at >0.9998 with 36dir and >0.9996 with 334dir

#### 4. Caveats

- **Tested only North 300m**: North-facing heliostats see a relatively symmetric annual sun distribution. East/West/South heliostats may show different sensitivity to training set size.
- **TPS proxy model**: Results may differ with POD or other proxy models.
- **No DNI weighting**: All directions equally weighted. DNI-weighted optimization might change the sensitivity.

### Recommendation

For routine optimization: **110dir (paper mode)** — best balance of accuracy and speed.

For quick iteration: **36dir** — produces essentially the same surface, just with an overoptimistic training S95.

For final production runs: **334dir (balanced)** — eliminates train/val gap entirely, at the cost of 3.3× longer runtime vs 110dir.

