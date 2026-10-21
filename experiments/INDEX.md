# 实验台账（experiments/INDEX.md）

> 本文件登记本仓库的每一次实验运行：既有运行、已归档运行、计划中的补跑。
> 规程见 `AGENTS.md` §8；论文 claim 与证据的完整对照见本次整理报告（B 部分）。
> 状态取值：`done` / `partial` / `planned` / `invalid`（口径作废但保留证据）/ `offsite`（不在本机）。

---

## 1. 论文 claim 索引

正文与摘要里的每条结论对应一个编号，实验行与图行都引用它。

| ID | claim（正文口径） | 位置 |
|---|---|---|
| K1 | 物理耦合可微渲染：结构形变到光斑对螺栓行程端到端可微 | §3、§4.3、§4.4 |
| K2 | 光学模块与已发表 RMCRT 前向模型一致（面型匹配、能量差） | §4.2 |
| K3 | TPS 代理可复现 FEA 形变（RMS / R² / shape_corr） | §4.1 |
| K4 | 重力对光路的影响显著且随镜位强烈变化 | §5.2 |
| K5 | 重力畸变主体是螺栓网格之外悬挑带的高阶凹陷 | §5.2 |
| K6 | 固定 35 栓布局下 84%–87% 的优化差距结构性不可达 | §5.3 |
| K7 | 结构层重设计（边距 / 密度 / 材料）压低结构性界限 | §5.4 |
| K8 | 结论在 20 面镜全场泛化 | §5.5 |
| K9 | 相对离线串行范式的评估次数与时间优势 | §4.4 |
| K10 | 能量效率项 λ_E 的取值依据与能量守恒 | §3.4、§5.1 |
| K11 | 代理误差折算到光斑层面的预算（S95 偏乐观 6%–8%） | §4.2 |
| K12 | 46° 附近的几何非线性反转点 | §5.2 |
| K13 | 334 方向采样对年均 S95 已饱和 | §5.1 |

---

## 2. 本机既有运行

| ID | 目录 | 目的 | claim | 配置 | 口径 | 状态 |
|---|---|---|---|---|---|---|
| R-00 | `experiments/runs/_smoke_20261019/` | 迁移后冒烟验证（新输出路径 + 三平面重力加载） | — | `experiments/_smoke_20261019.json` | 1 镜 / 36 dir / 1 iter / coupling=1 | done |
| R-36-01 | `experiments/runs/bound_300m_36/` | 无重力端到端下界 B\*（300 m N/E/S/W） | K6 | `configs/archive/_bound_nograv_300m_36.json` | 36 dir / 200 iter / 无重力 | done |
| R-36-02 | `experiments/runs/lsq_eval_c0_36/` | B_ideal：椭圆 LS 螺栓 + 无重力，1 iter | K4、K6 | `_eval_lsq_c0_36.json` | 36 dir / 1 iter / coupling=0 | done |
| R-36-03 | `experiments/runs/lsq_eval_c1_36/` | B_naive：LS 螺栓 + 真实重力 | K4、K6 | `_eval_lsq_c1_36.json` | 36 dir / 1 iter / coupling=1 | done |
| R-36-04 | `experiments/runs/comp_eval_c1_36/` | B_comp：闭式补偿初值 + 真实重力 | K6 | `_eval_comp_c1_36.json` | 36 dir / 1 iter / coupling=1 | done |
| R-36-05 | `experiments/runs/fw_tanh_a0/` | 九组消融之 a0（tanh、无锚定） | K6 | `_fw_tanh_a0.json` | 36 dir / 200 iter | done |
| R-36-06 | `experiments/runs/fw_tanh_a1e3/` | 锚定 1e-3 | K6 | `_fw_tanh_a1e3.json` | 同上 | done |
| R-36-07 | `experiments/runs/fw_tanh_a1e3_b1e2/` | 锚定 1e-3 + 弯曲能 1e-2 | K6 | `_fw_tanh_a1e3_b1e2.json` | 同上 | done |
| R-36-08 | `experiments/runs/fw_tanh_a1e4/` | 锚定 1e-4 | K6 | `_fw_tanh_a1e4.json` | 同上 | done |
| R-36-09 | `experiments/runs/fw_tanh_a1e5/` | 锚定 1e-5 | K6 | `_fw_tanh_a1e5.json` | 同上 | done |
| R-36-10 | `experiments/runs/fw_tanh_naiveinit/` | naive 初值（init 无关性） | K6 | `_fw_tanh_naiveinit.json` | 同上 | done |
| R-36-11 | `experiments/runs/fw_nt_a1e3_soft1e5/` | 无 tanh + 软墙 1e-5 | K6 | `_fw_nt_a1e3_soft1e5.json` | 同上 | done |
| R-36-12 | `experiments/runs/fw_nt_a1e3_soft1e6/` | 无 tanh + 软墙 1e-6 | K6 | `_fw_nt_a1e3_soft1e6.json` | 同上 | done |
| R-36-13 | `experiments/runs/fw_nt_soft1e5/` | 无 tanh + 软墙，无锚定 | K6 | `_fw_nt_soft1e5.json` | 同上 | done |

