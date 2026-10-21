# scripts/ 脚本索引

> 2026-10-19 分拣后的状态。三个位置的约定：
> - `scripts/`：**仍在用**的工具（数据生成、验证、对比、分析）
> - `scripts/experiments/`：**历史一次性实验**，保留供溯源，不保证开箱即跑
> - `archive/scripts_retired_2026-10-19/`：**已退役**（被替代或路径失效），见该目录 README

运行约定：全部从仓库根目录执行，`python scripts\<name>.py`；输入输出路径相对仓库根。
ANSYS 相关脚本的默认 `ANSYS.exe` 路径是 `L:/Program Files/ANSYS Inc/v252/...`（台式机），本机运行需用参数覆盖。

---

## 一、核心（数据与实验主线）

| 脚本 | 作用 | 依赖 / 输出 | 被谁引用 |
|---|---|---|---|
| `generate_proxy_model.py` | TPS 影响函数 + 20-bin 三平面重力；`all-ansys` 子命令直接跑 MAPDL | ANSYS（仅 all-ansys）→ `data_proxy/` | AGENTS §5、README |
| `generate_sundir_year.py` | 全年太阳方向采样（balanced 334 / paper 110 / dense 1558） | 纯 Python → `data/*_sundir*.txt` | AGENTS §5、`sundir_sampling.md` |
| `run_fea_validation.py` | 带螺栓行程的 FEA 点云 vs TPS proxy（形变 + 光斑） | ANSYS → `experiments/runs/<id>/fea_validation/` | AGENTS §6、`flux_fea_vs_proxy_validation_guide.md` |
| `run_flux_validation.py` | FEA 面型 vs proxy 面型的光斑对比（S95、能量） | 纯 Python + 已有 npy | 同上 |
| `post_fea_validation.py` | APDL vs GUI vs Proxy 三路形变验证 | ANSYS（可选） | AGENTS §6、`bolt_position_optimization_stage_report.md` |

## 二、分析工具（出论文里的数字/表）

| 脚本 | 作用 | 产出 |
|---|---|---|
| `gravity_decomposition.py` | 重力场三频带分解（仿射/二次/高阶凹陷）与可补偿性诊断 | `analysis/gravity_compensability_report.*` |
| `layout_scan_analysis.py` | 布局扫描的斜率统计（margin/密度对比） | `analysis/layout_scan_report.md`、`margin_full_report.md` |
| `material_swap_analysis.py` | 镜面材料替换的形变场相似度 | `analysis/material_swap_report.md` |
| `compare_lsq_vs_opt.py` | 20 镜「理想椭圆 / 端到端优化」S95 对比 | `data/lsq_vs_opt_334d.csv`（论文表 4） |
| `compare_results.py` | 不同 sundir 训练集的结果对比 | 终端表；默认读 `experiments/runs/sundir_cmp_*`（需先有这些 run） |
| `compare_flux.py` | 两组 `--dump-flux` NPY 的光斑对比（S95/相关/能量） | 终端表 / CSV |
| `compute_s95_from_flux.py` | 从 NPY 光斑算 S95（与 C++ 同一二分语义） | CSV；被 `dump_final_spots.py` 复用 |

## 三、拟合与初始化

| 脚本 | 作用 | 产出 |
|---|---|---|
| `lsq_fit_elliptic.py` | 理想椭圆面 → TPS 最小二乘螺栓初值 | `data/init/*_lsq_bolt_init.txt`、`lsq_fit_summary.csv` |
| `lsq_fit_compensated.py` | 椭圆 LSQ + 斜率空间闭式重力补偿初值 + 锚定 buffer | `data/init_comp*/`、`*_anchor.bin` |

## 四、一次性实验（Phase 5.4 / 6，支线已收口）

| 脚本 | 作用 | 状态 |
|---|---|---|
| `tps_position_sensitivity.py` | TPS 螺栓位置灵敏度（直接法，Phase 6 G0a） | 可运行；结论见阶段报告 |
| `pos_joint_optimize.py` | Phase 6 栓位×行程联合优化驱动 | 可运行；依赖 `data_pos/`（本机已归档） |
| `pos_joint_optimize_bold.py` | 同上，bold top-K 版本 | 同上 |
| `plot_layout_surfaces.py` | Phase 5.3/5.4 布局与重力场可视化 | 依赖 `data_proxy_margin/`、`data_proxy_truth/`（本机已归档） |

## 五、共享库

| 文件 | 作用 |
|---|---|
| `layout_utils.py` | 螺栓布局 JSON 解析（grid / lines / free 三形式），被 Phase 5.4/6 与绘图脚本 import |

---

## 六、`scripts/experiments/`（历史一次性，保留溯源）

| 脚本 | 用途 |
|---|---|
| `dump_final_spots.py` | 终版交付包的光斑图（bare vs optimized） |
| `export_final_package_m04.py` | 终版交付包导出（布局 + 行程表 + 面型图） |
| `g0_layout_interp_validation.py` | G0 门：重力场能否跨布局线性插值 |
| `g2_lasso_recovery.py` | G2 门：稀疏布局 LASSO 的合成支撑恢复 |

> 这些脚本依赖已归档到外置盘的 `data_pos*/`、`data_proxy_margin/`、`data_proxy_truth/`，
> 在本机直接跑会缺输入；保留是为了能对照当年的实验设计。

---

## 七、`scripts/remote/`（台式机远程访问）

| 脚本 | 作用 |
|---|---|
| `check-readiness.ps1` | 只读自检，输出 JSON 与 READY / NOT_READY 判定 |
| `complete-sshd-setup.ps1` | OpenSSH Server 完整安装（幂等） |
| `add-laptop-key.ps1` | 把笔记本公钥写入 `administrators_authorized_keys` |
| `diagnose-sshd-start.ps1` | 诊断 sshd 1067 启动失败 |
| `fix-sshd-hostkey-owner.ps1` | 修复主机密钥 owner/ACL（`no hostkeys available`） |

细节、Tailscale 拓扑与排障见 `docs/remote_desktop_workflow.md`。

## 八、新增脚本的规矩

1. 数据生成/验证类放 `scripts/`；一次性实验放 `scripts/experiments/`；不要新建第三个层级。
2. 路径用仓库根相对路径，不要硬编码 `L:/` 或 `D:/`；必须写死时给 `--root` 参数。
3. 输出落 `experiments/runs/<ID>/` 或 `analysis/`，不要写根目录 `results_*`。
4. 脚本产生论文里的数字时，在 `experiments/INDEX.md` 登记一行。
