#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <io.h>
#include <process.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <algorithm>
#include <atomic>
#include <filesystem>
#include <string>
#include <vector>
#include <map>
#include <stdexcept>

#ifndef O_CLOEXEC
#define O_CLOEXEC 0
#endif
#ifndef X_OK
#define X_OK 0
#endif
inline int getpid() { return _getpid(); }
inline int setenv(const char *name, const char *value, int) { return _putenv_s(name, value); }
inline int open(const wchar_t *path, int flags, int mode = _S_IREAD | _S_IWRITE) {
    return _wopen(path, flags | _O_BINARY, mode);
}
inline int access(const wchar_t *path, int mode) { return _waccess(path, mode); }
inline int close(int fd) { return _close(fd); }
constexpr int LOCK_EX = 1, LOCK_NB = 2;
using pid_t = int;
#define WIFEXITED(status) true
#define WEXITSTATUS(status) (status)
inline int flock(int fd, int) {
    OVERLAPPED position{};
    return LockFileEx(reinterpret_cast<HANDLE>(_get_osfhandle(fd)),
                     LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &position) ? 0 : -1;
}

namespace bako::windows {
inline std::wstring wide(const std::string &text) {
    if (text.empty()) return {};
    int size = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), nullptr, 0);
    if (!size) throw std::runtime_error("Invalid UTF-8 Windows argument");
    std::wstring result(size, 0);
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), result.data(), size);
    return result;
}
inline std::wstring quote(const std::wstring &value) {
    std::wstring result = L"\"";
    size_t slashes = 0;
    for (wchar_t ch : value) {
        if (ch == L'\\') { ++slashes; continue; }
        result.append(ch == L'"' ? slashes * 2 + 1 : slashes, L'\\');
        result += ch; slashes = 0;
    }
    result.append(slashes * 2, L'\\');
    return result + L'"';
}
struct Handle {
    HANDLE value = INVALID_HANDLE_VALUE;
    Handle() = default;
    explicit Handle(HANDLE handle) : value(handle) {}
    ~Handle() { reset(); }
    Handle(const Handle &) = delete;
    Handle &operator=(const Handle &) = delete;
    Handle(Handle &&other) noexcept : value(other.value) { other.value = INVALID_HANDLE_VALUE; }
    Handle &operator=(Handle &&other) noexcept {
        reset(); value = other.value; other.value = INVALID_HANDLE_VALUE; return *this;
    }
    void reset() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); value = INVALID_HANDLE_VALUE; }
};
inline std::filesystem::path temporary_directory(const std::filesystem::path &parent, const std::string &prefix) {
    std::filesystem::create_directories(parent);
    for (unsigned i = 0; i < 10000; ++i) {
        auto path = parent / (prefix + std::to_string(GetCurrentProcessId()) + "-" +
                             std::to_string(GetTickCount64()) + "-" + std::to_string(i));
        if (std::filesystem::create_directory(path)) return path;
    }
    throw std::runtime_error("Cannot create native session directory");
}
inline std::filesystem::path cache_root() {
    wchar_t path[32768];
    auto size = GetEnvironmentVariableW(L"LOCALAPPDATA", path, 32768);
    if (!size || size >= 32768) throw std::runtime_error("LOCALAPPDATA is unavailable");
    return std::filesystem::path(path) / "texastra";
}
inline void pause(unsigned milliseconds) {
    // Sleep(1) can wait a full 15.6 ms Windows clock tick on an idle desktop.
    // A per-thread high-resolution timer avoids changing system timer policy.
    thread_local Handle timer(CreateWaitableTimerExW(nullptr, nullptr, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS));
    LARGE_INTEGER due; due.QuadPart = -static_cast<LONGLONG>(milliseconds) * 10000;
    if (timer.value && timer.value != INVALID_HANDLE_VALUE && SetWaitableTimer(timer.value, &due, 0, nullptr, nullptr, FALSE))
        WaitForSingleObject(timer.value, INFINITE);
    else Sleep(milliseconds);
}
inline void send_all(HANDLE handle, const std::string &data) {
    size_t offset = 0;
    while (offset < data.size()) {
        DWORD count;
        if (!WriteFile(handle, data.data() + offset, static_cast<DWORD>(std::min(data.size() - offset, size_t(1 << 20))), &count, nullptr) || !count)
            throw std::runtime_error("Native compiler control pipe closed");
        offset += count;
    }
}
inline std::string receive_exact(HANDLE handle, size_t size, const std::atomic<bool> *cancel = nullptr) {
    std::string result(size, '\0');
    size_t offset = 0;
    const auto deadline = GetTickCount64() + 90000;
    while (offset < size) {
        if (cancel && cancel->load()) throw std::runtime_error("Build cancelled");
        DWORD ready = 0;
        if (!PeekNamedPipe(handle, nullptr, 0, nullptr, &ready, nullptr))
            throw std::runtime_error("Native compiler event pipe closed");
        if (!ready) {
            if (GetTickCount64() >= deadline) throw std::runtime_error("Native compiler event pipe timed out");
            pause(1); continue;
        }
        DWORD count;
        if (!ReadFile(handle, result.data() + offset, static_cast<DWORD>(std::min(size - offset, size_t(ready))), &count, nullptr) || !count)
            throw std::runtime_error("Native compiler event pipe closed");
        offset += count;
    }
    return result;
}
class Child {
    Handle process, job;
  public:
    Handle commands, events;
    DWORD pid = 0;
    ~Child() { stop(); }
    void stop() {
        if (process.value != INVALID_HANDLE_VALUE) {
            if (WaitForSingleObject(process.value, 0) != WAIT_OBJECT_0) {
                TerminateJobObject(job.value, 1); WaitForSingleObject(process.value, 5000);
            }
            process.reset(); job.reset(); commands.reset(); events.reset(); pid = 0;
        }
    }
    bool running() const { return process.value != INVALID_HANDLE_VALUE && WaitForSingleObject(process.value, 0) == WAIT_TIMEOUT; }
    DWORD status() const { DWORD result = 1; if (process.value != INVALID_HANDLE_VALUE) GetExitCodeProcess(process.value, &result); return result; }
    void start(const std::filesystem::path &program, const std::vector<std::string> &args,
               const std::filesystem::path &directory, const std::filesystem::path &log,
               std::map<std::wstring, std::wstring> overrides = {}, bool transport = false) {
        stop();
        SECURITY_ATTRIBUTES security{sizeof(security), nullptr, TRUE};
        Handle output(CreateFileW(log.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                 &security, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr));
        Handle input(CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                &security, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
        if (output.value == INVALID_HANDLE_VALUE || input.value == INVALID_HANDLE_VALUE)
            throw std::runtime_error("Cannot open native compiler log or stdin");
        Handle command_read, event_write;
        std::vector<HANDLE> inherited{input.value, output.value};
        if (transport) {
            if (!CreatePipe(&command_read.value, &commands.value, &security, 65536) ||
                !CreatePipe(&events.value, &event_write.value, &security, 65536))
                throw std::runtime_error("Cannot create native compiler transport");
            SetHandleInformation(commands.value, HANDLE_FLAG_INHERIT, 0);
            SetHandleInformation(events.value, HANDLE_FLAG_INHERIT, 0);
            inherited.push_back(command_read.value); inherited.push_back(event_write.value);
            overrides[L"BAKO_COMMAND_HANDLE"] = std::to_wstring(reinterpret_cast<uintptr_t>(command_read.value));
            overrides[L"BAKO_EVENT_HANDLE"] = std::to_wstring(reinterpret_cast<uintptr_t>(event_write.value));
        }
        struct Less { bool operator()(const std::wstring &a, const std::wstring &b) const { return _wcsicmp(a.c_str(), b.c_str()) < 0; } };
        std::map<std::wstring, std::wstring, Less> env;
        wchar_t *block = GetEnvironmentStringsW();
        if (!block) throw std::runtime_error("Cannot read process environment");
        for (const wchar_t *entry = block; *entry; entry += wcslen(entry) + 1) {
            std::wstring value(entry); auto equal = value.find(L'=', value[0] == L'=' ? 1 : 0);
            if (equal != std::wstring::npos) env[value.substr(0, equal)] = value.substr(equal + 1);
        }
        FreeEnvironmentStringsW(block);
        for (const auto &[name, value] : overrides) { if (value.empty()) env.erase(name); else env[name] = value; }
        std::wstring environment;
        for (const auto &[name, value] : env) { environment += name + L'=' + value; environment += L'\0'; }
        environment += L'\0';
        std::wstring command = quote(program.native());
        for (const auto &arg : args) command += L' ' + quote(wide(arg));
        SIZE_T size = 0;
        InitializeProcThreadAttributeList(nullptr, 1, 0, &size);
        std::vector<unsigned char> attributes(size);
        auto *list = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attributes.data());
        if (!InitializeProcThreadAttributeList(list, 1, 0, &size)) throw std::runtime_error("Cannot initialize child handle list");
        if (!UpdateProcThreadAttribute(list, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherited.data(),
                                       inherited.size() * sizeof(HANDLE), nullptr, nullptr)) {
            DeleteProcThreadAttributeList(list); throw std::runtime_error("Cannot restrict inherited handles");
        }
        STARTUPINFOEXW startup{}; startup.StartupInfo.cb = sizeof(startup);
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
        startup.StartupInfo.hStdInput = input.value;
        startup.StartupInfo.hStdOutput = startup.StartupInfo.hStdError = output.value;
        startup.lpAttributeList = list;
        PROCESS_INFORMATION info{};
        BOOL ok = CreateProcessW(program.c_str(), command.data(), nullptr, nullptr, TRUE,
            CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT | CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT,
            environment.data(), directory.c_str(), &startup.StartupInfo, &info);
        auto failure = GetLastError(); DeleteProcThreadAttributeList(list);
        if (!ok) throw std::runtime_error("Cannot start native process: Windows error " + std::to_string(failure));
        process = Handle(info.hProcess); Handle thread(info.hThread); pid = info.dwProcessId;
        job = Handle(CreateJobObjectW(nullptr, nullptr));
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if (job.value == INVALID_HANDLE_VALUE || !SetInformationJobObject(job.value, JobObjectExtendedLimitInformation, &limits, sizeof(limits)) ||
            !AssignProcessToJobObject(job.value, process.value)) {
            TerminateProcess(process.value, 1); throw std::runtime_error("Cannot contain native child process");
        }
        ResumeThread(thread.value);
    }
};
} // namespace bako::windows
