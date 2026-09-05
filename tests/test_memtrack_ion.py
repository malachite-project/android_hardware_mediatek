#!/usr/bin/env python3
"""Native tests of the production ION accounting method; Android/logging are stubbed.

The method is copied verbatim from its source, not reimplemented. Temporary text
files model proc output. No proc nodes or physical device are accessed.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <unistd.h>
struct MemtrackRecord {
  int64_t sizeInBytes = 0;
  int flags = 0;
  enum { FLAG_SMAPS_UNACCOUNTED = 1, FLAG_SHARED = 2, FLAG_SYSTEM = 4, FLAG_NONSECURE = 8 };
};
struct MemtrackDeviceIon {
  std::string mPath;
  bool getMemory(int pid, MemtrackRecord& record);
};
#define LOG(level) std::clog
@METHOD@
static void check(const std::string& data, int pid, int64_t expected, bool success = true) {
  char path[] = "/tmp/ion-contract-XXXXXX";
  int fd = mkstemp(path);
  assert(fd >= 0);
  FILE* file = fdopen(fd, "w");
  assert(file != nullptr);
  assert(fwrite(data.data(), 1, data.size(), file) == data.size());
  assert(fclose(file) == 0);
  MemtrackDeviceIon device{path};
  MemtrackRecord record;
  assert(device.getMemory(pid, record) == success);
  if (success) {
    assert(record.sizeInBytes == expected);
    assert(record.flags == 15);
  }
  assert(unlink(path) == 0);
}
int main() {
  check("client 42 4096\n", 42, 4096);
  check("client 42 4096\n\n", 42, 4096);
  check("client 42 4096\nheader\n", 42, 4096);
  check("client 42 4096\npartial 42\n", 42, 4096);
  check("name pid size\nclient 42 4096\nsecond 42 2048\n", 42, 6144);
  check("other 7 8192\n", 42, 0);
  check("bad 42 -1\nclient 42 8\n", 42, 8);
  check("huge 42 999999999999999999999999\nclient 42 8\n", 42, 8);
  check("zero 42 0\n", 42, 0);
  check("", 42, 0);
  check("kernel 0 16\nother 42 32\n", 0, 16);
  check("one 42 9223372036854775807\ntwo 42 1\n", 42, 0, false);
  MemtrackDeviceIon missing{"/definitely-nonexistent-malachite-ion-contract"};
  MemtrackRecord record;
  assert(!missing.getMemory(42, record));
  puts("PASS: 13 ION accounting cases (native, ASan/UBSan)");
}
'''


def method(source):
    signature = 'bool MemtrackDeviceIon::getMemory(int pid, MemtrackRecord& record) {'
    start = source.index(signature)
    return source[start:source.index('\n}\n', start) + 2]


class IonAccountingTests(unittest.TestCase):
    def test_native_accounting(self):
        compiler = os.environ.get('CXX', 'clang++')
        self.assertIsNotNone(shutil.which(compiler), f'{compiler} is required')
        source_path = Path(os.environ.get('ION_SOURCE', ROOT / 'aidl/memtrack/MemtrackDeviceIon.cpp'))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'ion_test.cpp'
            binary = Path(directory) / 'ion_test'
            source.write_text(HARNESS.replace('@METHOD@', method(source_path.read_text())))
            subprocess.run([compiler, '-std=c++17', '-O1', '-g', '-Wall', '-Wextra',
                            '-Wno-sign-compare', '-Werror', '-fsanitize=address,undefined',
                            '-fno-omit-frame-pointer', str(source), '-o', str(binary)],
                           check=True, timeout=60)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
