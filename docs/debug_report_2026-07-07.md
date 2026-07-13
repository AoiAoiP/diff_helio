# VSM 螺栓优化管线 — 调试与实验报告

**日期**: 2026-07-06 ~ 2026-07-07 | **GPU**: NVIDIA RTX 4070 SUPER
**定日镜**: North, 300m | **镜面**: 12.84×9.45m, 35螺栓 (7×5)

---

## 1. 实验历程概览

| 阶段 | 问题 | 修复 | S95 | Stroke |
|:---:|------|------|:---:|:---:|
| 1 | VSM 自影响错误 (28/35 螺栓) | 重生成影响函数数据 | 76.7 m² | 48.7 mm |
| 2 | 导数全零 (phi_u/phi_v/k*) | 重生成导数数据 | 228.3 m² | 81.3 mm |
| 3 | 全部 6 文件修复 | — | **52.9 m²** | 17.4 mm |
| 4 | STROKE 符号反转 (曲面凸↔凹) | 改 main.cpp 后处理 | 52.9 m² | 17.4 mm |
| 5 | Ansys 不收敛 (极端弯曲) | 加 L2 螺栓惩罚 λ=5×10⁶ | 53.2 m² | 15.7 mm |
| 6 | Flux 坐标 wrap (光斑劈开) | nGrid + azimuth 居中 | — | — |
| 7 | **cosθ 因子缺失** | shader + 梯度修正 | **81.6 m²** | 22.9 mm |

---

## 2. Bug 详解

### Bug 1: VSM 影响函数非物理

**现象**: 优化产生鞍形螺栓分布 (±25mm)，Ansys 验证为凸面。

**根因**: `fix_mfs_tikhonov.py` 生成的 VSM 系统中，35 个螺栓仅 7 个自影响 >0.3。28 个螺栓在其自身位置的响应接近零或为负。系统欠定（358 未知数，198 方程），Tikhonov 最小范数解将响应分散到全局源点。

| 指标 | 修复前 | 修复后 |
|------|:---:|:---:|
| 正常螺栓 (自影响>0.3) | 7/35 | **35/35** |
| 自影响范围 | [−0.02, 1.00] | [1.04, 1.22] |

### Bug 2: 导数数据全为零

**现象**: 自影响修复后 S95 完全不降 (228.49→228.31)。

**根因**: `phi_u/phi_v/kxx/kzz/kxz` 5 个 bin 文件全部为零。shader 中 `yu=Σh·phi_u=0`，螺栓无法改变表面法向量，光学梯度为零。

### Bug 3: STROKE 后处理曲面反转

**现象**: S95 优化正确 (76.8%)，但 Ansys 输入后曲面为凸面。

**根因**: `main.cpp` 中 `h_phys = -h_pipe` 的负号取反了曲面。由于 Σφ=1（刚体平移不变性），正确的零基准转换无需取反。

```
错误: h_stroke = -h_pipe - min(-h_pipe)  → surface_ansys ∝ -surface_shader
正确: h_stroke =  h_pipe - min( h_pipe)  → surface_ansys = surface_shader + const
```

### Bug 4: cosθ 因子缺失

**现象**: Agent 模型代理的螺栓 UY PV≈44mm vs FEA≈12mm（差 3.7×）。

**根因**: 螺栓垂直于镜面安装，倾斜 θ=58° 时竖直分量 = 行程×cosθ≈0.53×。shader 中 `y = gravity + Σ h·φ` 缺少 cosθ。

**修复**: `bolt_common.slang` 中 `y += h * phi * cosTheta`，梯度同步缩放。

| 指标 | 修复前 | 修复后 |
|------|:---:|:---:|
| S95 | 53.2 m² | 81.6 m² |
| Max stroke | 15.7 mm | 22.9 mm |
| Proxy PV | 44.6 mm | 33.2 mm |
| RMS vs FEA | 17.2 mm | **11.9 mm** |

---

## 3. Ansys 收敛与 L2 正则化

17.4mm 的螺栓行程在 4mm 薄板上产生大变形几何非线性，Ansys Mechanical 无法收敛。添加 L2 螺栓惩罚：

```cpp
// pipeline.cpp — L2 ridge penalty on bolt heights
grads[b] += lambdaBoltL2 * 2.0f * heights[b] / n;
```

| λ_l2 | Max Stroke | S95 | Ansys |
|------|:---:|:---:|:---:|
| 0 | 17.4 mm | 52.9 m² | ❌ 不收敛 |
| **5×10⁶** | **15.7 mm** | **53.2 m²** | **✅ 收敛** |
| 5×10⁷ | 11.5 mm | 60.0 m² | — |
| 2×10⁸ | 8.2 mm | 80.1 m² | — |

