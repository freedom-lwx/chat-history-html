#include "tiling.h"
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <stdexcept>

static void Require(bool condition) {
    if (!condition) throw std::runtime_error("tiling invariant failed");
}
int main() {
    for (uint32_t n = 1; n <= 10000; ++n) {
        const auto p = nl::MakeVectorPlan(n);
        Require(p.blocks > 0 && p.blocks <= nl::kMaxBlocks);
        uint32_t next = 0;
        for (uint32_t b = 0; b < p.blocks; ++b) {
            const uint32_t first = nl::FirstTile(p, b);
            const uint32_t last = nl::LastTile(p, b);
            Require(first == next && first < last);
            for (uint32_t t = first; t < last; ++t) {
                const uint32_t offset = t * nl::kTile;
                const uint32_t valid = std::min(nl::kTile, n - offset);
                Require(offset < n && valid > 0 && offset + valid <= n);
            }
            next = last;
        }
        Require(next == p.tiles);
    }
    const auto max = nl::MakeVectorPlan(nl::kMaxLength);
    Require(nl::LastTile(max, max.blocks - 1) == max.tiles);
    Require(nl::MakeVectorPlan(0).blocks == 0);
    Require(nl::ValidMatrix(32, 48, 64));
    Require(!nl::ValidMatrix(17, 48, 64));
    Require(!nl::ValidMatrix(16, 16, 0));
    std::cout << "Host tiling tests passed (no NPU execution).\n";
}
