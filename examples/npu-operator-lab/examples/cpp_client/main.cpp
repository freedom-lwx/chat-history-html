#include "npu_lab.h"
#include "acl/acl.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void Check(int status, const char* where) {
    if (status != 0)
        throw std::runtime_error(std::string(where) + ": status=" + std::to_string(status));
}
class Session {
public:
    aclrtStream stream = nullptr;
    explicit Session(int device) : device_(device) {
        Check(aclInit(nullptr), "aclInit");
        try {
            Check(aclrtSetDevice(device_), "aclrtSetDevice");
            selected_ = true;
            Check(aclrtCreateStream(&stream), "aclrtCreateStream");
        } catch (...) {
            if (selected_) aclrtResetDevice(device_);
            aclFinalize();
            throw;
        }
    }
    ~Session() {
        if (stream) { aclrtSynchronizeStream(stream); aclrtDestroyStream(stream); }
        if (selected_) aclrtResetDevice(device_);
        aclFinalize();
    }
    Session(const Session&) = delete;
    Session& operator=(const Session&) = delete;
private:
    int device_;
    bool selected_ = false;
};
class DeviceBuffer {
public:
    void* ptr = nullptr;
    const size_t bytes;
    explicit DeviceBuffer(size_t size) : bytes(size) {
        Check(aclrtMalloc(&ptr, bytes, ACL_MEM_MALLOC_HUGE_FIRST), "aclrtMalloc");
    }
    ~DeviceBuffer() { if (ptr) aclrtFree(ptr); }
    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;
    void Upload(const void* host) {
        Check(aclrtMemcpy(ptr, bytes, host, bytes, ACL_MEMCPY_HOST_TO_DEVICE), "H2D");
    }
    void Download(void* host) const {
        Check(aclrtMemcpy(host, bytes, ptr, bytes, ACL_MEMCPY_DEVICE_TO_HOST), "D2H");
    }
};
static void Near(float actual, double expected, double atol = 1e-5, double rtol = 1e-5) {
    // Reject NaN explicitly; abs(NaN)>limit would otherwise be false.
    if (!std::isfinite(actual) || !std::isfinite(expected) ||
        std::abs(actual - expected) > atol + rtol * std::abs(expected))
        throw std::runtime_error("numerical mismatch");
}
static void TestVector(uint32_t n, aclrtStream stream) {
    std::vector<float> a(n), b(n), out(n);
    for (uint32_t i = 0; i < n; ++i) {
        a[i] = (static_cast<int>(i % 17) - 8) * 0.25f;
        b[i] = (static_cast<int>(i % 11) - 5) * 0.5f;
    }
    DeviceBuffer da(n * sizeof(float)), db(n * sizeof(float)), dc(n * sizeof(float));
    da.Upload(a.data()); db.Upload(b.data());
    Check(nl_add_f32((float*)da.ptr, (float*)db.ptr, (float*)dc.ptr, n, stream), "Add");
    dc.Download(out.data());
    for (uint32_t i = 0; i < n; ++i) Near(out[i], a[i] + b[i]);
    Check(nl_add_relu_f32((float*)da.ptr, (float*)db.ptr, (float*)dc.ptr, n, stream), "AddReLU");
    dc.Download(out.data());
    for (uint32_t i = 0; i < n; ++i) Near(out[i], std::max(a[i] + b[i], 0.0f));
    DeviceBuffer scalar(sizeof(float));
    Check(nl_reduce_sum_f32((float*)da.ptr, (float*)scalar.ptr, n, stream), "ReduceSum");
    float sum = 0;
    scalar.Download(&sum);
    double reference = 0;
    for (float x : a) reference += x;
    Near(sum, reference, 1e-4, 1e-5);
    if (nl_add_f32((float*)da.ptr, (float*)db.ptr, (float*)da.ptr, n, stream) != NL_BAD_ARGUMENT)
        throw std::runtime_error("output alias was not rejected");
    std::cout << "Add / AddReLU / ReduceSum passed, n=" << n << '\n';
}
static void TestMatmul(uint32_t m, uint32_t n, uint32_t k, aclrtStream stream) {
    // Exact half encodings for {-1, 0, 1}; no SDK-specific host half type needed.
    const uint16_t bits[] = {0xbc00, 0x0000, 0x3c00};
    std::vector<uint16_t> a(m * k), b(k * n);
    std::vector<float> af(m * k), bf(k * n), c(m * n);
    for (uint32_t i = 0; i < m; ++i)
        for (uint32_t j = 0; j < k; ++j) {
            const uint32_t v = (i * 7 + j * 2 + i * j) % 3;
            a[i * k + j] = bits[v]; af[i * k + j] = static_cast<int>(v) - 1;
        }
    for (uint32_t i = 0; i < k; ++i)
        for (uint32_t j = 0; j < n; ++j) {
            const uint32_t v = (i * 5 + j * 7 + i * j + 1) % 3;
            b[i * n + j] = bits[v]; bf[i * n + j] = static_cast<int>(v) - 1;
        }
    DeviceBuffer da(a.size() * sizeof(uint16_t)), db(b.size() * sizeof(uint16_t));
    DeviceBuffer dc(c.size() * sizeof(float));
    da.Upload(a.data()); db.Upload(b.data());
    Check(nl_matmul_f16_f32((uint16_t*)da.ptr, (uint16_t*)db.ptr, (float*)dc.ptr,
                            m, n, k, stream), "MatMul");
    dc.Download(c.data());
    for (uint32_t i = 0; i < m; ++i)
        for (uint32_t j = 0; j < n; ++j) {
            double expected = 0;
            for (uint32_t t = 0; t < k; ++t) expected += af[i * k + t] * bf[t * n + j];
            Near(c[i * n + j], expected);
        }
    if (nl_matmul_f16_f32((uint16_t*)da.ptr, (uint16_t*)db.ptr, (float*)dc.ptr,
                          17, n, k, stream) != NL_UNSUPPORTED_SHAPE)
        throw std::runtime_error("unsupported shape was not rejected");
    std::cout << "MatMul passed, " << m << 'x' << k << " @ " << k << 'x' << n << '\n';
}
int main(int argc, char** argv) {
    try {
        const int device = argc > 1 ? std::stoi(argv[1]) : 0;
        Session session(device); // this standalone application owns ACL lifecycle
        std::cout << nl_build_target() << '\n';
        if (nl_api_version() != 1) throw std::runtime_error("ABI mismatch");
        Check(nl_add_f32(nullptr, nullptr, nullptr, 0, session.stream), "empty Add");
        for (uint32_t n : {1u, 7u, 8u, 255u, 256u, 257u, 1000u, 2049u, 16384u})
            TestVector(n, session.stream);
        TestMatmul(16, 16, 16, session.stream);
        TestMatmul(32, 48, 32, session.stream);
        TestMatmul(64, 64, 64, session.stream);
        std::cout << "All device tests passed.\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
