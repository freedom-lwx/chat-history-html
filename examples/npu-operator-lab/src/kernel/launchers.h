#ifndef NPU_LAB_LAUNCHERS_H
#define NPU_LAB_LAUNCHERS_H
#include <cstdint>

// Internal host ABI. Implementations live beside the device kernels in .asc.
// These enqueue work only. The public library wrapper handles synchronization.
extern "C" {
void nl_launch_add(uint32_t blocks, void* stream, const void* a,
                   const void* b, void* out, uint32_t n, uint32_t tiles);
void nl_launch_add_relu(uint32_t blocks, void* stream, const void* a,
                        const void* b, void* out, uint32_t n, uint32_t tiles);
void nl_launch_reduce_partials(uint32_t blocks, void* stream, const void* x,
                               void* partials, uint32_t n, uint32_t tiles);
void nl_launch_reduce_final(void* stream, const void* partials,
                            void* out, uint32_t blocks);
void nl_launch_matmul(uint32_t blocks, void* stream, const void* a,
                      const void* b, void* out, uint32_t m,
                      uint32_t n, uint32_t k);
}
#endif
