// backward.slang — bwd_diff through 2-layer glass optics, matching forward render
module backward;
import common;
import sunshape;

static const uint kBWGroupSize = 256u;
static const uint kBWControlCount = 16u;
static const uint totalSpp    = kGridSize * kGridSize;
static const uint totalPixels = 7850u;

// ---- Progressive AD tests ----
[Differentiable]
float testY(
    float c00,float c01,float c02,float c03, float c10,float c11,float c12,float c13,
    float c20,float c21,float c22,float c23, float c30,float c31,float c32,float c33,
    no_diff float u, no_diff float v)
{
    float bv0=no_diff(bernstein3(0u,v)),bv1=no_diff(bernstein3(1u,v)),bv2=no_diff(bernstein3(2u,v)),bv3=no_diff(bernstein3(3u,v));
    float bu0=no_diff(bernstein3(0u,u)),bu1=no_diff(bernstein3(1u,u)),bu2=no_diff(bernstein3(2u,u)),bu3=no_diff(bernstein3(3u,u));
    return bv0*(bu0*c00+bu1*c01+bu2*c02+bu3*c03)+bv1*(bu0*c10+bu1*c11+bu2*c12+bu3*c13)
          +bv2*(bu0*c20+bu1*c21+bu2*c22+bu3*c23)+bv3*(bu0*c30+bu1*c31+bu2*c32+bu3*c33);
}

[Differentiable]
float testNormal(
    float c00,float c01,float c02,float c03, float c10,float c11,float c12,float c13,
    float c20,float c21,float c22,float c23, float c30,float c31,float c32,float c33,
    no_diff float u, no_diff float v, no_diff float2 hs)
{
    float bv0=no_diff(bernstein3(0u,v)),bv1=no_diff(bernstein3(1u,v)),bv2=no_diff(bernstein3(2u,v)),bv3=no_diff(bernstein3(3u,v));
    float bu0=no_diff(bernstein3(0u,u)),bu1=no_diff(bernstein3(1u,u)),bu2=no_diff(bernstein3(2u,u)),bu3=no_diff(bernstein3(3u,u));
    float du0=no_diff(bernstein3_diff(0u,u)),du1=no_diff(bernstein3_diff(1u,u)),du2=no_diff(bernstein3_diff(2u,u)),du3=no_diff(bernstein3_diff(3u,u));
    float dv0=no_diff(bernstein3_diff(0u,v)),dv1=no_diff(bernstein3_diff(1u,v)),dv2=no_diff(bernstein3_diff(2u,v)),dv3=no_diff(bernstein3_diff(3u,v));
    float yu=du0*(bv0*c00+bv1*c10+bv2*c20+bv3*c30)+du1*(bv0*c01+bv1*c11+bv2*c21+bv3*c31)
            +du2*(bv0*c02+bv1*c12+bv2*c22+bv3*c32)+du3*(bv0*c03+bv1*c13+bv2*c23+bv3*c33);
    float yv=dv0*(bu0*c00+bu1*c01+bu2*c02+bu3*c03)+dv1*(bu0*c10+bu1*c11+bu2*c12+bu3*c13)
            +dv2*(bu0*c20+bu1*c21+bu2*c22+bu3*c23)+dv3*(bu0*c30+bu1*c31+bu2*c32+bu3*c33);
    return length(cross(float3(hs.x, yu, 0.0f), float3(0.0f, yv, hs.y)));
}

