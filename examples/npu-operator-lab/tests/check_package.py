#!/usr/bin/env python3
"""CPU-only package checks. These do not compile ASC or validate NPU execution."""
import ast
from pathlib import Path
import random
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def plan(n):
    tiles = (n + 255) // 256
    return tiles, min(8, tiles)


class PackageTests(unittest.TestCase):
    def test_python_consumer_parses(self):
        ast.parse((ROOT / "examples/python_client.py").read_text(encoding="utf-8"))

    def test_contract_constants(self):
        text = (ROOT / "src/host/tiling.h").read_text(encoding="utf-8")
        self.assertRegex(text, r"kTile\s*=\s*256;")
        self.assertRegex(text, r"kMaxBlocks\s*=\s*8;")
        self.assertRegex(text, r"kPartialStride\s*=\s*8;")
        self.assertRegex(text, r"kMaxMatrixDim\s*=\s*256;")

    def test_vector_coverage(self):
        for n in list(range(1, 10001)) + [2**24]:
            tiles, blocks = plan(n)
            previous = 0
            covered = 0
            for b in range(blocks):
                first, last = tiles * b // blocks, tiles * (b + 1) // blocks
                self.assertEqual(first, previous)
                self.assertLess(first, last)
                begin, end = first * 256, min(last * 256, n)
                self.assertLess(begin, end)
                covered += end - begin
                previous = last
            self.assertEqual(previous, tiles)
            self.assertEqual(covered, n)

    def test_two_stage_reduce_model(self):
        rng = random.Random(71)
        for n in [1, 7, 255, 256, 257, 1000, 2049, 16384]:
            x = [rng.randrange(-8, 9) for _ in range(n)]
            tiles, blocks = plan(n)
            scratch = [None] * (blocks * 8)
            for b in range(blocks):
                first, last = tiles * b // blocks, tiles * (b + 1) // blocks
                value = sum(x[first * 256:min(n, last * 256)])
                scratch[b * 8:(b + 1) * 8] = [value] + [0] * 7
            self.assertEqual(sum(scratch), sum(x))

    def test_matrix_index_and_accumulation_model(self):
        # Tests ND tile offsets and complete coverage, NOT Cube physical layouts.
        m, n, k = 32, 48, 32
        rng = random.Random(72)
        a = [[rng.randrange(-2, 3) for _ in range(k)] for _ in range(m)]
        b = [[rng.randrange(-2, 3) for _ in range(n)] for _ in range(k)]
        actual = [[None] * n for _ in range(m)]
        tiles = (m // 16) * (n // 16)
        for core in range(min(8, tiles)):
            for tile in range(core, tiles, min(8, tiles)):
                row, col = (tile // (n // 16)) * 16, (tile % (n // 16)) * 16
                for i in range(16):
                    for j in range(16):
                        self.assertIsNone(actual[row + i][col + j])
                        acc = 0
                        for k0 in range(0, k, 16):
                            acc += sum(a[row + i][k0 + t] * b[k0 + t][col + j]
                                       for t in range(16))
                        actual[row + i][col + j] = acc
        expected = [[sum(a[i][t] * b[t][j] for t in range(k))
                     for j in range(n)] for i in range(m)]
        self.assertEqual(actual, expected)

    def test_launchers_have_implementations(self):
        header = (ROOT / "src/kernel/launchers.h").read_text(encoding="utf-8")
        source = "\n".join(p.read_text(encoding="utf-8")
                           for p in (ROOT / "src/kernel").glob("*.asc"))
        for name in re.findall(r"void (nl_launch_\w+)\(", header):
            self.assertIn('extern "C" void ' + name + '(', source)

    def test_device_sources_have_no_stub_markers(self):
        for path in (ROOT / "src").rglob("*"):
            if path.suffix not in {".asc", ".cpp", ".h"}: continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("TODO", text, str(path))
            self.assertNotIn("IMPLEMENT_ME", text, str(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
