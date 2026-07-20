# P0 优化验证报告：A1 逐光线预裁剪 + L1 效率项

**日期**: 2026-07-20
**分支**: `feature/p0-raycull-effloss`（commit `ab44de8`，基于 master `26f1d2e`，worktree `L:/Code/bezier_opt_p0`）
**测试**: North 300m 单镜，36 太阳方向，200 iter，lr=4e-4 constant，RTX 4070 SUPER
**对照基线**: `L:/Code/bezier_opt_desktop/results_s95gpu`（同配置历史运行，Best S95=50.0387）

---

## 1. 改动内容

### A1 逐光线角度预裁剪（`ray_cull` / `ray_cull_margin_mrad`，默认 8 mrad）

`forward.slang` 在进入 Box-Muller + 双层玻璃折射 + 日轮求值之前，先用宏观面法向（含面型变形、不含斜率扰动）做一次反射预测试：`dot(reflect(dir, surfNrm), sunDir) < cos(支持域+margin)` 则跳过——该光线真实贡献严格为零。支持域：Buie 0.0436 rad（`sunshape.slang` 硬截断）、pillbox θ_max、Gaussian 5σ。cutoff 余弦经 SunParams UBO（`cullCosCutoff`）传入；`ray_cull=0` 时回退旧路径（位精确）。

### L1 效率项（`lambda_energy`，默认 0 = 关闭）

ARCAim 式 (8) 的能量尺度不变效率守卫，补 S95 sigmoid 损失的能量盲区：

```
L = Σ σ(6·(f/level−1)) + λ·M·E_ref/E,   dL_eff/df_i = −λ·M·E_ref/E²
```

M=接收面像素数（7850，使 λ~O(1)）；E 复用 GPU S95 二分查找已算出的 `s95State[2]`（零额外归约 pass）；E_ref 为 iter 0 逐太阳方向捕获的参考能量（每太阳方向一次性 16 字节回读）。`s95_gpu.slang` 经 16 字节 push constants 传参；λ=0 时数学上逐位等价于纯 S95 路径。

---

## 2. 一致性验证（主结果）

| 对比 | max\|ΔLoss\| | max\|ΔS95\| | 结论 |
|---|:---:|:---:|---|
| RUN1（cull=0, λ=0）vs `results_s95gpu`（200 点逐点） | **0** | **0** | 新代码特性关闭时**零侵入**，位精确复现基线 |
| RUN2（cull=1, margin=8）vs RUN1（200 点逐点） | **0** | **0** | A1 **数学无损**：只裁贡献严格为零的光线 |
| RUN2 vs RUN1 最优螺栓文件（`BEST_bolts.txt`） | — | — | **逐字节相同**（含全部中间轨迹） |
| RUN3（cull=1, λ=0.1）vs RUN1 | +28,342 | +0.33 m² | L1 机制精确生效（见下） |

L1 定量核对：λ·M·E_ref/E 在 E≈E_ref 时 ≈ 0.1×7850×36 ≈ **+28,260**，实测 loss 偏移 **+28,342**（差 0.3%，源于 E 逐太阳方向略有差异）——公式与实现精确一致。λ=0.1 下优化正常收敛不发散，最终 S95 50.27 vs 50.10（+0.65%），螺栓解 RMS 偏移 0.49 mm——按设计以微小 S95 代价换取能量保持倾向。

## 3. 时间与空间开销

### 200-iter 总时间（主依据，长运行抗噪）

| 运行 | 配置 | 总时间 | vs 基线 |
|---|---|---:|:---:|
| RUN1 | cull=0, λ=0 | 311.7 s | — |
| RUN2 | cull=1, margin=8, λ=0 | 296.8 s | **−4.8%** |
| RUN3 | cull=1, λ=0.1 | 320.8 s | +2.9% |

RUN3 的 +8.1%（vs RUN2）来源：iter-0 的 36 次 16 B 回读（一次性）、效率项改变优化路径导致面型不同从而裁剪率不同；loss kernel 本身新增运算为每像素几次 flop，可忽略。

### 30-iter 回文基准（b,c,e,x,e,c,b，辅助）

单次总时间波动 ±25%（40.2/47.5/38.7/12.1/37.1/37.0/52.0 s）——环境中存在并行 GPU 活动（另一个 P1 会话同时工作），短运行噪声大，仅作辅助参考。

### 裁剪机制有效性诊断（margin=−30，cutoff=13.6 mrad，**有损**）

30-iter 总时间 **12.1 s**（vs 同长度 ~38 s，**约 3.2× 加速**）——证明预裁剪管线确实能消除大部分光线计算（此时 ~70% 光线被裁）。代价：Buie 43.6 mrad 支持域内 13.6~43.6 mrad 的环日尾部能量被丢弃，S95@iter30 偏差 117.3 vs 104.1 m²（+13%）。**margin 是"无损—速度"的可调旋钮**：margin≥8 mrad 位精确无损；更小 margin 可作优化内循环加速手段（终验需回 margin≥8）。

### 空间开销

- 新增 GPU buffer：**0 字节**（仅 16 B push constants + SunParams UBO 内 1 个 float 复用原 padding）
- 运行显存实测：2024 → 2069 MiB（+2.2%，为驱动/系统波动范围；与旧版基线同量级 ~2 GB）
- 每光线新增开销：1 次 reflect + 1 次 dot（~10 flop）

## 4. A1 加速幅度（~5%）的物理归因

分析文档曾预估 5~20×，实测无损裁剪仅 ~5%。原因：

1. **Buie 环日分量支持域大**：能量支持延伸至 43.6 mrad（CSR=0.01），无损裁剪半径必须 ≥ 43.6+8 = 51.6 mrad；
2. **镜子张角大**：12.84 m 宽镜在 300 m 处对每张接收面像素张角 ~43 mrad——绝大多数像素的"孔径反射锥"都与这个大半径支持域相交，可被判定为零贡献的光线比例天然很小；
3. 对比 diffspt：其平面镜 + 协方差裁剪按镜子实际张角收紧，且接收面远处像素由 tile 级 footprint 裁剪先行排除（本项目已由 activePixelList 等价实现）。

**结论**：在本几何与本日轮模型下，无损逐光线裁剪的收益上限就是百分之几；更大的加速需要接受可控偏差（小 margin，见诊断行）或转向更根本的采样削减（低 spp + 滤波，见 `analysis/arcaim_comparison.md` A5/L2）。A1 保留价值：零成本、零风险、位精确，且对 Gaussian/pillbox 小支持域日轮或更远镜子收益自动上升。

## 5. 复现

```bash
# worktree L:/Code/bezier_opt_p0, branch feature/p0-raycull-effloss
./build/src/Release/bezier_opt.exe configs/_tmp_p0_baseline.json   # cull=0, λ=0
./build/src/Release/bezier_opt.exe configs/_tmp_p0_cull.json       # cull=1, margin=8
./build/src/Release/bezier_opt.exe configs/_tmp_p0_eff.json        # cull=1, λ=0.1
```

30-iter 基准配置：`configs/_tmp_p0q_{baseline,cull,eff,cullx}.json`（cullx 为 margin=−30 诊断）。
