"""Compile the production Mali backend with Android class/logging stubs.

No HAL service is started and only temporary fixture files are read.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ.get('MTK_HARDWARE_ROOT', Path(__file__).resolve().parents[1]))
PAGE = os.sysconf('SC_PAGE_SIZE')
MAX = (1 << 63) - 1


class MaliAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='mali-contract-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        (cls.work / 'android-base').mkdir()
        (cls.work / 'android-base/logging.h').write_text('#include <sstream>\n#define LOG(level) std::ostringstream()\n')
        (cls.work / 'MemtrackDeviceMali.h').write_text('''#pragma once
#include <cstdint>
#include <string>
namespace aidl::android::hardware::memtrack {
struct MemtrackRecord {
    enum { FLAG_SMAPS_UNACCOUNTED=1, FLAG_PRIVATE=2, FLAG_NONSECURE=4 };
    int64_t flags = 0, sizeInBytes = 0;
};
class MemtrackDeviceMali {
public:
    std::string mPath;
    bool getMemory(int pid, MemtrackRecord& record);
};
}
''')
        shutil.copyfile(ROOT / 'aidl/memtrack/MemtrackDeviceMali.cpp', cls.work / 'backend.cpp')
        (cls.work / 'main.cpp').write_text('''#include "MemtrackDeviceMali.h"
#include <iostream>
int main(int argc, char** argv) {
    if (argc != 4) return 2;
    using namespace aidl::android::hardware::memtrack;
    MemtrackDeviceMali device;
    device.mPath = argv[1];
    MemtrackRecord record;
    record.sizeInBytes = std::stoll(argv[3]);
    bool ok = device.getMemory(std::stoi(argv[2]), record);
    std::cout << ok << " " << record.sizeInBytes << " " << record.flags << "\\n";
}
''')
        compiler = os.environ.get('CXX', 'clang++')
        subprocess.run([compiler, '-std=c++17', '-fsanitize=address,undefined',
            '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', '-g',
            '-I', str(cls.work), str(cls.work / 'backend.cpp'), str(cls.work / 'main.cpp'),
            '-o', str(cls.work / 'test')], check=True, capture_output=True, text=True, timeout=60)

    def query(self, data, pid=42, initial=0):
        fixture = self.work / 'input'
        if data is None:
            fixture.unlink(missing_ok=True)
        else:
            fixture.write_text(data)
        result = subprocess.run([str(self.work / 'test'), str(fixture), str(pid), str(initial)],
            check=True, capture_output=True, text=True, timeout=10,
            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                     UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
        return tuple(map(int, result.stdout.split()))

    def test_valid_pages_and_flags(self):
        self.assertEqual(self.query('client 3 42\n'), (1, 3 * PAGE, 7))

    def test_headers_blank_partial_and_unrelated_rows(self):
        self.assertEqual(self.query('name pages pid\n\nclient 2\nclient 99 7\nclient 3 42\n'), (1, 3 * PAGE, 7))

    def test_zero_pid_aggregates_clients(self):
        self.assertEqual(self.query('client 2 7\nother 3 42\n', pid=0), (1, 5 * PAGE, 7))

    def test_negative_pages_are_not_subtracted(self):
        self.assertEqual(self.query('bad -1 42\ngood 3 42\n'), (1, 3 * PAGE, 7))

    def test_largest_representable_page_count(self):
        pages = MAX // PAGE
        self.assertEqual(self.query(f'client {pages} 42\n'), (1, pages * PAGE, 7))

    def test_page_to_byte_overflow_is_rejected(self):
        self.assertEqual(self.query(f'client {MAX // PAGE + 1} 42\n')[0], 0)

    def test_aggregate_overflow_is_rejected(self):
        self.assertEqual(self.query(f'client {MAX // PAGE} 42\nother 1 42\n')[0], 0)

    def test_initial_record_total_is_preserved(self):
        self.assertEqual(self.query('client 2 42\n', initial=123), (1, 2 * PAGE + 123, 7))

    def test_initial_record_overflow_is_rejected(self):
        self.assertEqual(self.query('client 1 42\n', initial=MAX)[0], 0)

    def test_unparseable_size_is_skipped(self):
        self.assertEqual(self.query(f'client {MAX + 1} 42\ngood 1 42\n'), (1, PAGE, 7))

    def test_unrelated_huge_allocation_is_not_accounted(self):
        self.assertEqual(self.query(f'client {MAX} 7\n'), (1, 0, 7))

    def test_empty_input(self):
        self.assertEqual(self.query(''), (1, 0, 7))

    def test_missing_file(self):
        self.assertEqual(self.query(None), (0, 0, 0))


if __name__ == '__main__':
    unittest.main()
