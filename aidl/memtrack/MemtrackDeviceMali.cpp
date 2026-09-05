/*
 * SPDX-FileCopyrightText: 2025-2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

#include "MemtrackDeviceMali.h"

#include <android-base/logging.h>

#include <unistd.h>
#include <fstream>
#include <limits>
#include <sstream>

namespace aidl {
namespace android {
namespace hardware {
namespace memtrack {

bool MemtrackDeviceMali::getMemory(int pid, MemtrackRecord& record) {
    std::ifstream ifs(mPath);
    std::string line, client_name;
    unsigned int client_pid;
    int64_t client_size;
    const int64_t page_size = getpagesize();

    if (!ifs.is_open()) {
        return false;
    }

    while (std::getline(ifs, line)) {
        std::istringstream iss(line);

        if ((iss >> client_name >> client_size >> client_pid) && client_size >= 0) {
            if (client_pid == pid || pid == 0) {
                if (client_size > std::numeric_limits<int64_t>::max() / page_size) {
                    LOG(ERROR) << "Mali allocation size exceeds the memtrack byte range";
                    return false;
                }
                const int64_t bytes = client_size * page_size;
                if (record.sizeInBytes > std::numeric_limits<int64_t>::max() - bytes) {
                    LOG(ERROR) << "Mali allocation total exceeds the memtrack byte range";
                    return false;
                }
                LOG(DEBUG) << "Accounting memory allocated by PID " << pid << ": " << bytes;
                record.sizeInBytes += bytes;
            }
        }
    }

    LOG(DEBUG) << "Total memory allocated by PID " << pid << ": " << record.sizeInBytes;

    record.flags = MemtrackRecord::FLAG_SMAPS_UNACCOUNTED | MemtrackRecord::FLAG_PRIVATE |
                   MemtrackRecord::FLAG_NONSECURE;
    return true;
}

}  // namespace memtrack
}  // namespace hardware
}  // namespace android
}  // namespace aidl
