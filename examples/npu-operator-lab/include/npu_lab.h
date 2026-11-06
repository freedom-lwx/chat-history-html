#ifndef NPU_LAB_H
#define NPU_LAB_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Linux / CANN >= 9.0 / dav-2201 teaching implementation.
 * All tensor pointers are DEVICE pointers in the caller's current context.
 * stream must be a valid, non-null aclrtStream from that context.
 * Functions are synchronous on that stream; do not call from graph capture.
 * The caller owns initialization, device selection, buffers, and the stream.
 * Inputs are contiguous. Output must not overlap either input.
 * Return: 0 success, negative NlStatus, positive ACL runtime error.
 */
enum NlStatus {
    NL_OK = 0,
    NL_BAD_ARGUMENT = -1,
    NL_UNSUPPORTED_SHAPE = -2
};

uint32_t nl_api_version(void);
const char* nl_build_target(void);

/* float32, equal lengths, no broadcasting. n==0 is a no-op.
 * Maximum n: 16,777,216. Finite inputs are the tested contract.
 */
int nl_add_f32(const float* a, const float* b, float* out,
               uint32_t n, void* stream);
int nl_add_relu_f32(const float* a, const float* b, float* out,
                    uint32_t n, void* stream);

/* float32 -> one float32 scalar. 1 <= n <= 16,777,216.
 * Two kernel launches on the same stream; internal scratch is owned by library.
 */
int nl_reduce_sum_f32(const float* x, float* out,
                      uint32_t n, void* stream);

/* Row-major A[m,k] @ B[k,n] -> C[m,n]. A/B: IEEE FP16 bit patterns,
 * NOT integer values. C and accumulation: float32. No transpose/bias/batch.
 * m,n,k must be positive multiples of 16, each <= 256.
 * The kernel uses 16x16 output tiles and explicit K accumulation.
 */
int nl_matmul_f16_f32(const uint16_t* a, const uint16_t* b, float* out,
                      uint32_t m, uint32_t n, uint32_t k, void* stream);
#ifdef __cplusplus
}
#endif
#endif
