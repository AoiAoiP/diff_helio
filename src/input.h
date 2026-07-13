#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace bezier {

struct HeliostatConfig {
    std::string name;
    std::array<float, 3> position;
    float A, B, C; // Ellipse parameters: z = Ax^2 + By^2 + Cxy
};

// Load sun direction vectors from text file (3 columns: x, y, z)
std::vector<std::array<float, 3>> loadSunDirections(const std::string &path);

// Load heliostat configurations from ellipse.txt
std::vector<HeliostatConfig> loadHeliostatConfigs(const std::string &path);

// Fit Bezier control points (4x4) to an elliptical surface z = Ax^2 + By^2 + Cxy
std::vector<float> fitBezierFromEllipse(float A, float B, float C, float width, float length);

// Precompute Buie sun shape integral (CPU-side, using numerical integration)
float computeBuieIntegral(float csr);

} // namespace bezier