> 13 个目录已于 2026-10-19 从根目录 `results_*` 迁入 `experiments/runs/`，并同步修改了 `src/config.h`、`src/pipeline.cpp`（4 处硬编码）、119 个配置的 `output_dir` 与 13 个脚本的路径。旧路径不再存在；`.gitignore` 的 `results_*/` 仅作护栏。

---

## 3. 不在本机（台式机 / 外置归档 `L:/Code/_archive_bezier_paper_prep/`）

> 下表是归档时的旧命名（`results_*`），**没有迁入本仓库**；若日后同步回来，放到 `experiments/runs/<同名去前缀>/` 并在本表登记新路径。

| ID | 目录或产物 | 目的 | claim | 现状 |
|---|---|---|---|---|
| A-01 | `results_4mirror_200iter/`（含 `fea_validation/`） | 2026-07 四面镜基线与代理 vs FEA 验证（带螺栓行程） | K3、K11 | 不在本机；表 5 与 §4.1 的数字来源 |
| A-02 | `results_Field/` | 20 镜 λ_E=0 端到端优化 | K8 | 不在本机；只剩 `data/lsq_vs_opt_334d.csv` |
| A-03 | Phase 5 margin / density 外环原始 | 边距 0.08→0.03、密度 5×3→11×9 | K7 | 归档于外置盘；数值已转录 `docs/phase5_report.md` §3.1.3、§3.2.2 |
| A-04 | `results_final_m05/` | m\*=0.05 交付包（布局坐标 + 行程 + 面型/光斑图 + 334dir 终评） | K7 | 不在本机 |
| A-05 | `validation/pre_fea_validation/`、`validation/post_fea_validation/` | APDL vs GUI vs Proxy 三路验证 | K3 | 不在本机，且被 `.gitignore` 排除 |
| A-06 | λ 扫描运行目录（1200 m λ=0.1/0.3/0.5、900 m λ=0.5） | 能量项权重选择 | K10 | 结果目录不在本机，只剩文档里的汇总表 |

---

## 4. 计划中的补跑（最小集合）

只列"补齐一个 claim 所需的最小实验"；能在改稿层面解决的（K3、K4、K5、K7 的口径问题）不列。

| ID | 目的 | 补齐 | 最小规模 | 复用资产 | 成本 | 产出 |
|---|---|---|---|---|---|---|
| E-01 | 带螺栓行程的 proxy vs FEA 光斑预算 | K11、图 5/图 6 | North 300 m，29.5° + 58.5°，同一行程文件 | `run_fea_validation.py`、`validation/flux_fea_vs_proxy/` | 需台式机 FEA 点云；渲染 <5 min | 图 5、图 6 的代理误差面板 |
| E-02 | 与已发表 RMCRT 的同面型交叉校验 + 噪声地板 | K2、图 6 | 1 个面型 × 1 个太阳方向 × 两侧渲染 × 2 次重复 | 外部模型 | 协议已写死在 `docs/flux_fea_vs_proxy_validation_guide.md` | 图 6 的并排面板 |
| E-03 | 远距表 4 行重评（λ_E=0.5） | K8 | 900/1200 m × 4 向，1 iter 评估 | `_eval_1200m_reg.json`、`bolt_optimize_*_lam0.5.json` | 8 次 1-iter 评估，<10 min | 表 4 替换行或删行依据 |
| E-04 | 核 `lsq_s95_334d` 列口径 | K8 | 4 镜 × 1 iter（`disable_gravity` 开/关各一次） | `_eval_lsq_c0/c1_36.json` 改 334 版 | <10 min | 表 4 的列注 |
| E-05 | 梯度步长扫描（差分符号翻转） | K1、图 7 | `--check-grad` × 3 个步长 | 现有配置 | 分钟级 | 图 7 的步长曲线 |
| E-06 | 分阶段计时 + 离线 FEA 耗时 | K9、图 8 | 在 `pipeline.cpp` 加 2–3 个计时点，跑 1 次 36dir | — | 半小时 | 图 8、§4.4 的时间换算 |
| E-07 | 20 镜真实重力面型评估（统一 §5.5 口径到 334dir） | K4、K8 | 20 镜 × 1 iter | `_eval_lsq_c1_*` 改 334 版 | <15 min | §5.5 惩罚表的统一口径 |
| E-08 | 导出 334 方向的月份分布 | K13 | 重跑 `generate_sundir_year.py` 打印日期字段 | `data/334_sundir_balanced.txt` | 秒级 | §5.1“各月 21–33”的可核依据 |

---

## 5. 登记模板

新实验追加一行：

```
| E-YYYYMMDD-slug | 一句话目的 | K? | configs/... 或 scripts/... | 方向数 / 迭代 / coupling / 日期 | planned 或 done | 输出路径 |
```

原始输出一律放 `experiments/runs/<ID>/`；配置里的 `output_dir` 已全部改写为该形式（含 `configs/archive/` 的 98 个历史配置），程序默认值也已改为 `experiments/runs/unnamed`。不要在根目录再新建 `results_*`。
