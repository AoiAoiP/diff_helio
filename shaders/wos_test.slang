// Test: use GLSL-style layout qualifiers instead of [[vk::binding]]
layout(binding=0, set=0) buffer OutputBuf { float data[]; } outputBuf;

[shader("compute")]
[numthreads(64, 1, 1)]
void computeWoSInfluence(uint tid : SV_DispatchThreadID) {
    outputBuf.data[tid] = float(tid) * 0.001f;
}