[Differentiable]
float testGlassOptics(
    float c00,float c01,float c02,float c03, float c10,float c11,float c12,float c13,
    float c20,float c21,float c22,float c23, float c30,float c31,float c32,float c33,
    no_diff float u, no_diff float v, no_diff float hx, no_diff float hz,
    no_diff OrthonormalBasis mb, no_diff float3 helioPos, no_diff float3 origin,
    no_diff float3 perturb1, no_diff float3 perturb2, no_diff float2 hs, no_diff float refIdx)
{
    float bv0=no_diff(bernstein3(0u,v)),bv1=no_diff(bernstein3(1u,v)),bv2=no_diff(bernstein3(2u,v)),bv3=no_diff(bernstein3(3u,v));
    float bu0=no_diff(bernstein3(0u,u)),bu1=no_diff(bernstein3(1u,u)),bu2=no_diff(bernstein3(2u,u)),bu3=no_diff(bernstein3(3u,u));
    float du0=no_diff(bernstein3_diff(0u,u)),du1=no_diff(bernstein3_diff(1u,u)),du2=no_diff(bernstein3_diff(2u,u)),du3=no_diff(bernstein3_diff(3u,u));
    float dv0=no_diff(bernstein3_diff(0u,v)),dv1=no_diff(bernstein3_diff(1u,v)),dv2=no_diff(bernstein3_diff(2u,v)),dv3=no_diff(bernstein3_diff(3u,v));
    float yu=du0*(bv0*c00+bv1*c10+bv2*c20+bv3*c30)+du1*(bv0*c01+bv1*c11+bv2*c21+bv3*c31)
            +du2*(bv0*c02+bv1*c12+bv2*c22+bv3*c32)+du3*(bv0*c03+bv1*c13+bv2*c23+bv3*c33);
    float yv=dv0*(bu0*c00+bu1*c01+bu2*c02+bu3*c03)+dv1*(bu0*c10+bu1*c11+bu2*c12+bu3*c13)
            +dv2*(bu0*c20+bu1*c21+bu2*c22+bu3*c23)+dv3*(bu0*c30+bu1*c31+bu2*c32+bu3*c33);
    float y=bv0*(bu0*c00+bu1*c01+bu2*c02+bu3*c03)+bv1*(bu0*c10+bu1*c11+bu2*c12+bu3*c13)
          +bv2*(bu0*c20+bu1*c21+bu2*c22+bu3*c23)+bv3*(bu0*c30+bu1*c31+bu2*c32+bu3*c33);
    float3 nrmL = -normalize(cross(float3(hs.x, yu, 0.0f), float3(0.0f, yv, hs.y)));
    float3 tn = basisToWorldDirection(mb, nrmL);
    float3 pos = basisToWorldPosition(mb, float3(hx, y, hz), helioPos);
    float3 dir = normalize(pos - origin);
    OrthonormalBasis sb = computeBasis(tn);
    float3 nor1 = basisToWorldDirection(sb, perturb1);
    float3 nor2 = basisToWorldDirection(sb, perturb2);
    float etaE = 1.0f/refIdx, etaX = refIdx;
    float ndi = dot(nor1, dir);
    float kEnter = 1.0f - etaE*etaE*(1.0f-ndi*ndi);
    float3 d2 = (kEnter > 0.0f) ? normalize(etaE*dir - (etaE*ndi + sqrt(kEnter))*nor1) : float3(0.0f,0.0f,0.0f);
    float3 outRG = float3(0.0f,0.0f,0.0f);
    if (length(d2) > kEpsilon) {
        float3 d3 = normalize(reflect(d2, nor2));
        float ndx = dot(d3, -nor1);
        float kExit = 1.0f - etaX*etaX*(1.0f-ndx*ndx);
        if (kExit > 0.0f) outRG = normalize(etaX*d3 - (etaX*ndx + sqrt(kExit))*(-nor1));
    }
    // TIR fallback removed — TIR samples correctly produce zero gradient
    return dot(outRG, float3(0.0f,1.0f,0.0f));
}

