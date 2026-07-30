# 110dir 复核操作文档（台式机执行）

> **任务**：把 Phase 2/3 的核心结论从 36dir 复核到 110dir——验证"结构性重力地板"不是稀疏采样的伪影。
> **预计耗时**：eval 三件套 ~1h；两个训练组视 GPU 约 6–20h（可 overnight 串行）。

## 0. 为什么必须复核（目的）

论文全部定量结论（地板 ~76.2/94.3/76.2 m²、回收率 ~15%、结构性残余 84–87%）都来自 **36dir**
（36 个太阳方向）训练。而 `sundir_sample/EXPERIMENT_REPORT_EAST_WEST.md` 早已证明：
**E/W 镜对稀疏采样过拟合达北侧 4–5 倍，110dir 是最低可行训练集**——36dir 可能高估 E/W 侧 ~1.7 m²。

核心证伪点：**若地板在 110dir 下消失或大幅移动，"35 螺栓结构性地板"就是采样伪影，
整条论文主线垮塌。** 这是投稿前必须自己先打的一枪。附带产出 110dir 基线
（B_ideal/B_naive/B_comp@110）作论文终稿数字。

## 1. 环境自检（幻影重力教训，必做）

```bash
git pull
stat -c %s data_proxy/gravity_10deg.bin    # 必须 12288
ls data/init_comp/North_300m_bolt_init.txt # 110dir comp init 在位
```

每个任务启动后**立刻眼检日志**：
- 必须含 20 行 `Loaded gravity_*deg.bin (3-plane, ...)`；
- `_eval_lsq_c1_110` 的 East init 必须 ≈ **77.9**（真实重力）；若为 ≈65.7 → 幻影重力，停止报告。

## 2. 执行顺序与命令

```bash
# ① 110dir 基线 eval（各 ~20 min，共 ~1h）——产出 B_ideal / B_naive / B_comp @110
./build/src/Release/bezier_opt.exe configs/_eval_lsq_c0_110.json   # B_ideal@110
./build/src/Release/bezier_opt.exe configs/_eval_lsq_c1_110.json   # B_naive@110（East init 眼检点）
./build/src/Release/bezier_opt.exe configs/_eval_comp_c1_110.json  # B_comp@110

# ② B*@110（无重力下界，200 iter，patience 早停，~数小时）
./build/src/Release/bezier_opt.exe configs/_bound_nograv_300m.json

# ③ a0@110（重力下端到端，comp init，100 iter，~数小时）
./build/src/Release/bezier_opt.exe configs/_fw_tanh_a0_110.json
```

②③建议 overnight 串行：`... _bound_nograv_300m.json > logs/_bound_nograv_300m.log 2>&1 && ... _fw_tanh_a0_110.json > logs/_fw_tanh_a0_110.log 2>&1`

> 说明：`_bound_nograv_300m.json` 与三个 `_eval_*_110.json` 为仓库既有/新增配置，无需改动；
> `_fw_tanh_a0_110.json` 由 a0 改三处关键词生成（sun→110dir、init→data/init_comp/、
> output→results_fw_tanh_a0_110、iter 150→100）。

## 3. 判定标准（对照 36dir 既有值）

36dir 参考：B_ideal 51.32/65.68/73.51/65.60；B_naive 51.31/77.90/98.33/78.07；
B_comp 51.75/76.71/94.90/76.83；B\* 49.77/65.00/73.07/64.68；a0 终值 50.34/76.21/94.28/76.19。

| 检查 | 通过 | 证伪（立即停止并上报） |
|---|---|---|
| B\*@110 vs B\*@36 | 每镜 ±2 m² 内 | 偏差 >4 m²（采样改变下界本身） |
| a0@110 地板 | E/S/W 终值 − B\*@110 ≥ 36dir 差距（11.2/21.2/11.5）的 2/3 | 任一 E/S/W 终值距 B\*@110 < 2 m² → **地板消失，36dir 结论是采样伪影** |
| 回收率 | (naive→best)/(naive→B\*) ≈ 10–20% | ≥50%（36dir 大幅低估可达性） |
| 绝对值 | 整体上移 0–2 m² 属预期（36dir 过拟合） | 上移 >4 m²（36dir 数字完全不可信） |

## 4. 回传内容

1. 三个 eval 的四镜 S95（init 列即可）；
2. `_bound_nograv_300m.log` 与 `_fw_tanh_a0_110.log` 中每镜 `Done. Best S95` 行（含 init/reduction）；
3. 每镜平台期起始 iter（history 目测即可）；
4. 若触发证伪列：**原样贴全部日志**，不要自行解读。

---

> 对应主报告 `docs/gravity_compensation_experiment.md` §2.3 Phase 4 第 3 步。
