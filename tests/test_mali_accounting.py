"""Run production Mali accounting with native sanitizers and Android header stubs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ.get('MEDIATEK_ROOT', Path(__file__).resolve().parents[1]))


class MaliAccounting(unittest.TestCase):
    def test_native_accounting(self):
        compiler = shutil.which(os.environ.get('CXX', 'clang++'))
        self.assertIsNotNone(compiler, 'A C++ compiler is required; do not silently skip')
        with tempfile.TemporaryDirectory(prefix='mali-accounting-') as td:
            work = Path(td)
            shutil.copyfile(ROOT / 'aidl/memtrack/MemtrackDeviceMali.cpp', work / 'production.cpp')
            (work / 'android-base').mkdir()
            (work / 'android-base/logging.h').write_text(
                '#include <sstream>\nstruct NullLog { template<class T> NullLog& operator<<(const T&) { return *this; } };\n'
                '#define LOG(level) NullLog()\n')
            (work / 'MemtrackDeviceMali.h').write_text('''
#include <cstdint>
#include <string>
namespace aidl::android::hardware::memtrack {
struct MemtrackRecord {
    int64_t sizeInBytes = 0;
    int flags = 0;
    static constexpr int FLAG_SMAPS_UNACCOUNTED=1, FLAG_PRIVATE=2, FLAG_NONSECURE=4;
};
class MemtrackDeviceMali {
public:
    std::string mPath;
    bool getMemory(int pid, MemtrackRecord& record);
};
}
''')
            (work / 'main.cpp').write_text(r'''
#include "MemtrackDeviceMali.h"
#include <cassert>
#include <fstream>
#include <limits>
#include <unistd.h>
using namespace aidl::android::hardware::memtrack;
int main(int argc, char** argv) {
    assert(argc == 2);
    const int64_t page = getpagesize();
    const int64_t limit = std::numeric_limits<int64_t>::max();
    MemtrackDeviceMali device;
    device.mPath = argv[1];
    auto check = [&](const std::string& input, int pid, int64_t initial, bool ok, int64_t expected) {
        { std::ofstream file(device.mPath); file << input; }
        MemtrackRecord record; record.sizeInBytes = initial;
        assert(device.getMemory(pid, record) == ok);
        if (ok) { assert(record.sizeInBytes == expected); assert(record.flags == 7); }
    };
    check("client 2 42\n", 42, 0, true, 2*page);
    check("client 2 42\nother 3 42\n", 42, 0, true, 5*page);
    check("client 2 42\nother 3 43\n", 42, 0, true, 2*page);
    check("client 2 42\nother 3 43\n", 0, 0, true, 5*page);
    check("header\n\nclient 2\nclient 2 42\n", 42, 0, true, 2*page);
    check("client -1 42\nclient 2 42\n", 42, 0, true, 2*page);
    check("client 0 42\n", 42, 7, true, 7);
    check("", 42, 0, true, 0);
    check("client " + std::to_string(limit/page) + " 42\n", 42, 0, true, (limit/page)*page);
    check("client " + std::to_string(limit/page+1) + " 42\n", 42, 0, false, 0);
    check("client 1 42\n", 42, limit-page+1, false, 0);
    check("client " + std::to_string(limit/page) + " 42\nother 1 42\n", 42, 0, false, 0);
    check("client " + std::to_string(limit) + " 43\n", 42, 0, true, 0);
    device.mPath += ".missing";
    MemtrackRecord record;
    assert(!device.getMemory(42, record));
}
''')
            subprocess.run([compiler, '-std=c++17', '-fsanitize=address,undefined',
                            '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', '-g',
                            '-I', str(work), str(work / 'production.cpp'), str(work / 'main.cpp'),
                            '-o', str(work / 'test')], check=True, timeout=60)
            subprocess.run([str(work / 'test'), str(work / 'memory')], check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