// ---- computePixelEnergy: 2-layer glass, matching forward ----
[Differentiable]
float computePixelEnergy(
    float c00,float c01,float c02,float c03, float c10,float c11,float c12,float c13,
    float c20,float c21,float c22,float c23, float c30,float c31,float c32,float c33,
    no_diff float u, no_diff float v, no_diff float3 origin, no_diff float3 normP,
    no_diff float3 perturb1, no_diff float3 perturb2, no_diff float hx, no_diff float hz,
    no_diff float3 macroN, no_diff OrthonormalBasis macroBasis,
    no_diff float3 sunDir, no_diff float dni, no_diff float refIdx,
    no_diff float4 shapeParams, no_diff float shapeInt, no_diff float shapeType,
    no_diff float refArea)
{
    float bv0=no_diff(bernstein3(0u,v)),bv1=no_diff(bernstein3(1u,v)),bv2=no_diff(bernstein3(2u,v)),bv3=no_diff(bernstein3(3u,v));
    float bu0=no_diff(bernstein3(0u,u)),bu1=no_diff(bernstein3(1u,u)),bu2=no_diff(bernstein3(2u,u)),bu3=no_diff(bernstein3(3u,u));
    float y = bv0*(bu0*c00+bu1*c01+bu2*c02+bu3*c03)+bv1*(bu0*c10+bu1*c11+bu2*c12+bu3*c13)
            +bv2*(bu0*c20+bu1*c21+bu2*c22+bu3*c23)+bv3*(bu0*c30+bu1*c31+bu2*c32+bu3*c33);
    float dv0=no_diff(bernstein3_diff(0u,v)),dv1=no_diff(bernstein3_diff(1u,v)),dv2=no_diff(bernstein3_diff(2u,v)),dv3=no_diff(bernstein3_diff(3u,v));
    float du0=no_diff(bernstein3_diff(0u,u)),du1=no_diff(bernstein3_diff(1u,u)),du2=no_diff(bernstein3_diff(2u,u)),du3=no_diff(bernstein3_diff(3u,u));
    float yu=du0*(bv0*c00+bv1*c10+bv2*c20+bv3*c30)+du1*(bv0*c01+bv1*c11+bv2*c21+bv3*c31)
            +du2*(bv0*c02+bv1*c12+bv2*c22+bv3*c32)+du3*(bv0*c03+bv1*c13+bv2*c23+bv3*c33);
    float yv=dv0*(bu0*c00+bu1*c01+bu2*c02+bu3*c03)+dv1*(bu0*c10+bu1*c11+bu2*c12+bu3*c13)
            +dv2*(bu0*c20+bu1*c21+bu2*c22+bu3*c23)+dv3*(bu0*c30+bu1*c31+bu2*c32+bu3*c33);

    float3 posLocal = float3(hx, y, hz);
    float3 tu = float3(getHeliostatSize().x, yu, 0.0f);
    float3 tv = float3(0.0f, yv, getHeliostatSize().y);
    float3 nrmLocal = -normalize(cross(tu, tv));

    float3 he = basisToWorldPosition(macroBasis, posLocal, heliostatPosition);
    float3 tn = basisToWorldDirection(macroBasis, nrmLocal);

    float3 ray = he - origin; float rl = max(length(ray), kEpsilon); float3 dir = ray / rl;
    if (dot(normP, float3(dir.x, 0.0f, dir.z)) <= 0.0f) return 0.0f;

    // 2-layer glass optics — EXACT match with forward render
    OrthonormalBasis surfBasis = computeBasis(tn);
    float3 nor1 = basisToWorldDirection(surfBasis, perturb1);
    float3 nor2 = basisToWorldDirection(surfBasis, perturb2);
    float etaE = 1.0f / refIdx;
    float etaX = refIdx;
    float ndi = dot(nor1, dir);
    float kEnter = 1.0f - etaE * etaE * (1.0f - ndi * ndi);
    float3 d2 = (kEnter > 0.0f) ? normalize(etaE * dir - (etaE * ndi + sqrt(kEnter)) * nor1) : float3(0,0,0);
    float3 outRG = float3(0,0,0);
    if (length(d2) > kEpsilon) {
        float3 d3 = normalize(reflect(d2, nor2));
        float ndx = dot(d3, -nor1);
        float kExit = 1.0f - etaX * etaX * (1.0f - ndx * ndx);
        if (kExit > 0.0f) {
            outRG = normalize(etaX * d3 - (etaX * ndx + sqrt(kExit)) * (-nor1));
        }
    }
    if (length(outRG) <= kEpsilon) outRG = normalize(reflect(-dir, nor1));

    float rat = max(0.0f, refArea * dot(normP, dir) * dot(nor1, -dir)
                   / (rl * rl) * computeDistanceAttenuation(rl));
    if (rat <= 0.0f) return 0.0f;

    float ct = clamp(dot(outRG, normalize(sunDir)), -0.99999f, 0.99999f);
    float st = (abs(ct - 1.0f) < kEpsilon) ? 0.0f : acos(ct);
    float ssVal = computeSunshape(st, shapeParams, shapeType);
    return dni * rat * ssVal / max(2.0f * kPi * shapeInt * float(totalSpp), kEpsilon);
}

