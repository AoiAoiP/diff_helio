#include "config.h"
#include "input.h"
#include "pipeline.h"
#include "vulkan_app.h"
#include <fmt/core.h>
#include <algorithm>
#include <chrono>
#include <numeric>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>

namespace fs = std::filesystem;

static void saveNpy(const std::string &path, const std::vector<float> &data, const std::vector<size_t> &shape) {
    std::ofstream f(path, std::ios::binary);
    f.write("\x93NUMPY", 6);
    f.put(1); f.put(0);
    std::string header = "{'descr': '<f4', 'fortran_order': False, 'shape': (";
    for (size_t i = 0; i < shape.size(); i++) {
        header += std::to_string(shape[i]);
        if (i + 1 < shape.size()) header += ", ";
    }
    header += ")}";
    int pad = 16 - ((10 + (int)header.size() + 1) % 16);
    for (int i = 0; i < pad; i++) header += ' ';
    header += '\n';
    uint16_t headerLen = (uint16_t)header.size();
    f.write((const char *)&headerLen, 2);
    f.write(header.data(), header.size());
    f.write((const char *)data.data(), data.size() * sizeof(float));
}

static void saveControlPoints(const std::vector<float> &cy, const std::string &path, const std::string &meta = {}) {
    std::string txtPath = path + ".txt";
    std::ofstream f(txtPath);
    f << "# Bezier surface control points (4x4)\n";
    if (!meta.empty()) f << "# " << meta << "\n";
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 4; j++)
            f << fmt::format("{} {} {:.8f}\n", i, j, cy[i * 4 + j]);
    f.close();
    saveNpy(path + ".npy", cy, {4, 4});
    fmt::print("  Saved: {} and {}.npy\n", txtPath, path);
}

