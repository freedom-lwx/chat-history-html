#!/usr/bin/env python3
"""Standalone ctypes consumer. Python stdlib only; requires built NPU library.

NL_LIB=/absolute/path/to/libnpu_lab.so python3 examples/python_client.py 0
No NumPy or PyTorch is required. This is NOT a PyTorch dispatcher/autograd op.
"""
import ctypes as C
import math
import os
from pathlib import Path
import struct
import sys


def main():
    device = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    acl_path = Path(os.environ["ASCEND_HOME_PATH"]) / "lib64/libascendcl.so"
    lib_path = Path(os.environ["NL_LIB"]).resolve(strict=True)
    acl = C.CDLL(str(acl_path), mode=C.RTLD_GLOBAL)
    lab = C.CDLL(str(lib_path))
    ptr, u32, i32, size = C.c_void_p, C.c_uint32, C.c_int32, C.c_size_t

    def bind(lib, name, args, result=i32):
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, result
        return fn

    init = bind(acl, "aclInit", [C.c_char_p])
    finalize = bind(acl, "aclFinalize", [])
    set_device = bind(acl, "aclrtSetDevice", [i32])
    reset_device = bind(acl, "aclrtResetDevice", [i32])
    create_stream = bind(acl, "aclrtCreateStream", [C.POINTER(ptr)])
    destroy_stream = bind(acl, "aclrtDestroyStream", [ptr])
    sync = bind(acl, "aclrtSynchronizeStream", [ptr])
    malloc = bind(acl, "aclrtMalloc", [C.POINTER(ptr), size, i32])
    free = bind(acl, "aclrtFree", [ptr])
    memcpy = bind(acl, "aclrtMemcpy", [ptr, size, ptr, size, i32])
    api = bind(lab, "nl_api_version", [], u32)
    target = bind(lab, "nl_build_target", [], C.c_char_p)
    add = bind(lab, "nl_add_f32", [ptr, ptr, ptr, u32, ptr])
    relu = bind(lab, "nl_add_relu_f32", [ptr, ptr, ptr, u32, ptr])
    reduce = bind(lab, "nl_reduce_sum_f32", [ptr, ptr, u32, ptr])
    matmul = bind(lab, "nl_matmul_f16_f32", [ptr, ptr, ptr, u32, u32, u32, ptr])
    # CANN ACL enum values used in this baseline.
    HUGE_FIRST, H2D, D2H = 0, 1, 2

    def check(code, where):
        if code != 0:
            raise RuntimeError(f"{where}: status={code}")

    def near(actual, expected, atol=1e-4, rtol=1e-5):
        if not (math.isfinite(actual) and math.isfinite(expected)):
            raise AssertionError("unexpected non-finite result")
        if abs(actual - expected) > atol + rtol * abs(expected):
            raise AssertionError(f"{actual} != {expected}")

    allocations = []
    stream = ptr()
    initialized = selected = False

    def alloc(nbytes):
        p = ptr()
        check(malloc(C.byref(p), nbytes, HUGE_FIRST), "malloc")
        allocations.append(p)
        return p

    def upload(host):
        nbytes = C.sizeof(host)
        p = alloc(nbytes)
        check(memcpy(p, nbytes, C.cast(host, ptr), nbytes, H2D), "H2D")
        return p

    def download(p, count):
        out = (C.c_float * count)()
        check(memcpy(C.cast(out, ptr), C.sizeof(out), p, C.sizeof(out), D2H), "D2H")
        return list(out)

    try:
        if api() != 1:
            raise RuntimeError("ABI version mismatch")
        print(target().decode())
        check(init(None), "aclInit"); initialized = True
        check(set_device(device), "set device"); selected = True
        check(create_stream(C.byref(stream)), "create stream")
        check(add(None, None, None, 0, stream), "empty Add")
        for n in (1, 7, 8, 255, 256, 257, 1000, 2049):
            a = [((i % 17) - 8) * 0.25 for i in range(n)]
            b = [((i % 11) - 5) * 0.5 for i in range(n)]
            da = upload((C.c_float * n)(*a))
            db = upload((C.c_float * n)(*b))
            dc = alloc(n * C.sizeof(C.c_float))
            check(add(da, db, dc, n, stream), "Add")
            for got, x, y in zip(download(dc, n), a, b): near(got, x + y)
            check(relu(da, db, dc, n, stream), "AddReLU")
            for got, x, y in zip(download(dc, n), a, b): near(got, max(x + y, 0))
            ds = alloc(C.sizeof(C.c_float))
            check(reduce(da, ds, n, stream), "ReduceSum")
            near(download(ds, 1)[0], math.fsum(a))
            if add(da, db, da, n, stream) != -1:
                raise AssertionError("alias should be rejected")
            print(f"vector cases passed: n={n}")

        m, n, k = 32, 48, 32
        a = [float((i * 7 + j * 2 + i * j) % 3 - 1)
             for i in range(m) for j in range(k)]
        b = [float((i * 5 + j * 7 + i * j + 1) % 3 - 1)
             for i in range(k) for j in range(n)]

        def half_array(values):
            # IEEE-754 half bit representation, not numeric uint16 conversion.
            bits = [struct.unpack("=H", struct.pack("=e", v))[0] for v in values]
            return (C.c_uint16 * len(bits))(*bits)

        da, db = upload(half_array(a)), upload(half_array(b))
        dc = alloc(m * n * C.sizeof(C.c_float))
        check(matmul(da, db, dc, m, n, k, stream), "MatMul")
        got = download(dc, m * n)
        for i in range(m):
            for j in range(n):
                expected = math.fsum(a[i * k + t] * b[t * n + j] for t in range(k))
                near(got[i * n + j], expected)
        if matmul(da, db, dc, 17, n, k, stream) != -2:
            raise AssertionError("unsupported matrix shape should be rejected")
        print("MatMul passed; all ctypes device checks completed.")
    finally:
        # Only recycle allocations after stream completion has been established.
        completed = not stream.value or sync(stream) == 0
        if completed:
            for p in reversed(allocations): free(p)
        if stream.value: destroy_stream(stream)
        # This standalone test owns the context. A host application must instead
        # respect its own runtime lifecycle; the library never resets its device.
        if selected: reset_device(device)
        if initialized: finalize()


if __name__ == "__main__":
    main()
