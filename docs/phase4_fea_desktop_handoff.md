# Phase 4 FEA 抽查操作文档（台式机执行）

> **任务**：用 ANSYS FEA 复算 Phase 3 优化终态螺栓下的重力畸变，与 TPS proxy 对比，
> 判定"重力地板是真实物理还是 proxy 伪影"。
> **前置**：台式机装有 ANSYS（笔记本无 ANSYS 组件，故移交本机执行）。
> **预计耗时**：10–40 分钟（3 角度 × 单次静态 FEA）。

## 0. 为什么做这个抽查（背景一分钟版）

Phase 3 结论：E/S/W 镜重力惩罚的 84–87% 是 35 螺栓结构不可达的"硬地板"
（South 300m 最大：naive 98.33 → 地板 94.28 → B\* 73.07 m²）。
该结论全部建立在 TPS proxy 的重力形变之上。若 proxy 系统性高估重力畸变，
地板可能被夸大。South 300m 惩罚最大——若地板是 proxy 伪影，在这里暴露最明显。
本抽查是该结论的最后一道独立验证（此前 proxy vs FEA 验证见
`validation/post_fea_validation/summary_table.md`，RMS ~2.8–3.3 mm, shape_corr 0.95–0.96，
但那些是 2026-07-17/21 旧螺栓配置的抽查，未覆盖本次 Phase 3 终态螺栓）。

## 1. 环境自检（必须先做，两条都过才能继续）

```bash
git clone git@github.com:AoiAoiP/diff_helio.git   # 或全新 clone：2026-07-30 历史已重写，旧本地副本不可 pull，须重新 clone
git log --oneline -1                                # 确认在最新 master（含本文档）

# ① v2 重力数据完整性（幻影重力事故教训，见主报告 §1.6）
stat -c %s data_proxy/gravity_10deg.bin    # 必须是 12288；若为 4096 立刻停止并报告

# ② 被测螺栓文件在位（repo 已含，无需生成）
ls results_fw_tanh_a0/South_300m_STROKE_bolts.txt
```

注意：`--compare` 步骤会用 `data_proxy/` 的影响函数与重力 bin 计算 proxy 侧形变，
bins 不对则对比结论无效。

## 2. Dry-run（不启动 ANSYS，验证管线与路径）

```bash
python scripts/run_fea_validation.py \
    --result-dir results_fw_tanh_a0 --heliostat-prefix South_300m \
    --angles 29.5 --dry-run
```

预期：`apdl_bolt_stroke_29.5deg.dat (14.0 KB)` 生成成功，无任何 ERROR。
若 ANSYS 路径与脚本默认不同，先记下实际路径，正式运行时加 `--ansys-exe`（见 §4）。

## 3. 正式运行（3 角度：0° / 29.5° / 58.5° + proxy 对比）

```bash
python scripts/run_fea_validation.py \
    --result-dir results_fw_tanh_a0 --heliostat-prefix South_300m \
    --compare 2>&1 | tee logs/_phase4_fea_south300m.log
```

- 被测量：`results_fw_tanh_a0/South_300m_STROKE_bolts.txt`
  （a0 基线组优化终态螺栓行程，35 螺栓，范围 0–37.8 mm）。
- 成功标志：`=== FEA Validation done: 3/3 angles ===`，且日志输出
  FEA vs proxy 的对比表（RMS / R² / shape_corr / PV ratio）。

### 可选第二镜（阴性对照，+10 分钟）

```bash
python scripts/run_fea_validation.py \
    --result-dir results_fw_tanh_a0 --heliostat-prefix North_300m \
    --compare 2>&1 | tee logs/_phase4_fea_north300m.log
```

North 重力惩罚 ≈0（地板残余仅 0.57 m²），预期 FEA/proxy 形变都小；
若 North 对比良好而 South 恶劣，说明问题随惩罚规模增长（指向 proxy 高应力区失真）。

## 4. 故障排查

| 症状 | 处置 |
|---|---|
| `ERROR: ANSYS not found at L:/...` | 脚本默认路径是 `L:/Program Files/ANSYS Inc/v252/ansys/bin/winx64/ANSYS252.exe`。确认台式机实际安装位置，加 `--ansys-exe "<实际路径>"` |
| ANSYS 启动但报 license 错误 | 确认 license manager 运行中（`ansyslmcenter`）；重试 |
| 某角度求解不收敛 | 记录该角度日志；0° 与 58.5° 成功也足以判定（29.5° 非必需） |
| `gravity_10deg.bin` 为 4096 B | **停止**——仓库数据未正确拉取（幻影重力环境），先解决数据问题再跑 |

## 5. 判定标准（拿到对比表后）

| 结果 | 判定 | 后续 |
|---|---|---|
| RMS ~2–3.3 mm 且 shape_corr ~0.95–0.96（与历史验证同水平） | **地板为真实物理**，Phase 3 结论通过独立验证 | 回传结果，写入主报告 §3.7，Phase 4 收口 |
| RMS 显著更大（≥2× 历史水平）或 shape_corr <0.9 | proxy 在优化终态螺栓+重力组合下失真，地板量级存疑 | **停止并回传全部日志**，重新评估结论强度 |
| FEA 畸变显著小于 proxy（PV ratio 远离 1） | 同上，可能高估地板 | 同上 |

## 6. 结果回传

1. 将日志末尾的对比表（每角度 RMS / R² / shape_corr / PV ratio）原样贴回会话；
2. `results_fw_tanh_a0/fea_validation/` 目录（CSV + fea_metadata.json + 日志）保留待 commit；
3. 若跑了 North 对照，一并贴出。

---

> 本文件对应主报告 `docs/gravity_compensation_experiment.md` §2.3 Phase 4 第 2 步。
> 执行完成后主报告将补记 §3.7（FEA 抽查结果）。