int main(int argc, char *argv[]) {
    try {
        setvbuf(stdout, NULL, _IONBF, 0); // unbuffered output for logging
        fmt::print("=== Bezier Heliostat Surface Optimizer ===\n");
        std::string configPath = "configs/default.json";
        bool checkGrad = false;
        bool dumpFlux = false;
        std::string boltInitFile;
        std::string surfaceFile;
        for (int i = 1; i < argc; i++) {
            std::string arg = argv[i];
            if (arg == "--config" && i + 1 < argc) configPath = argv[++i];
            else if (arg == "--check-grad") checkGrad = true;
            else if (arg == "--dump-flux") dumpFlux = true;
            else if (arg == "--bolt-file" && i + 1 < argc) boltInitFile = argv[++i];
            else if (arg == "--surface-file" && i + 1 < argc) surfaceFile = argv[++i];
            else if (arg[0] != '-') configPath = arg; // positional arg fallback
        }
        auto cfg = bezier::loadConfig(configPath);
        if (!boltInitFile.empty()) cfg.boltInitFile = boltInitFile; // CLI override
        fmt::print("Receiver: {}x{}, radius={:.1f}m\n", cfg.pixelWidth, cfg.pixelHeight, cfg.receiverRadius);
        fmt::print("Heliostat: {:.2f}x{:.2f}m, grid={}\n", cfg.heliostatWidth, cfg.heliostatLength, cfg.gridSize);
        fmt::print("Optimizer: {} iters, lr={:.1e}\n", cfg.iterations, cfg.learningRate);

        auto sunTrain = bezier::loadSunDirections(cfg.sunTrainFile);
        auto sunValidation = bezier::loadSunDirections(cfg.sunValidationFile);
        auto allConfigs = bezier::loadHeliostatConfigs(cfg.ellipseFile);
        // Process all heliostat positions (filter removed — field-wide eval)
        std::vector<bezier::HeliostatConfig> heliostatConfigs = allConfigs;
        fmt::print("Loaded: {} train, {} val, {} configs (filtered from {})\n",
                   sunTrain.size(), sunValidation.size(), heliostatConfigs.size(), allConfigs.size());
        // sunShapeIntegral is computed automatically in loadConfig()

        bezier::VulkanApp app;

        // Gradient check mode
        if (checkGrad) {
            // Select 3 representative sun directions for multi-angle gradient verification
            // Choose directions with varying cosθ to test gravity interpolation
            std::vector<int> testIndices;
            if (sunTrain.size() >= 3) {
                testIndices = {0, (int)sunTrain.size()/3, (int)sunTrain.size()*2/3};
            } else {
                for (int i = 0; i < (int)sunTrain.size(); i++) testIndices.push_back(i);
            }
            // Ensure we also test the last direction (often has different cosθ)
            if (sunTrain.size() > 3 && testIndices.back() != (int)sunTrain.size()-1)
                testIndices.push_back((int)sunTrain.size()-1);

            std::array<float,3> hp = heliostatConfigs[0].position;
            float dlen = std::sqrt(hp[0]*hp[0] + hp[2]*hp[2]);
            std::array<float,3> ap;
            if (dlen > 1e-6f) {
                float dx = hp[0] / dlen, dz = hp[2] / dlen;
                ap = {dx * cfg.receiverRadius, cfg.receiverPosition[1], dz * cfg.receiverRadius};
            } else {
                ap = {0, cfg.receiverPosition[1], cfg.receiverRadius};
            }
            float pixelArea = (2.0f * 3.14159265f * cfg.receiverRadius * cfg.receiverHeight)
                            / (cfg.pixelWidth * cfg.pixelHeight);

            if (cfg.useBoltParameterization) {
                fmt::print("=== Bolt Gradient Verification Mode ===\n");
                bezier::BezierPipeline pipeline(app, cfg);
                pipeline.verifyBoltGradients(sunTrain[0], hp, ap, pixelArea);
            } else {
                fmt::print("=== Gradient Verification Mode ===\n");
                bezier::BezierPipeline pipeline(app, cfg);
                auto initCY = bezier::fitBezierFromEllipse(0.0002f, -0.0003f, 0.0f,
                    cfg.heliostatWidth, cfg.heliostatLength);
                pipeline.verifyGradients(initCY, sunTrain[0], hp, ap, pixelArea);
            }
            return 0;
        }

        // Flux dump mode: one forward render, save flux
        if (dumpFlux) {
            fmt::print("=== Flux Dump Mode ===\n");
            bezier::BezierPipeline pipeline(app, cfg);
            // Initialize pipeline (same pattern as verifyGradients and optimize)
            pipeline.createPipelines();
            pipeline.createBuffersAndTextures();
            if (cfg.useBoltParameterization) {
                pipeline.createBoltPipelines();
                pipeline.createBoltBuffers();
                std::vector<float> initBolts(cfg.numBolts, 0.0f);
                if (!boltInitFile.empty()) {
                    // Load bolt heights from file (txt: 35 vals, or 25 CPs for B-spline)
                    std::ifstream bf(boltInitFile);
                    if (!bf) { fmt::print(stderr, "Cannot open bolt file: {}\n", boltInitFile); return 1; }
                    std::vector<float> vals;
                    std::string line;
                    while (std::getline(bf, line)) {
                        if (line.empty() || line[0] == '#') continue;
                        // Parse "idx value" or just "value"
                        const char *s = line.c_str();
                        char *end;
                        float v1 = std::strtof(s, &end);
                        if (end != s) {
                            // Try second token
                            while (*end == ' ' || *end == '\t') end++;
                            if (*end && *end != '\n') {
                                float v2 = std::strtof(end, &end);
                                vals.push_back(v2);
                            } else {
                                vals.push_back(v1);
                            }
                        }
                    }
                    if ((int)vals.size() == cfg.numBolts) {
                        initBolts = vals;
                        fmt::print("  Loaded {} bolt heights from {}\n", vals.size(), boltInitFile);
                    } else if (cfg.useBSpline && (int)vals.size() == (int)(cfg.numCpX * cfg.numCpZ)) {
                        // CP heights -> bolt via T matrix
                        std::string tpath = cfg.influenceDataPath + "/bspline_T.bin";
                        std::ifstream tf(tpath, std::ios::binary);
                        if (!tf) { fmt::print(stderr, "Cannot open T matrix: {}\n", tpath); return 1; }
                        int nCp = vals.size();
                        int nBolts = cfg.numBolts;
                        std::vector<float> T(nBolts * nCp);
                        tf.read((char*)T.data(), nBolts * nCp * sizeof(float));
                        initBolts.assign(nBolts, 0.0f);
                        for (int i = 0; i < nBolts; i++)
                            for (int j = 0; j < nCp; j++)
                                initBolts[i] += T[i * nCp + j] * vals[j];
                        fmt::print("  Loaded {} CPs -> {} bolts via T matrix\n", nCp, nBolts);
                    } else {
                        fmt::print(stderr, "Bolt file has {} values, expected {} bolts or {} CPs\n",
                                   vals.size(), cfg.numBolts, cfg.numCpX*cfg.numCpZ);
                        return 1;
                    }
                }
                pipeline.uploadBoltData(initBolts);
            } else {
                auto initCY = bezier::fitBezierFromEllipse(
                    heliostatConfigs[0].A, heliostatConfigs[0].B, heliostatConfigs[0].C,
                    cfg.heliostatWidth, cfg.heliostatLength);
                pipeline.uploadHeliostatData(initCY);
            }
            for (const auto &hc : heliostatConfigs) {
            float dist = std::sqrt(hc.position[0]*hc.position[0] + hc.position[1]*hc.position[1] + hc.position[2]*hc.position[2]);
            fmt::print("Heliostat: {} (dist={:.1f}m)\n", hc.name, dist);

            float dlen = std::sqrt(hc.position[0]*hc.position[0] + hc.position[2]*hc.position[2]);
            std::array<float,3> ap;
            if (dlen > 1e-6f) {
                ap = {hc.position[0]/dlen * cfg.receiverRadius,
                      cfg.receiverPosition[1],
                      hc.position[2]/dlen * cfg.receiverRadius};
            } else {
                ap = {0, cfg.receiverPosition[1], cfg.receiverRadius};
            }

            if (!surfaceFile.empty()) {
                pipeline.uploadSurfaceFromFile(surfaceFile);
            }

            // Helper: compute cosTheta for gravity scaling (same as in pipeline.cpp)
            auto computeCosTheta = [](const std::array<float,3>& sd, const std::array<float,3>& hp,
                                       const std::array<float,3>& ap) -> float {
                float sdx=sd[0], sdy=sd[1], sdz=sd[2];
                float sl = std::sqrt(sdx*sdx+sdy*sdy+sdz*sdz);
                float rdx=ap[0]-hp[0], rdy=ap[1]-hp[1], rdz=ap[2]-hp[2];
                float rl = std::sqrt(rdx*rdx+rdy*rdy+rdz*rdz);
                float ny = sdy/sl + rdy/rl;
                float nx = sdx/sl + rdx/rl, nz = sdz/sl + rdz/rl;
                float nl = std::sqrt(nx*nx+ny*ny+nz*nz);
                return std::abs(ny) / nl;
            };

            float pixelArea = (2.0f * 3.14159265f * cfg.receiverRadius * cfg.receiverHeight)
                            / (cfg.pixelWidth * cfg.pixelHeight);
            float evalTotalS95 = 0.0f;
            int evalValidSuns = 0;

            for (size_t si = 0; si < sunTrain.size(); si++) {
                const auto &sd = sunTrain[si];
                pipeline.updateUniforms(sd, hc.position, ap);
                if (cfg.useBoltParameterization && surfaceFile.empty()) {
                    float cosTheta = computeCosTheta(sd, hc.position, ap);
                    pipeline.boltForwardSurface(cosTheta);
                }
                pipeline.forwardRender(!cfg.useBoltParameterization && surfaceFile.empty());
                auto flux = pipeline.readFlux();

                // Center flux: roll azimuth so spot is continuous and centered.
                // Uses circular center-of-mass to find the spot centroid.
                {
                    float sum_sin = 0.0f, sum_cos = 0.0f;
                    for (int x = 0; x < cfg.pixelWidth; x++) {
                        float col_sum = 0.0f;
                        for (int y = 0; y < cfg.pixelHeight; y++)
                            col_sum += flux[y * cfg.pixelWidth + x];
                        float theta = 2.0f * 3.14159265f * x / cfg.pixelWidth;
                        sum_sin += col_sum * std::sin(theta);
                        sum_cos += col_sum * std::cos(theta);
                    }
                    float mean_theta = std::atan2(sum_sin, sum_cos);
                    if (mean_theta < 0.0f) mean_theta += 2.0f * 3.14159265f;
                    int center_pixel = int(mean_theta / (2.0f * 3.14159265f) * cfg.pixelWidth) % cfg.pixelWidth;
                    int shift = cfg.pixelWidth / 2 - center_pixel;
                    std::vector<float> rolled(flux.size());
                    for (int y = 0; y < cfg.pixelHeight; y++) {
                        for (int x = 0; x < cfg.pixelWidth; x++) {
                            int src_x = (x - shift + cfg.pixelWidth) % cfg.pixelWidth;
                            rolled[y * cfg.pixelWidth + x] = flux[y * cfg.pixelWidth + src_x];
                        }
                    }
                    flux = std::move(rolled);
                }

                // Compute S95 for evaluation (inline, same algorithm as pipeline.cpp)
                {
                    float total = 0.0f, maxVal = 0.0f;
                    for (float f : flux) { total += f; if (f > maxVal) maxVal = f; }
                    if (total > 1e-6f) {
                        float low = 0.0f, high = maxVal, level = 0.0f;
                        for (int binIter = 0; binIter < 20; binIter++) {
                            float mid = (low + high) * 0.5f;
                            float sumAbove = 0.0f;
                            for (float f : flux) if (f > mid) sumAbove += f;
                            if (sumAbove / total > 0.95f) low = mid;
                            else { high = mid; level = mid; }
                        }
                        if (level > 0) {
                            int count = 0;
                            for (float f : flux) if (f >= level) count++;
                            evalTotalS95 += count * pixelArea;
                            evalValidSuns++;
                        }
                    }
                }

                // Save as NPY
                std::string fluxPath = cfg.outputDir + "/" + hc.name + "_" +
                    std::to_string((int)dist) + "m_sun" + std::to_string(si) + "_flux.npy";
                // NPY format (matching saveNpy pattern)
                std::ofstream f(fluxPath, std::ios::binary);
                f.write("\x93NUMPY", 6);
                f.put(1); f.put(0);  // version 1.0
                std::string header = "{'descr': '<f4', 'fortran_order': False, "
                    "'shape': (" + std::to_string(cfg.pixelHeight) + ", " +
                    std::to_string(cfg.pixelWidth) + ")}";
                int pad = 16 - ((10 + (int)header.size() + 1) % 16);
                for (int i = 0; i < pad; i++) header += ' ';
                header += '\n';
                uint16_t headerLen = (uint16_t)header.size();
                f.write((const char *)&headerLen, 2);
                f.write(header.data(), header.size());
                f.write((const char *)flux.data(), flux.size() * sizeof(float));
                f.close();
                auto diag = pipeline.getDiagCounts();
                float totalRays = (float)(cfg.pixelWidth * cfg.pixelHeight * cfg.gridSize * cfg.gridSize);
                fmt::print("  Saved flux: {} ({} pixels, sum={:.1f})\n",
                    fluxPath, flux.size(),
                    std::accumulate(flux.begin(), flux.end(), 0.0f));
                fmt::print("  ┌─ Branch Boundary Diagnostics ({:.0f} total rays) ─────────────┐\n", totalRays);
                fmt::print("  │ [0] TIR fallback:       {:>8d} ({:.4f}%)\n", diag[0], 100.0f*diag[0]/totalRays);
                fmt::print("  │ [1] Near back-face:     {:>8d} ({:.4f}%)  dot(nor1,-dir)<0.01\n", diag[1], 100.0f*diag[1]/totalRays);
                fmt::print("  │ [2] Near sun outer cut: {:>8d} ({:.4f}%)  |sunθ-0.0436|<0.003\n", diag[2], 100.0f*diag[2]/totalRays);
                fmt::print("  │ [3] Near sun inner cut: {:>8d} ({:.4f}%)  |sunθ-0.00465|<0.0013\n", diag[3], 100.0f*diag[3]/totalRays);
                fmt::print("  │ [4] Near receiver edge: {:>8d} ({:.4f}%)  -0.01<dc<0\n", diag[4], 100.0f*diag[4]/totalRays);
                fmt::print("  │ [5] Rays processed:     {:>8d}\n", diag[5]);
                fmt::print("  └{:─^64}┘\n", "");
            }
                // Print evaluation summary for this heliostat
                if (evalValidSuns > 0) {
                    float avgS95 = evalTotalS95 / evalValidSuns;
                    fmt::print("  EVAL: avg S95 = {:.4f} m² over {} / {} valid sun directions\n",
                               avgS95, evalValidSuns, sunTrain.size());
                }
            }  // end heliostat loop
            return 0;
        }

        // WoS influence computation mode removed (route rejected at G1 gate, 2026-08)

        bezier::BezierPipeline pipeline(app, cfg);
        fs::create_directories(cfg.outputDir);

        std::string summaryPath = cfg.outputDir + "/optimization_summary.csv";
        std::ofstream summary(summaryPath);
        summary << "Position,Distance(m),Init_S95(m2),Best_S95(m2),Reduction(%)\n";
        summary.flush(); // Ensure header is written immediately

        auto t0 = std::chrono::high_resolution_clock::now();
        for (size_t i = 0; i < heliostatConfigs.size(); i++) {
            const auto &hc = heliostatConfigs[i];
            float dist = std::sqrt(hc.position[0]*hc.position[0] + hc.position[1]*hc.position[1] + hc.position[2]*hc.position[2]);
            fmt::print("\n[{}/{}] {}\n", i+1, heliostatConfigs.size(), hc.name);

            try {
                auto result = pipeline.optimize(hc, sunTrain, sunValidation);

                std::string prefix = fmt::format("{}_{:.0f}m", hc.name, dist);
                if (cfg.useBoltParameterization) {
                    auto &h = result.bestControlY;  // pipeline convention: +Y away from receiver

                    // ── Post-process: pipeline → bolt stroke heights ──
                    // The bolt influence model uses Σφ_b ≈ 1.0 (rigid translation).
                    // Adding a constant to all bolts is just a rigid-body shift.
                    // We preserve the optimizer's relative pattern directly:
                    //   h_stroke = h_pipe - min(h_pipe)   (zero-based, shape-preserving)
                    // No sign flip needed — the optimizer works in shader convention
                    // and the bolt stroke direction must match the shader's convention.
                    float min_pipe = *std::min_element(h.begin(), h.end());
                    std::vector<float> h_stroke(h.size());
                    for (size_t k = 0; k < h.size(); k++) h_stroke[k] = h[k] - min_pipe;

                    float max_stroke = *std::max_element(h_stroke.begin(), h_stroke.end());
                    fmt::print("  Bolt stroke: min={:.3f}mm  max={:.3f}mm  (zero-based)\n",
                               *std::min_element(h_stroke.begin(), h_stroke.end()) * 1000.0f,
                               max_stroke * 1000.0f);

                    // Save pipeline heights + stroke
                    std::string txtPath = cfg.outputDir + "/" + prefix + "_BEST_bolts.txt";
                    std::ofstream bf(txtPath);
                    bf << "# Bolt heights — PIPELINE convention (+Y away from receiver)\n";
                    bf << "# Best S95: " << result.bestS95 << " m^2\n";
                    bf << "# idx  h_pipe(m)  h_stroke(m)\n";
                    for (size_t k = 0; k < h.size(); k++)
                        bf << k << " " << h[k] << " " << h_stroke[k] << "\n";
                    bf.close();

                    // Save bolt stroke heights (ready for FEA input)
                    {
                        std::string strokePath = cfg.outputDir + "/" + prefix + "_STROKE_bolts.txt";
                        std::ofstream sf(strokePath);
                        sf << "# Bolt stroke heights (zero-based, ready for FEA)\n";
                        sf << "# max_stroke = " << max_stroke * 1000.0f << " mm\n";
                        for (size_t k = 0; k < h_stroke.size(); k++)
                            sf << h_stroke[k] << "\n";
                        sf.close();
                    }
                    // Also save as raw binary for Python
                    {
                        std::string binPath = cfg.outputDir + "/" + prefix + "_BEST_bolts.bin";
                        std::ofstream binf(binPath, std::ios::binary);
                        binf.write(reinterpret_cast<const char*>(h.data()),
                                   h.size() * sizeof(float));
                    }
                } else {
                    saveControlPoints(result.bestControlY, cfg.outputDir + "/" + prefix + "_BEST_BeCP",
                                      fmt::format("Best S95: {:.4f} m^2", result.bestS95));
                }

                std::ofstream csv(cfg.outputDir + "/" + prefix + "_history.csv");
                csv << "iteration,loss,s95_area\n";
                for (size_t k = 0; k < result.lossHistory.size(); k++)
                    csv << k << "," << result.lossHistory[k] << "," << result.s95History[k] << "\n";
                csv.close();

                float reduction = (result.initialS95 - result.bestS95) / std::max(result.initialS95, 1e-6f) * 100.0f;
                summary << fmt::format("{},{:.1f},{:.4f},{:.4f},{:.2f}\n", hc.name, dist, result.initialS95, result.bestS95, reduction);
                summary.flush();
            } catch (const std::exception &e) {
                fmt::print(stderr, "  ERROR optimizing {}: {}\n", hc.name, e.what());
                summary << fmt::format("{},{:.1f},ERROR,ERROR,ERROR\n", hc.name, dist);
                summary.flush();
            }
        }

        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::high_resolution_clock::now() - t0).count();
        summary.close();
        fmt::print("\n=== Done in {} sec. Results: {} ===\n", elapsed, cfg.outputDir);

    } catch (const std::exception &e) {
        fmt::print(stderr, "Error: {}\n", e.what());
        return 1;
    }
    return 0;
}
