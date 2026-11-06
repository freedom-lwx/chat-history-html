#ifndef NPU_LAB_TILING_H
#define NPU_LAB_TILING_H
#include <cstdint>

namespace nl {
constexpr uint32_t kTile = 256;
constexpr uint32_t kMaxBlocks = 8;  // conservative teaching choice, not autotuning
constexpr uint32_t kMaxLength = 1u << 24;
constexpr uint32_t kMatrixTile = 16;
constexpr uint32_t kMaxMatrixDim = 256;
constexpr uint32_t kPartialStride = 8; // float32: 32-byte private slot per task

struct VectorPlan {
    uint32_t length;
    uint32_t tiles;
    uint32_t blocks;
};

inline VectorPlan MakeVectorPlan(uint32_t n) {
    const uint32_t tiles = n / kTile + (n % kTile != 0);
    return {n, tiles, tiles < kMaxBlocks ? tiles : kMaxBlocks};
}

// Identical tile-index partition is used in vector kernels.
inline uint32_t FirstTile(const VectorPlan& p, uint32_t block) {
    return p.tiles * block / p.blocks;
}
inline uint32_t LastTile(const VectorPlan& p, uint32_t block) {
    return p.tiles * (block + 1) / p.blocks;
}
inline bool ValidMatrix(uint32_t m, uint32_t n, uint32_t k) {
    return m && n && k && m <= kMaxMatrixDim && n <= kMaxMatrixDim &&
           k <= kMaxMatrixDim && m % kMatrixTile == 0 &&
           n % kMatrixTile == 0 && k % kMatrixTile == 0;
}
inline uint32_t MatrixBlocks(uint32_t m, uint32_t n) {
    const uint32_t tiles = (m / kMatrixTile) * (n / kMatrixTile);
    return tiles < kMaxBlocks ? tiles : kMaxBlocks;
}
}
#endif
