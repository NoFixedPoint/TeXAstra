#pragma once
// The controller uses spawn (never fork) because it has renderer threads.
#ifdef __APPLE__
#include <mach-o/dyld.h>
#include <sys/sysctl.h>
#endif

namespace bako {
inline void isolate_spawn(posix_spawn_file_actions_t &actions, posix_spawnattr_t &attr) {
#ifdef __APPLE__
    (void)actions;
    posix_spawnattr_setpgroup(&attr, 0);
    posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT);
#else
    posix_spawn_file_actions_addclosefrom_np(&actions, 3);
    posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETSID);
#endif
}
inline int unix_socket(bool nonblocking = false) {
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd >= 0) {
        fcntl(fd, F_SETFD, FD_CLOEXEC);
        if (nonblocking) fcntl(fd, F_SETFL, O_NONBLOCK);
    }
    return fd;
}
inline int accept_socket(int listener) {
    int fd = accept(listener, nullptr, nullptr);
    if (fd >= 0) fcntl(fd, F_SETFD, FD_CLOEXEC);
    return fd;
}
inline char process_state(pid_t pid) {
    if (pid <= 0) return 'Z';
#ifdef __APPLE__
    int mib[] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, pid};
    struct kinfo_proc info = {};
    size_t size = sizeof(info);
    if (sysctl(mib, 4, &info, &size, nullptr, 0) || !size) return 'Z';
    return info.kp_proc.p_stat == SSTOP ? 'T' : info.kp_proc.p_stat == SZOMB ? 'Z' : 'R';
#else
    try {
        auto s = read(fs::path("/proc") / std::to_string(pid) / "stat");
        return s.at(s.rfind(") ") + 2);
    } catch (...) { return 'Z'; }
#endif
}
inline fs::path executable_path() {
#ifdef __APPLE__
    uint32_t size = 0;
    _NSGetExecutablePath(nullptr, &size);
    std::vector<char> buffer(size);
    if (_NSGetExecutablePath(buffer.data(), &size)) throw std::runtime_error("Cannot locate runtime");
    return fs::canonical(buffer.data());
#else
    return fs::canonical("/proc/self/exe");
#endif
}
// A short symlink avoids Darwin's 104-byte Unix socket path limit even when
// the project and persistent cache have long names. No process-wide chdir.
struct SocketDirectory {
    fs::path temporary;
    ~SocketDirectory() {
        if (!temporary.empty()) {
            std::error_code ignored;
            fs::remove(temporary / "s", ignored);
            fs::remove(temporary, ignored);
        }
    }
    std::string path(const fs::path &directory, int fd, const std::string &name) {
#ifdef __APPLE__
        (void)fd;
        if (temporary.empty()) {
            char pattern[] = "/tmp/texastra-sock-XXXXXX";
            auto created = mkdtemp(pattern);
            if (!created) throw std::runtime_error("Cannot create socket directory");
            temporary = created;
            fs::create_directory_symlink(fs::canonical(directory), temporary / "s");
        }
        return (temporary / "s" / name).string();
#else
        (void)directory;
        return (fs::path("/proc/self/fd") / std::to_string(fd) / name).string();
#endif
    }
};
}
