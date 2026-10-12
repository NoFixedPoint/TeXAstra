#include "compiler_state.hpp"
#include <filesystem>
#include <fstream>
#include <sstream>
#include <set>
#include <iostream>

namespace fs = std::filesystem;
using bako::windows::CompilerState;
struct FileState { void *file; long long offset; std::string prefix; bool writable; };
struct CompilerFile { fs::path path; bool writable, open; };
struct Worker {
    CompilerState compiler;
    HMODULE engine = nullptr;
    HANDLE commands = INVALID_HANDLE_VALUE, events = INVALID_HANDLE_VALUE;
    bool live = false, prime = false;
    int checkpoints = 0;
    long long request_us = 0, resumed_us = 0;
    std::map<void *, CompilerFile> files;
    std::map<int, std::vector<FileState>> histories;
    std::string command;
    int (*flush)(void *) = nullptr;
    long long (*tell)(void *) = nullptr;
    int (*seek)(void *, long long) = nullptr;
    int (*close)(void *) = nullptr;
    size_t (*fonts)(const int *, int, char **) = nullptr;
    void (*release_bundle)(void *) = nullptr;
    template<class T> T symbol(const char *name) {
        auto result = GetProcAddress(engine, name);
        if (!result) throw std::runtime_error(std::string("Missing engine export: ") + name);
        return reinterpret_cast<T>(result);
    }
    bool pinned(void *file) const {
        for (const auto &[index, history] : histories) {
            (void)index;
            for (const auto &entry : history) if (entry.file == file) return true;
        }
        return false;
    }
    void capture_files(int index) {
        std::vector<FileState> captured;
        for (const auto &[file, info] : files) if (info.open) {
            if (info.writable && flush(file)) throw std::runtime_error("Cannot flush compiler file");
            auto position = tell(file);
            if (position < 0) throw std::runtime_error("Compiler checkpoint contains a non-seekable file");
            FileState saved{file, position, {}, info.writable};
            if (info.writable) {
                std::ifstream input(info.path, std::ios::binary);
                if (!input) throw std::runtime_error("Cannot capture compiler output prefix");
                saved.prefix.assign(std::istreambuf_iterator<char>(input), {});
            }
            captured.push_back(std::move(saved));
        }
        histories[index] = std::move(captured);
    }
    void restore_files(int index) {
        auto found = histories.find(index);
        if (found == histories.end()) throw std::runtime_error("Missing compiler file checkpoint");
        histories.erase(std::next(found), histories.end());
        std::set<void *> wanted;
        for (const auto &saved : found->second) wanted.insert(saved.file);
        for (auto it = files.begin(); it != files.end();) {
            if (!wanted.count(it->first)) {
                it->second.open = false;
                if (!pinned(it->first)) { close(it->first); it = files.erase(it); continue; }
            }
            ++it;
        }
        for (const auto &saved : found->second) {
            auto &info = files.at(saved.file);
            if (info.writable) flush(saved.file);
            if (seek(saved.file, 0)) throw std::runtime_error("Cannot rewind compiler file");
            if (saved.writable) {
                // Share with the retained CRT handle. Its buffer was flushed;
                // restore bytes/truncation before installing the logical offset.
                HANDLE output = CreateFileW(info.path.c_str(), GENERIC_WRITE,
                    FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                    OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
                if (output == INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot restore compiler output");
                DWORD written = 0;
                bool ok = WriteFile(output, saved.prefix.data(), static_cast<DWORD>(saved.prefix.size()), &written, nullptr) &&
                          written == saved.prefix.size() && SetEndOfFile(output);
                CloseHandle(output);
                if (!ok) throw std::runtime_error("Cannot restore compiler output prefix");
            }
            if (seek(saved.file, saved.offset)) throw std::runtime_error("Cannot restore compiler input offset");
            info.open = true;
        }
    }
    void send(const void *bytes, size_t size) {
        auto *data = static_cast<const char *>(bytes);
        while (size) {
            DWORD written;
            if (!WriteFile(events, data, static_cast<DWORD>(std::min(size, size_t(1 << 20))), &written, nullptr) || !written)
                ExitProcess(0);
            data += written; size -= written;
        }
    }
    void read_command() {
        command.clear();
        for (;;) {
            char byte; DWORD got;
            if (!ReadFile(commands, &byte, 1, &got, nullptr) || !got) ExitProcess(0);
            if (byte == '\n') return;
            if (command.size() >= 4096) throw std::runtime_error("Invalid compiler control message");
            command += byte;
        }
    }
    [[noreturn]] void resume(int index, int limit) {
        LARGE_INTEGER tick, frequency; QueryPerformanceCounter(&tick); QueryPerformanceFrequency(&frequency);
        request_us = (tick.QuadPart / frequency.QuadPart) * 1000000 + (tick.QuadPart % frequency.QuadPart) * 1000000 / frequency.QuadPart;
        restore_files(index);
        live = true;
        compiler.restore(index, limit);
    }
    void loop();
};
static Worker *worker = nullptr;

extern "C" {
__declspec(dllexport) long long bako_host_now();
__declspec(dllexport) void bako_host_io(const void *pointer, size_t size) { worker->compiler.heap.prepare_io(pointer, size); }
__declspec(dllexport) void *bako_host_malloc(size_t size) { return worker->compiler.heap.allocate(size); }
__declspec(dllexport) void *bako_host_realloc(void *pointer, size_t size) {
    if (pointer && !worker->compiler.heap.owns(pointer)) {
        std::fputs("Native engine attempted to resize unowned memory\n", stderr); ExitProcess(8);
    }
    return worker->compiler.heap.resize(pointer, size);
}
__declspec(dllexport) int bako_host_free(void *pointer) {
    if (!worker->compiler.heap.owns(pointer)) return 0;
    worker->compiler.heap.release(pointer); return 1;
}
__declspec(dllexport) void bako_host_open(void *file, const char *path, const char *mode) {
    worker->files[file] = {fs::absolute(fs::u8path(path)), std::strchr(mode, 'w') || std::strchr(mode, 'a') || std::strchr(mode, '+'), true};
}
__declspec(dllexport) int bako_host_close(void *file) {
    auto found = worker->files.find(file);
    if (found == worker->files.end()) return 0;
    if (worker->pinned(file)) {
        if (found->second.writable) worker->flush(file);
        found->second.open = false;
        return 1;
    }
    worker->files.erase(found); return 0;
}
__declspec(dllexport) __declspec(noinline) int bako_host_checkpoint(int index) {
    CONTEXT context;
    RtlCaptureContext(&context);
    if (worker->compiler.returning()) { worker->resumed_us = bako_host_now(); return worker->compiler.requested_limit(); }
    worker->capture_files(index);
    worker->compiler.capture(index, context);
    if (index < 10000) {
        char path[64]; std::snprintf(path, sizeof(path), "cp-%03d.pid", index);
        std::ofstream(path) << GetCurrentProcessId();
        ++worker->checkpoints;
    }
    return worker->compiler.requested_limit();
}
__declspec(dllexport) int bako_host_live() { return worker->live ? 1 : 0; }
__declspec(dllexport) void bako_host_publish(const char *metadata, size_t m, const char *bytes, size_t n) {
    char header[100]; int count = std::snprintf(header, sizeof(header), "%zu %zu\n", m, n);
    worker->send(header, static_cast<size_t>(count)); worker->send(metadata, m); worker->send(bytes, n);
    worker->loop();
}
__declspec(dllexport) void bako_host_park() { if (!worker->prime) worker->loop(); }
__declspec(dllexport) long long bako_host_now() {
    LARGE_INTEGER ticks, frequency; QueryPerformanceCounter(&ticks); QueryPerformanceFrequency(&frequency);
    return (ticks.QuadPart / frequency.QuadPart) * 1000000 + (ticks.QuadPart % frequency.QuadPart) * 1000000 / frequency.QuadPart;
}
__declspec(dllexport) void bako_host_timings(long long *values) {
    values[0]=worker->request_us; values[1]=worker->request_us;
    values[2]=worker->resumed_us; values[3]=worker->request_us;
}
__declspec(dllexport) void bako_host_stats(char *data, size_t size) {
    std::snprintf(data, size, "{\"mode\":\"windows\",\"pid\":%lu,\"checkpoints\":%d,\"heapUsedBytes\":%zu}",
                  GetCurrentProcessId(), worker->checkpoints, worker->compiler.heap.used());
}
}

void Worker::loop() {
    for (;;) {
        read_command();
        if (command == "continue") return;
        if (command == "close") ExitProcess(0);
        if (command.compare(0, 8, "restore ") == 0) {
            int index = 0, limit = 0;
            if (std::sscanf(command.c_str(), "restore %d %d", &index, &limit) != 2 || limit < 1 || limit > 10000)
                throw std::runtime_error("Invalid compiler restore request");
            resume(index, limit);
        }
        if (command.compare(0, 6, "fonts ") == 0) {
            // A disposable in-process checkpoint isolates resource-export writes.
            // Control command remains in the host, outside the rollback domain.
            CONTEXT context;
            RtlCaptureContext(&context);
            if (compiler.returning()) continue;
            capture_files(10001);
            compiler.capture(10001, context);
            {
                std::istringstream input(command.substr(6));
                std::vector<int> ids; int id;
                while (input >> id) { if (id <= 0 || ids.size() >= 256) break; ids.push_back(id); }
                char *data = nullptr;
                size_t size = ids.empty() ? 0 : fonts(ids.data(), static_cast<int>(ids.size()), &data);
                auto header = std::to_string(size) + "\n";
                send(header.data(), header.size()); if (size) send(data, size);
                if (data) release_bundle(data);
            }
            resume(10001, compiler.requested_limit());
        }
    }
}

int run_compiler_worker(const fs::path &module, int argc, char **argv) {
    worker = new Worker;
    worker->prime = std::getenv("BAKO_SNAPSHOT_DISABLE") != nullptr;
    if (const char *value = std::getenv("BAKO_COMMAND_HANDLE"))
        worker->commands = reinterpret_cast<HANDLE>(std::strtoull(value, nullptr, 10));
    if (const char *value = std::getenv("BAKO_EVENT_HANDLE"))
        worker->events = reinterpret_cast<HANDLE>(std::strtoull(value, nullptr, 10));
    worker->engine = LoadLibraryW(module.c_str());
    if (!worker->engine) throw std::runtime_error("Cannot load native compiler module: " + std::to_string(GetLastError()));
    worker->flush = worker->symbol<decltype(worker->flush)>("bako_file_flush");
    worker->tell = worker->symbol<decltype(worker->tell)>("bako_file_tell");
    worker->seek = worker->symbol<decltype(worker->seek)>("bako_file_seek");
    worker->close = worker->symbol<decltype(worker->close)>("bako_file_close");
    worker->fonts = worker->symbol<decltype(worker->fonts)>("bako_font_bundle");
    worker->release_bundle = worker->symbol<decltype(worker->release_bundle)>("bako_release_bundle");
    worker->compiler.attach(worker->engine);
    auto entry = worker->symbol<int (*)(int, char **)>("bako_engine_main");
    return entry(argc, argv);
}

#ifdef BAKO_WORKER_STANDALONE
int main(int argc, char **argv) {
    try {
        wchar_t path[32768]; GetModuleFileNameW(nullptr, path, 32768);
        return run_compiler_worker(fs::path(path).parent_path() / "texastra-engine.dll", argc, argv);
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
#endif
