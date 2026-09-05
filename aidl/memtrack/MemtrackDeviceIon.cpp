/*
 * SPDX-FileCopyrightText: 2025-2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

#include "MemtrackDeviceIon.h"

#include <android-base/logging.h>

#include <fstream>
#include <limits>
#include <sstream>

namespace aidl {
namespace android {
namespace hardware {
namespace memtrack {

bool MemtrackDeviceIon::getMemory(int pid, MemtrackRecord& record) {
    std::ifstream ifs(mPath);
    std::string line, client_name;
    unsigned int client_pid;
    int64_t client_size;

    if (!ifs.is_open()) {
        return false;
    }

    while (std::getline(ifs, line)) {
        std::istringstream iss(line);
        // Headers, blank lines and partial rows must not reuse the last PID/size.
        if (!(iss >> client_name >> client_pid >> client_size) || client_size < 0) {
            continue;
        }

        if (client_pid == static_cast<unsigned int>(pid)) {
            if (client_size > std::numeric_limits<int64_t>::max() - record.sizeInBytes) {
                return false;
            }
            LOG(DEBUG) << "Accounting memory allocated by PID " << pid << ": " << client_size;
            record.sizeInBytes += client_size;
        }
    }

    LOG(DEBUG) << "Total memory allocated by PID " << pid << ": " << record.sizeInBytes;

    record.flags = MemtrackRecord::FLAG_SMAPS_UNACCOUNTED | MemtrackRecord::FLAG_SHARED |
                   MemtrackRecord::FLAG_SYSTEM | MemtrackRecord::FLAG_NONSECURE;
    return true;
}

}  // namespace memtrack
}  // namespace hardware
}  // namespace android
}  // namespace aidl
