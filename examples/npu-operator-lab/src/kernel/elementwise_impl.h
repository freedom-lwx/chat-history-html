#ifndef NPU_LAB_ELEMENTWISE_IMPL_H
#define NPU_LAB_ELEMENTWISE_IMPL_H
#include "kernel_operator.h"
#include "../host/tiling.h"

// Shared implementation, instantiated by Add and Add+ReLU entrypoints.
// Depth 1 is deliberate: correctness-first; this is NOT a tuned double-buffer.
template<bool FuseRelu>
class ElementwiseKernel {
public:
    __aicore__ inline void Init(__gm__ float* a, __gm__ float* b,
                               __gm__ float* out, uint32_t n, uint32_t tiles) {
        n_ = n;
        const uint32_t block = AscendC::GetBlockIdx();
        const uint32_t blocks = AscendC::GetBlockNum();
        first_ = tiles * block / blocks;
        last_ = tiles * (block + 1) / blocks;
        aGm_.SetGlobalBuffer(a, n);
        bGm_.SetGlobalBuffer(b, n);
        outGm_.SetGlobalBuffer(out, n);
        pipe_.InitBuffer(aQueue_, 1, nl::kTile * sizeof(float));
        pipe_.InitBuffer(bQueue_, 1, nl::kTile * sizeof(float));
        pipe_.InitBuffer(outQueue_, 1, nl::kTile * sizeof(float));
    }

    __aicore__ inline void Process() {
        for (uint32_t tile = first_; tile < last_; ++tile) {
            const uint32_t offset = tile * nl::kTile;
            const uint32_t remaining = n_ - offset;
            const uint32_t valid = remaining < nl::kTile ? remaining : nl::kTile;
            CopyIn(offset, valid);
            Compute(valid);
            CopyOut(offset, valid);
        }
    }

private:
    __aicore__ inline void CopyIn(uint32_t offset, uint32_t valid) {
        auto a = aQueue_.AllocTensor<float>();
        auto b = bQueue_.AllocTensor<float>();
        // DataCopyExtParams.blockLen is BYTES, not element count.
        AscendC::DataCopyExtParams p{
            1, static_cast<uint32_t>(valid * sizeof(float)), 0, 0, 0};
        AscendC::DataCopyPadExtParams<float> pad{false, 0, 0, 0.0f};
        AscendC::DataCopyPad(a, aGm_[offset], p, pad);
        AscendC::DataCopyPad(b, bGm_[offset], p, pad);
        aQueue_.EnQue(a);
        bQueue_.EnQue(b);
    }

    __aicore__ inline void Compute(uint32_t valid) {
        auto a = aQueue_.DeQue<float>();
        auto b = bQueue_.DeQue<float>();
        auto out = outQueue_.AllocTensor<float>();
        AscendC::Add(out, a, b, valid);
        if constexpr (FuseRelu) {
            // ReLU consumes the Add result in the same UB allocation.
            AscendC::PipeBarrier<PIPE_V>();
            AscendC::Maxs(out, out, 0.0f, valid);
        }
        outQueue_.EnQue(out);
        aQueue_.FreeTensor(a);
        bQueue_.FreeTensor(b);
    }

    __aicore__ inline void CopyOut(uint32_t offset, uint32_t valid) {
        auto out = outQueue_.DeQue<float>();
        AscendC::DataCopyExtParams p{
            1, static_cast<uint32_t>(valid * sizeof(float)), 0, 0, 0};
        // Only valid bytes reach GM. UB padding is never an output allocation.
        AscendC::DataCopyPad(outGm_[offset], out, p);
        outQueue_.FreeTensor(out);
    }

    AscendC::TPipe pipe_;
    AscendC::TQue<AscendC::TPosition::VECIN, 1> aQueue_, bQueue_;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue_;
    AscendC::GlobalTensor<float> aGm_, bGm_, outGm_;
    uint32_t n_, first_, last_;
};
#endif