// ---- Main backward render kernel ----
[[vk::binding(12)]] [format("r32f")] RWTexture2D<float> fluxGradient;
// binding 9 removed — Phase 1: inline Box-Muller replaces gaussianPool
[[vk::binding(11)]] RWStructuredBuffer<float> gradPartial;
[[vk::binding(16)]] RWStructuredBuffer<float> controlYGradientOut;
[[vk::binding(15)]] RWStructuredBuffer<float> debugBuf;

groupshared float gs_grads[kBWControlCount][kBWGroupSize / 32u];

float readCY(uint i, uint j) { return controlY[i * kControlSize + j]; }

[shader("compute")]
[numthreads(kBWGroupSize, 1, 1)]
void renderBackward(uint3 gid : SV_GroupID, uint3 gtid : SV_GroupThreadID) {
    uint lid = gtid.x, pixIdx = gid.x, spStart = gid.y * kBWGroupSize, spIdx = spStart + lid;
    if (pixIdx >= totalPixels) return;

    float3 macroN = computeHeliostatNormal(getSunDirection(), heliostatPosition, aimPoint);
    OrthonormalBasis macroBasis = computeBasis(macroN);
    float3 sunDir = getSunDirection();
    float dni = getSunDni();
    float refIdx = getHeliostatRefractiveIndex();
    float4 shapeParams = getSunShapeParams();
    float shapeInt = getSunShapeIntegral();
    float shapeType = getSunShapeType();
    float refArea = getHeliostatReflectiveArea();

    uint2 pc = uint2(pixIdx % getReceiverDims().x, pixIdx / getReceiverDims().x);
    float dL = fluxGradient[pc];

    // DIAG: progressive AD test
    if (pixIdx == 0u && gid.y == 0u && lid == 0u) {
        float2 hs = getHeliostatSize();
        float hx0=-hs.x*0.5f, hz0=-hs.y*0.5f;
        float3 rsPd, rsNd; getReceiverSampleData(uint2(0,0), rsPd, rsNd);
        float c00=readCY(0,0),c01=readCY(0,1),c02=readCY(0,2),c03=readCY(0,3);
        float c10=readCY(1,0),c11=readCY(1,1),c12=readCY(1,2),c13=readCY(1,3);
        float c20=readCY(2,0),c21=readCY(2,1),c22=readCY(2,2),c23=readCY(2,3);
        float c30=readCY(3,0),c31=readCY(3,1),c32=readCY(3,2),c33=readCY(3,3);

        // Step 1: Y
        var t00=diffPair(c00,0.0f); var t01=diffPair(c01,0.0f); var t02=diffPair(c02,0.0f); var t03=diffPair(c03,0.0f);
        var t10=diffPair(c10,0.0f); var t11=diffPair(c11,0.0f); var t12=diffPair(c12,0.0f); var t13=diffPair(c13,0.0f);
        var t20=diffPair(c20,0.0f); var t21=diffPair(c21,0.0f); var t22=diffPair(c22,0.0f); var t23=diffPair(c23,0.0f);
        var t30=diffPair(c30,0.0f); var t31=diffPair(c31,0.0f); var t32=diffPair(c32,0.0f); var t33=diffPair(c33,0.0f);
        bwd_diff(testY)(t00,t01,t02,t03,t10,t11,t12,t13,t20,t21,t22,t23,t30,t31,t32,t33, 0.5f, 0.5f, 1.0f);
        debugBuf[0] = t00.d;

        // Step 2: Normal
        var n00=diffPair(c00,0.0f); var n01=diffPair(c01,0.0f); var n02=diffPair(c02,0.0f); var n03=diffPair(c03,0.0f);
        var n10=diffPair(c10,0.0f); var n11=diffPair(c11,0.0f); var n12=diffPair(c12,0.0f); var n13=diffPair(c13,0.0f);
        var n20=diffPair(c20,0.0f); var n21=diffPair(c21,0.0f); var n22=diffPair(c22,0.0f); var n23=diffPair(c23,0.0f);
        var n30=diffPair(c30,0.0f); var n31=diffPair(c31,0.0f); var n32=diffPair(c32,0.0f); var n33=diffPair(c33,0.0f);
        bwd_diff(testNormal)(n00,n01,n02,n03,n10,n11,n12,n13,n20,n21,n22,n23,n30,n31,n32,n33, 0.5f, 0.5f, hs, 1.0f);
        debugBuf[1] = n00.d;

        // Step 3: Glass optics (Phase 1: inline Box-Muller)
        float dg0, dg1, dg2, dg3;
        generateGaussianSamples(0u, 0u, 0u, dg0, dg1, dg2, dg3);
        float sigma = getHeliostatSlopeError();
        float3 pp1 = normalize(float3(dg0 * sigma, 1.0f, dg1 * sigma));
        float3 pp2 = normalize(float3(dg2 * sigma, 1.0f, dg3 * sigma));
        var g00=diffPair(c00,0.0f); var g01=diffPair(c01,0.0f); var g02=diffPair(c02,0.0f); var g03=diffPair(c03,0.0f);
        var g10=diffPair(c10,0.0f); var g11=diffPair(c11,0.0f); var g12=diffPair(c12,0.0f); var g13=diffPair(c13,0.0f);
        var g20=diffPair(c20,0.0f); var g21=diffPair(c21,0.0f); var g22=diffPair(c22,0.0f); var g23=diffPair(c23,0.0f);
        var g30=diffPair(c30,0.0f); var g31=diffPair(c31,0.0f); var g32=diffPair(c32,0.0f); var g33=diffPair(c33,0.0f);
        bwd_diff(testGlassOptics)(g00,g01,g02,g03,g10,g11,g12,g13,g20,g21,g22,g23,g30,g31,g32,g33,
            0.5f, 0.5f, hx0, hz0, macroBasis, heliostatPosition, rsPd, pp1, pp2, hs, refIdx, 1.0f);
        debugBuf[2] = g00.d;

        // Step 4: Full
        var f00=diffPair(c00,0.0f); var f01=diffPair(c01,0.0f); var f02=diffPair(c02,0.0f); var f03=diffPair(c03,0.0f);
        var f10=diffPair(c10,0.0f); var f11=diffPair(c11,0.0f); var f12=diffPair(c12,0.0f); var f13=diffPair(c13,0.0f);
        var f20=diffPair(c20,0.0f); var f21=diffPair(c21,0.0f); var f22=diffPair(c22,0.0f); var f23=diffPair(c23,0.0f);
        var f30=diffPair(c30,0.0f); var f31=diffPair(c31,0.0f); var f32=diffPair(c32,0.0f); var f33=diffPair(c33,0.0f);
        bwd_diff(computePixelEnergy)(f00,f01,f02,f03,f10,f11,f12,f13,f20,f21,f22,f23,f30,f31,f32,f33,
            0.5f, 0.5f, rsPd, rsNd, pp1, pp2, hx0, hz0,
            macroN, macroBasis, sunDir, dni, refIdx,
            shapeParams, shapeInt, shapeType, refArea, 1.0f);
        debugBuf[3] = f00.d;
    }

    float localGrads[kBWControlCount];
    for (uint ci = 0u; ci < kBWControlCount; ci++) localGrads[ci] = 0.0f;

    if (spIdx < totalSpp) { // always compute gradient (dL may be small but non-zero)
        float3 rsPos, rsNrm;
        getReceiverSampleData(pc, rsPos, rsNrm);
        uint xid = spIdx / kGridSize, zid = spIdx % kGridSize;
        float u = float(xid) / float(kGridSize - 1u);
        float v = float(zid) / float(kGridSize - 1u);
        float2 hs = getHeliostatSize();
        float hx = -hs.x * 0.5f + float(xid) * (hs.x / float(kGridSize - 1u));
        float hz = -hs.y * 0.5f + float(zid) * (hs.y / float(kGridSize - 1u));
        uint rayIndex = spIdx * totalPixels + pixIdx;
        // P2: skip dead rays
        if (0u == ((rayValidity[rayIndex >> 5u] >> (rayIndex & 31u)) & 1u)) { localGrads[0]=0; }
        else {
        float bg0, bg1, bg2, bg3;
        generateGaussianSamples(rayIndex, pixIdx, spIdx, bg0, bg1, bg2, bg3);
        float sigma = getHeliostatSlopeError();
        float3 pp1 = normalize(float3(bg0 * sigma, 1.0f, bg1 * sigma));
        float3 pp2 = normalize(float3(bg2 * sigma, 1.0f, bg3 * sigma));

        var d00=diffPair(readCY(0u,0u),0.0f); var d01=diffPair(readCY(0u,1u),0.0f);
        var d02=diffPair(readCY(0u,2u),0.0f); var d03=diffPair(readCY(0u,3u),0.0f);
        var d10=diffPair(readCY(1u,0u),0.0f); var d11=diffPair(readCY(1u,1u),0.0f);
        var d12=diffPair(readCY(1u,2u),0.0f); var d13=diffPair(readCY(1u,3u),0.0f);
        var d20=diffPair(readCY(2u,0u),0.0f); var d21=diffPair(readCY(2u,1u),0.0f);
        var d22=diffPair(readCY(2u,2u),0.0f); var d23=diffPair(readCY(2u,3u),0.0f);
        var d30=diffPair(readCY(3u,0u),0.0f); var d31=diffPair(readCY(3u,1u),0.0f);
        var d32=diffPair(readCY(3u,2u),0.0f); var d33=diffPair(readCY(3u,3u),0.0f);

        bwd_diff(computePixelEnergy)(d00,d01,d02,d03,d10,d11,d12,d13,d20,d21,d22,d23,d30,d31,d32,d33,
            u, v, rsPos, rsNrm, pp1, pp2, hx, hz, macroN, macroBasis,
            sunDir, dni, refIdx, shapeParams, shapeInt, shapeType, refArea, dL);

        localGrads[0]=d00.d; localGrads[1]=d01.d; localGrads[2]=d02.d; localGrads[3]=d03.d;
        localGrads[4]=d10.d; localGrads[5]=d11.d; localGrads[6]=d12.d; localGrads[7]=d13.d;
        localGrads[8]=d20.d; localGrads[9]=d21.d; localGrads[10]=d22.d; localGrads[11]=d23.d;
        localGrads[12]=d30.d; localGrads[13]=d31.d; localGrads[14]=d32.d; localGrads[15]=d33.d;
        } // end else (ray valid)
    } // end if (spIdx < totalSpp)

    uint wid = lid / 32u;
    for (uint ci = 0u; ci < kBWControlCount; ci++) {
        float waveSum = WaveActiveSum(localGrads[ci]);
        if (WaveIsFirstLane()) gs_grads[ci][wid] = waveSum;
    }
    GroupMemoryBarrierWithGroupSync();
    if (wid == 0u) {
        for (uint ci = 0u; ci < kBWControlCount; ci++) {
            float sum = 0.0f;
            if (lid < kBWGroupSize / 32u) sum = gs_grads[ci][lid];
            sum = WaveActiveSum(sum);
            if (lid == 0u) {
                uint groupIdx = pixIdx * ((totalSpp + kBWGroupSize - 1u) / kBWGroupSize) + gid.y;
                gradPartial[groupIdx * kBWControlCount + ci] = sum;
            }
        }
    }
}

[shader("compute")]
[numthreads(kBWGroupSize, 1, 1)]
void reduceBackwardGradients(uint3 gid : SV_GroupID, uint3 gtid : SV_GroupThreadID) {
    uint lid = gtid.x;
    uint totalGroups = totalPixels * ((totalSpp + kBWGroupSize - 1u) / kBWGroupSize);
    for (uint ci = lid; ci < kBWControlCount; ci += kBWGroupSize) {
        float sum = 0.0f;
        for (uint gi = 0u; gi < totalGroups; gi++)
            sum += gradPartial[gi * kBWControlCount + ci];
        controlYGradientOut[ci] += sum;
    }
}
