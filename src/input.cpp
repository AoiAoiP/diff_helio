#include "input.h"
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace bezier {

std::vector<std::array<float, 3>> loadSunDirections(const std::string &path) {
    std::vector<std::array<float, 3>> result;
    std::ifstream f(path);
    if (!f) throw std::runtime_error("Cannot open: " + path);

    std::string line;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream ss(line);
        float x, y, z;
        if (ss >> x >> y >> z) {
            // Normalize
            float len = std::sqrt(x * x + y * y + z * z);
            if (len > 0) {
                result.push_back({x / len, y / len, z / len});
            }
        }
    }
    return result;
}

std::vector<HeliostatConfig> loadHeliostatConfigs(const std::string &path) {
    std::vector<HeliostatConfig> result;
    std::ifstream f(path);
    if (!f) throw std::runtime_error("Cannot open: " + path);

    std::string line;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream ss(line);
        HeliostatConfig cfg;
        if (ss >> cfg.name >> cfg.position[0] >> cfg.position[1] >> cfg.position[2] >> cfg.A >> cfg.B >> cfg.C) {
            result.push_back(cfg);
        }
    }
    return result;
}

// Bernstein basis: B(i, 3, t) = C(3,i) * t^i * (1-t)^(3-i)
static float bernstein(int i, float t) {
    float comb[4] = {1, 3, 3, 1};
    return comb[i] * std::pow(t, i) * std::pow(1.0f - t, 3 - i);
}

std::vector<float> fitBezierFromEllipse(float A, float B, float C, float width, float length) {
    // Fit 4x4 Bezier control points to z = Ax^2 + By^2 + Cxy
    // x maps to u (width), z maps to v (length)
    constexpr int grid = 20;
    constexpr int totalSamples = grid * grid;
    constexpr int nControl = 16; // 4x4

    // Build A_mat [totalSamples x 16] and Y_vec [totalSamples]
    std::vector<double> A_mat(totalSamples * nControl, 0.0);
    std::vector<double> Y_vec(totalSamples, 0.0);

    for (int ui = 0; ui < grid; ui++) {
        float u = static_cast<float>(ui) / (grid - 1);
        float x = width * (u - 0.5f);
        for (int vi = 0; vi < grid; vi++) {
            float v = static_cast<float>(vi) / (grid - 1);
            float z = length * (v - 0.5f);
            int row = ui * grid + vi;
            Y_vec[row] = A * (x * x) + B * (z * z) + C * x * z;

            for (int i = 0; i < 4; i++) {
                for (int j = 0; j < 4; j++) {
                    int col = i * 4 + j;
                    A_mat[row * nControl + col] = bernstein(i, v) * bernstein(j, u);
                }
            }
        }
    }

    // Solve least squares: (A^T A)^(-1) A^T Y
    // For simplicity, use normal equations: A^T A x = A^T Y
    std::vector<double> AtA(nControl * nControl, 0.0);
    std::vector<double> AtY(nControl, 0.0);

    for (int row = 0; row < totalSamples; row++) {
        for (int i = 0; i < nControl; i++) {
            AtY[i] += A_mat[row * nControl + i] * Y_vec[row];
            for (int j = 0; j < nControl; j++) {
                AtA[i * nControl + j] += A_mat[row * nControl + i] * A_mat[row * nControl + j];
            }
        }
    }

    // Gaussian elimination with partial pivoting
    std::vector<int> pivot(nControl);
    for (int i = 0; i < nControl; i++) pivot[i] = i;

    for (int col = 0; col < nControl; col++) {
        // Find pivot
        int maxRow = col;
        double maxVal = std::abs(AtA[col * nControl + col]);
        for (int row = col + 1; row < nControl; row++) {
            double val = std::abs(AtA[row * nControl + col]);
            if (val > maxVal) {
                maxVal = val;
                maxRow = row;
            }
        }
        if (maxVal < 1e-12) continue;

        // Swap
        if (maxRow != col) {
            std::swap(pivot[col], pivot[maxRow]);
            for (int j = 0; j < nControl; j++)
                std::swap(AtA[col * nControl + j], AtA[maxRow * nControl + j]);
            std::swap(AtY[col], AtY[maxRow]);
        }

        // Eliminate
        double pivotVal = AtA[col * nControl + col];
        for (int row = col + 1; row < nControl; row++) {
            double factor = AtA[row * nControl + col] / pivotVal;
            for (int j = col; j < nControl; j++)
                AtA[row * nControl + j] -= factor * AtA[col * nControl + j];
            AtY[row] -= factor * AtY[col];
        }
    }

    // Back substitution
    std::vector<float> result(nControl, 0.0f);
    for (int i = nControl - 1; i >= 0; i--) {
        double sum = AtY[i];
        for (int j = i + 1; j < nControl; j++)
            sum -= AtA[i * nControl + j] * result[j];
        if (std::abs(AtA[i * nControl + i]) > 1e-12)
            result[i] = static_cast<float>(sum / AtA[i * nControl + i]);
    }

    return result;
}

float computeBuieIntegral(float csr) {
    // Numerical integration of Buie model L(theta)*theta dtheta from 0 to 0.0436 rad
    // Using Simpson's rule
    auto L = [csr](float theta) -> float {
        if (theta <= 0.00465f) {
            return std::cos(326.0f * theta) / std::cos(308.0f * theta);
        }
        float k = 0.9f * std::log(13.5f * csr) * std::pow(csr, -0.3f);
        float gamma = 2.2f * std::log(0.52f * csr) * std::pow(csr, 0.43f) - 0.1f;
        return std::exp(k) * std::pow(theta * 1000.0f, gamma);
    };

    constexpr int N = 2000;
    constexpr float thetaMin = 0.0f;
    constexpr float thetaMax = 0.0436f;
    float h = (thetaMax - thetaMin) / N;

    float sum = 0.0f;
    for (int i = 0; i <= N; i++) {
        float theta = thetaMin + i * h;
        float f = L(theta) * theta;
        if (i == 0 || i == N)
            sum += f;
        else if (i % 2 == 0)
            sum += 2.0f * f;
        else
            sum += 4.0f * f;
    }

    return sum * h / 3.0f;
}

} // namespace bezier
