# 已退役脚本（2026-10-19）

从 `scripts/experiments/` 移出。**保留是为了溯源**，不再维护，不保证能直接运行。

| 脚本 | 退役原因 |
|---|---|
| `ansys_gravity.py` | 功能已并入 `scripts/generate_proxy_model.py all-ansys`（同一套 APDL 生成逻辑），保留会造成两份实现漂移 |
| `branch_adjudicate_m08.py` | 依赖 `ansys_gravity.py` 的 FEA 批处理做 m08 分支裁决（2026-07-31 一次性任务），结论已写入 `docs/phase5_report.md` |
| `gen_density_configs.py` | 脚本开头自注"一次性实验脚本，仅供溯源；ROOT 硬编码指向已删除的 worktree 路径，直接运行会报错" |
| `run_density_quick.py` | 同上，硬编码 `L:/Code/bezier_opt_desktop/.claude/worktrees/...`，且 `data/init_comp_5x3/` 等输入已不存在 |
| `validate_ellipse_tps_news.py` | 2026-07 的椭圆→TPS 验证，已由 `lsq_fit_elliptic.py`（拟合）+ `run_fea_validation.py`（验证）取代 |
| `validate_ellipse_vs_optimized.py` | 同上，一次性对比，默认读 `experiments/runs/north_300iter/`（本机无此 run） |
| `verify_ellipse_bolt_inversion.py` | 一次性验证"h_b=w_ellipse 能否复现椭圆面"，结论已写入文档，无需保留可运行版本 |

## 恢复方式

```powershell
# 单个恢复
Move-Item archive\scripts_retired_2026-10-19\ansys_gravity.py scripts\experiments\

# 全部恢复
Get-ChildItem archive\scripts_retired_2026-10-19 -Filter *.py | Move-Item -Destination scripts\experiments\
```

## 与 git 的关系

这些文件在退役前最后一次提交里仍在 `scripts/experiments/` 下，因此 `git log --follow` 仍可查到完整历史。
