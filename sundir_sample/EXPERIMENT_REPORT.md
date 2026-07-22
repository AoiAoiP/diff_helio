# Sundir Sampling Comparison Experiment

**Date**: 2026-07-22  
**Heliostat**: North 300m  
**Optimizer**: Bolt mode, 200 iter, lr=4e-4, TPS proxy, Buie sun (CSR=0.01)

## Experiment Design

Three training sets tested, all using true-solar-noon symmetric sampling:

| Config | Train Dirs | Description | Est. Annual Coverage |
|--------|-----------|-------------|---------------------|
| **36dir** | 36 | Legacy fast set (hand-picked) | Sparse |
| **110dir** (paper) | 110 | 12 months × 1 day × ~9 valid hours | Paper-recommended density |
| **334dir** (balanced) | 334 | 12 months × 3 days × ~9 valid hours | 3× paper density |

**Validation set**: 1556 directions (12 months × 14 days × ~9 valid hours) — dense annual coverage, same for all three evaluations.

## Results Summary

### Annual S95 (on common 1556-dir validation set)

| Config | Training S95 | Validation S95 | Train→Val Gap | Overfit? |
|--------|-------------|----------------|---------------|----------|
| 36dir | 50.02 m² | **50.39 m²** | +0.37 m² | Yes, mild |
| 110dir | 50.36 m² | **50.39 m²** | +0.03 m² | Negligible |
| 334dir | 50.38 m² | **50.38 m²** | +0.00 m² | None |

> **Key finding**: All three produce essentially identical validation S95 (50.38–50.39 m², <0.03% difference). The 36dir set causes mild overfitting (training S95 0.37 m² too optimistic), but the final surface generalizes equally well.

### Surface Shape (Bolt Stroke Patterns)

| Comparison | RMS Diff | Correlation | Max Diff |
|------------|----------|-------------|----------|
| 36dir vs 110dir | 0.165 mm | 0.999884 | 0.509 mm |
| 36dir vs 334dir | 0.246 mm | 0.999761 | 0.608 mm |
| 110dir vs 334dir | 0.290 mm | 0.999603 | 0.679 mm |

> **Key finding**: Bolt stroke patterns are virtually identical across all three training sets. Correlation >0.9996, RMS difference <0.3 mm (vs. 35.7 mm max stroke).

### Runtime Analysis

| Config | Per-Iter Time | Total Time | vs. 36dir Slowdown |
|--------|--------------|------------|---------------------|
| 36dir | 2.4s | 295s (4.9 min) | 1.0× |
| 110dir | 7.4s | 908s (15.1 min) | 3.1× |
| 334dir | 24.0s | 3012s (50.2 min) | 10.2× |

Runtime scales near-perfectly linearly with the number of sun directions (× sun shapes = 3).

### S95 Convergence

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

## Conclusions

### 1. The 36-dir legacy set is surprisingly adequate

For the **North 300m** heliostat, even 36 sun directions produce a final surface that performs identically to one trained on 334 directions (validation S95: 50.39 vs 50.38 m²). The bolt stroke pattern is nearly identical (RMS diff <0.25 mm, correlation >0.9997).

### 2. More directions reduce overfitting but don't improve generalization

Adding more training directions primarily reduces the train/val gap (0.37→0.03→0.00 m²) — it gives a more honest estimate of performance during optimization — but doesn't significantly improve the final surface quality.

### 3. 110dir (paper mode) is the practical sweet spot

- Validation performance matches 334dir (50.39 vs 50.38 m²)
- 3.3× faster than 334dir (15 min vs 50 min)
- Train/val gap is negligible (0.03 m²)
- Bolt strokes correlate at >0.9998 with 36dir and >0.9996 with 334dir

### 4. Caveats

- **Tested only North 300m**: North-facing heliostats see a relatively symmetric annual sun distribution. East/West/South heliostats may show different sensitivity to training set size.
- **TPS proxy model**: Results may differ with POD or other proxy models.
- **No DNI weighting**: All directions equally weighted. DNI-weighted optimization might change the sensitivity.

## Recommendation

For routine optimization: **110dir (paper mode)** — best balance of accuracy and speed.

For quick iteration: **36dir** — produces essentially the same surface, just with an overoptimistic training S95.

For final production runs: **334dir (balanced)** — eliminates train/val gap entirely, at the cost of 3.3× longer runtime vs 110dir.
