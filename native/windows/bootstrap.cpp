// Single-file distribution. Compiler and renderer DLLs are verified and
// extracted beside the inner controller before the Windows loader sees them.
#include "platform.hpp"
#include <bcrypt.h>
#include <libdeflate.h>
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>
#include "payload_identity.hpp"

namespace fs = std::filesystem;
using bako::windows::Handle;
using Digest = std::array<unsigned char, 32>;
static Digest hash(const void *data, size_t length) {
    Digest result{};
    if (length > ULONG_MAX || BCryptHash(BCRYPT_SHA256_ALG_HANDLE, nullptr, 0,
        static_cast<PUCHAR>(const_cast<void *>(data)), static_cast<ULONG>(length), result.data(), 32))
        throw std::runtime_error("Cannot verify bundled runtime");
    return result;
}
static std::string hex(const Digest &digest) {
    std::string result;
    for (auto byte : digest) { result += "0123456789abcdef"[byte >> 4]; result += "0123456789abcdef"[byte & 15]; }
    return result;
}
struct Payload {
    const unsigned char *cursor, *end;
    const unsigned char *take(size_t length) {
        if (length > static_cast<size_t>(end - cursor)) throw std::runtime_error("Truncated runtime payload");
        auto *result = cursor; cursor += length; return result;
    }
    uint32_t integer() { uint32_t value; std::memcpy(&value, take(4), 4); return value; }
};
static bool matches(const fs::path &path, size_t size, const Digest &expected) {
    std::error_code error;
    if (fs::file_size(path, error) != size || error) return false;
    std::ifstream file(path, std::ios::binary);
    std::vector<unsigned char> bytes(size);
    return file.read(reinterpret_cast<char *>(bytes.data()), size) && hash(bytes.data(), bytes.size()) == expected;
}
static fs::path extract() {
    auto resource = FindResourceW(nullptr, MAKEINTRESOURCEW(101), MAKEINTRESOURCEW(10));
    if (!resource) throw std::runtime_error("Bundled runtime resource is missing");
    auto size = SizeofResource(nullptr, resource);
    auto *data = static_cast<const unsigned char *>(LockResource(LoadResource(nullptr, resource)));
    if (!data || hex(hash(data, size)) != BAKO_PAYLOAD_SHA256) throw std::runtime_error("Bundled runtime checksum mismatch");
    auto directory = bako::windows::cache_root() / "runtime" / BAKO_PAYLOAD_SHA256;
    fs::create_directories(directory);
    Handle lock(CreateFileW((directory / "extract.lock").c_str(), GENERIC_READ | GENERIC_WRITE,
                           FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr));
    OVERLAPPED position{};
    if (lock.value == INVALID_HANDLE_VALUE || !LockFileEx(lock.value, LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, &position))
        throw std::runtime_error("Cannot lock runtime extraction cache");
    Payload payload{data, data + size};
    if (std::memcmp(payload.take(8), "BAKOWIN1", 8)) throw std::runtime_error("Unknown runtime payload version");
    auto count = payload.integer();
    if (count > 64) throw std::runtime_error("Invalid runtime file count");
    for (unsigned i = 0; i < count; ++i) {
        auto name_size = payload.integer(), file_size = payload.integer(), compressed_size = payload.integer();
        Digest expected; std::memcpy(expected.data(), payload.take(32), 32);
        auto *name_bytes = payload.take(name_size);
        std::string name(reinterpret_cast<const char *>(name_bytes), name_size);
        if (name.empty() || name.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.") != std::string::npos || name == "." || name == "..")
            throw std::runtime_error("Invalid bundled runtime filename");
        auto *compressed = payload.take(compressed_size);
        auto destination = directory / name;
        if (matches(destination, file_size, expected)) continue;
        std::vector<unsigned char> bytes(file_size);
        auto *decoder = libdeflate_alloc_decompressor();
        if (!decoder) throw std::bad_alloc();
        auto status = libdeflate_zlib_decompress(decoder, compressed, compressed_size, bytes.data(), bytes.size(), nullptr);
        libdeflate_free_decompressor(decoder);
        if (status != LIBDEFLATE_SUCCESS || hash(bytes.data(), bytes.size()) != expected)
            throw std::runtime_error("Cannot unpack bundled runtime: " + name);
        auto temporary = directory / (name + ".new");
        {
            std::ofstream file(temporary, std::ios::binary | std::ios::trunc);
            if (!file.write(reinterpret_cast<const char *>(bytes.data()), bytes.size()))
                throw std::runtime_error("Cannot write runtime cache");
        }
        if (!MoveFileExW(temporary.c_str(), destination.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
            throw std::runtime_error("Cannot install runtime cache file: " + name);
    }
    if (payload.cursor != payload.end) throw std::runtime_error("Unexpected runtime payload suffix");
    return directory / "bakoma-backend.exe";
}
int wmain(int argc, wchar_t **argv) {
    try {
        auto executable = extract();
        std::wstring command = bako::windows::quote(executable.native());
        for (int i = 1; i < argc; ++i) command += L' ' + bako::windows::quote(argv[i]);
        Handle job(CreateJobObjectW(nullptr, nullptr));
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if (!job.value || !SetInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits)))
            throw std::runtime_error("Cannot contain runtime processes");
        STARTUPINFOW startup{}; startup.cb = sizeof(startup);
        startup.dwFlags = STARTF_USESTDHANDLES;
        startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
        startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
        startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
        PROCESS_INFORMATION child{};
        if (!CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, TRUE,
                            CREATE_NO_WINDOW | CREATE_SUSPENDED, nullptr, nullptr, &startup, &child))
            throw std::runtime_error("Cannot start bundled runtime: Windows error " + std::to_string(GetLastError()));
        Handle process(child.hProcess), thread(child.hThread);
        if (!AssignProcessToJobObject(job.value, process.value)) {
            TerminateProcess(process.value, 1); throw std::runtime_error("Cannot contain bundled runtime");
        }
        ResumeThread(thread.value);
        WaitForSingleObject(process.value, INFINITE);
        DWORD code = 1; GetExitCodeProcess(process.value, &code);
        return static_cast<int>(code);
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