关键发现：仅降低 10% 行程 (17.4→15.7mm) 就跨过了 Ansys 收敛门槛，且光学性能几乎无损 (S95 +0.3)。

---

## 4. 验证结果

### 4.1 形变验证（Proxy vs FEA，3 个角度）

| 角度 | Proxy PV | FEA PV | RMS |
|:---:|:---:|:---:|:---:|
| 58.6° | 33.2 mm | 12.1 mm | 11.9 mm |
| 50.7° | — | 15.7 mm | — |
| 58.5° | — | 12.2 mm | — |

**结论**: cosθ 修复后 PV 差距从 3.7× 缩小到 2.7×。剩余差异来自 FEA 的几何非线性（大变形膜刚度），线性 VSM 无法捕捉。

### 4.2 光斑验证

GPU 光追 (Buie 太阳 + 2²⁵ Sobol + 玻璃折射 + 斜率误差) 显示：在 300m 距离下，镜面曲率（无论是 33mm 还是 12mm PV）对光斑分布几乎没有影响。光斑由宏观朝向、太阳形状和斜率误差主导。

**含义**: S95 从 228→82 的改善在代理模型内部成立，但真实物理中的光斑改善可能远小于预测。

### 4.3 用户 FEA 验证

用户将缩放前后的 STROKE 输入 Ansys，确认：
- 原始 17.4mm 行程：Ansys 不收敛
- L2=5×10⁶ (15.7mm)：收敛，产生 ~12mm PV
- 修复前 STROKE：凸面（确认了 Bug 3）
- 修复后 STROKE：凹面 ✓

---

## 5. 管线改进

### 新增配置参数

| 参数 | 默认值 | 说明 |
|------|:---:|------|
| `lambda_bolt_l2` | 0 | L2 螺栓惩罚，限制行程范围 |
| `lambda_bolt_positive` | 0 | 惩罚正 h_pipe（非物理拉力） |

### 新增命令行选项

| 选项 | 说明 |
|------|------|
| `--surface-file <path>` | 从文件加载 UY 表面（绕过螺栓计算），用于 FEA 验证 |
| `--dump-flux` | Flux dump 自动 azimuth 居中 unwrap |

### 新增脚本

| 脚本 | 用途 |
|------|------|
| `scripts/validate_deformation.py` | 变形验证：proxy vs FEA + 残差 3×3 图 |
| `scripts/visualize_flux.py` | Flux 可视化（自动居中 unwrap） |
| `scripts/interpolate_fea.py` | FEA 节点数据 → 25×25 网格插值 |

### 修改文件清单

| 文件 | 改动 |
|------|------|
| `shaders/bolt_common.slang` | cosθ 因子 |
| `shaders/bolt_forward.slang` | cosθ push constant |
| `shaders/bolt_backward.slang` | cosθ push constant + 梯度缩放 |
| `src/pipeline.cpp` | L2 惩罚 + 表面加载 + nGrid 计算 + cosθ push constant |
| `src/pipeline.h` | boltBackwardPass + uploadSurfaceFromFile 签名 |
| `src/main.cpp` | STROKE 后处理修复 + --surface-file + flux unwrap |
| `src/config.h/cpp` | lambda_bolt_l2 |

---

## 6. 关键教训

1. **SPV 加载路径**: exe 从 `shaders/` 加载 SPV，不是 `build/shaders/`。修改 `.slang` 后必须复制新 SPV 到 `shaders/` 或修改 loadSpv 路径。

2. **线性 vs 非线性**: 线性 VSM 代理模型在 >10mm 螺栓行程时系统性高估变形（几何非线性板刚度增大）。对优化来说这不一定致命——优化器找到的方向可能是对的，只是幅度被高估。

3. **光斑不敏感**: 300m 距离下，mm 级镜面曲率变化对光斑无影响。S95 优化可能对远距离定日镜意义有限。

4. **符号约定一致性**: 管线约定 (+Y 远离接收器) vs FEA 约定 (+Y 向上) vs 物理约定 (螺栓推拉方向) 三套坐标系的转换是所有 bug 的来源。

---

## 7. 后续方向

| 优先级 | 方向 | 说明 |
|:---:|------|------|
| P0 | 端到端 FEA→Optics 验证 | Ansys 变形场 + GPU 光追，确认真实 S95 改善 |
| P1 | 非线性修正 | 在代理模型中加膜刚度修正，匹配 FEA 非线性响应 |
| P1 | 近场定日镜测试 | 短距离下曲率效应更显著，S95 改善可能更真实 |
| P2 | 重力符号验证 | 确认 gravity UY 符号在 shader 中的正确性 |
