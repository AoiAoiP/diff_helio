// wos_common.slang — WoS buffer bindings
module wos_common;

// Bolt positions [N_BOLTS * 2] in physical coords (x,z)
[[vk::binding(0)]] public uniform StructuredBuffer<float2> boltPositions;

// Output influence texture [N_BOLTS * TEX_W * TEX_H]
[[vk::binding(1)]] public RWStructuredBuffer<float> influencePhi;
