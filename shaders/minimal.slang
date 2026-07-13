// minimal.slang - Simplest possible shader to verify Vulkan pipeline

[format("r32f")]
[[vk::binding(0)]] RWTexture2D<float> outputTexture;

[shader("compute")]
[numthreads(16, 16, 1)]
void testClear(uint3 tid : SV_DispatchThreadID) {
    outputTexture[tid.xy] = 42.0f;
}
