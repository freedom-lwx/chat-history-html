#include "npu_lab.h"
#include "acl/acl.h"
#include "tiling.h"
#include "../kernel/launchers.h"
#include <cstddef>
#include <cstdint>

namespace {
bool Overlaps(const void* a, size_t aBytes, const void* b, size_t bBytes) {
    const auto x = reinterpret_cast<uintptr_t>(a);
    const auto y = reinterpret_cast<uintptr_t>(b);
    // Difference form avoids overflow from computing end addresses.
    return x <= y ? y - x < aBytes : x - y < bBytes;
}
int ValidateBinary(const float* a, const float* b, float* out,
                   uint32_t n, void* stream) {
    if (n > nl::kMaxLength) return NL_UNSUPPORTED_SHAPE;
    if (!stream) return NL_BAD_ARGUMENT;
    if (n == 0) return NL_OK;
    if (!a || !b || !out) return NL_BAD_ARGUMENT;
    const size_t bytes = static_cast<size_t>(n) * sizeof(float);
    if (Overlaps(a, bytes, out, bytes) || Overlaps(b, bytes, out, bytes))
        return NL_BAD_ARGUMENT;
    return NL_OK;
}
}

extern "C" uint32_t nl_api_version(void) { return 1; }
extern "C" const char* nl_build_target(void) {
    return "teaching source; Linux; CANN>=9.0 ASC; dav-2201; hardware validation pending";
}

extern "C" int nl_add_f32(const float* a, const float* b, float* out,
                           uint32_t n, void* stream) {
    const int check = ValidateBinary(a, b, out, n, stream);
    if (check != NL_OK || n == 0) return check;
    const auto p = nl::MakeVectorPlan(n);
    nl_launch_add(p.blocks, stream, a, b, out, p.length, p.tiles);
    return aclrtSynchronizeStream(static_cast<aclrtStream>(stream));
}

extern "C" int nl_add_relu_f32(const float* a, const float* b, float* out,
                                uint32_t n, void* stream) {
    const int check = ValidateBinary(a, b, out, n, stream);
    if (check != NL_OK || n == 0) return check;
    const auto p = nl::MakeVectorPlan(n);
    nl_launch_add_relu(p.blocks, stream, a, b, out, p.length, p.tiles);
    return aclrtSynchronizeStream(static_cast<aclrtStream>(stream));
}

extern "C" int nl_reduce_sum_f32(const float* x, float* out,
                                  uint32_t n, void* stream) {
    if (n == 0 || n > nl::kMaxLength) return NL_UNSUPPORTED_SHAPE;
    if (!x || !out || !stream) return NL_BAD_ARGUMENT;
    if (Overlaps(x, static_cast<size_t>(n) * sizeof(float), out, sizeof(float)))
        return NL_BAD_ARGUMENT;
    const auto p = nl::MakeVectorPlan(n);
    void* workspace = nullptr;
    const size_t bytes = p.blocks * nl::kPartialStride * sizeof(float);
    aclError status = aclrtMalloc(&workspace, bytes, ACL_MEM_MALLOC_HUGE_FIRST);
    if (status != ACL_SUCCESS) return status;
    nl_launch_reduce_partials(p.blocks, stream, x, workspace, p.length, p.tiles);
    // Same stream orders the complete partial kernel before the final kernel.
    nl_launch_reduce_final(stream, workspace, out, p.blocks);
    status = aclrtSynchronizeStream(static_cast<aclrtStream>(stream));
    if (status != ACL_SUCCESS) {
        // Completion is not established. Avoid recycling potentially live scratch.
        // Treat a device execution fault as fatal; recover/reset the owned context.
        return status;
    }
    return aclrtFree(workspace);
}

extern "C" int nl_matmul_f16_f32(const uint16_t* a, const uint16_t* b, float* out,
                                  uint32_t m, uint32_t n, uint32_t k, void* stream) {
    if (!nl::ValidMatrix(m, n, k)) return NL_UNSUPPORTED_SHAPE;
    if (!a || !b || !out || !stream) return NL_BAD_ARGUMENT;
    const size_t aBytes = static_cast<size_t>(m) * k * sizeof(uint16_t);
    const size_t bBytes = static_cast<size_t>(k) * n * sizeof(uint16_t);
    const size_t cBytes = static_cast<size_t>(m) * n * sizeof(float);
    if (Overlaps(a, aBytes, out, cBytes) || Overlaps(b, bBytes, out, cBytes))
        return NL_BAD_ARGUMENT;
    nl_launch_matmul(nl::MatrixBlocks(m, n), stream, a, b, out, m, n, k);
    return aclrtSynchronizeStream(static_cast<aclrtStream>(stream));
}
