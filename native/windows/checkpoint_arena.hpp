#pragma once
// Native Windows checkpoint storage. This is not a whole-process snapshot:
// callers must own all tracked state and stop writes at capture/restore points.
#ifndef _WIN32
#error CheckpointArena requires Windows
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace bako::windows {
class CheckpointArena {
    using Bytes = std::vector<unsigned char>;
    using Page = std::shared_ptr<const Bytes>;
    static constexpr size_t leaf_size = 256;
    using Leaf = std::vector<Page>;
    using Image = std::vector<std::shared_ptr<const Leaf>>;
    struct Snapshot { uint64_t id; Image image; };
    struct Pending { const unsigned char *bytes = nullptr; bool load = false; };
    inline static std::atomic<CheckpointArena *> active{nullptr};
    DWORD owner = GetCurrentThreadId();
    unsigned char *memory = nullptr;
    size_t byte_count = 0, page_size = 0, page_count = 0;
    PVOID handler = nullptr;
    Image current;
    std::vector<Snapshot> snapshots;
    std::vector<Pending> pending;
    std::vector<void *> written;
    uint64_t next_id = 1, faults = 0, copied_bytes = 0;

    static std::runtime_error error(const char *operation) {
        return std::runtime_error(std::string(operation) + " failed: Windows error " +
                                  std::to_string(GetLastError()));
    }
    void require_owner() const {
        if (GetCurrentThreadId() != owner)
            throw std::logic_error("CheckpointArena requires its owning thread");
    }
    static const Page &page(const Image &image, size_t index) {
        static const Page empty;
        const auto &leaf = image[index / leaf_size];
        return leaf ? (*leaf)[index % leaf_size] : empty;
    }
    static LONG CALLBACK fault(EXCEPTION_POINTERS *exception) noexcept {
        auto *self = active.load(std::memory_order_acquire);
        const auto *record = exception->ExceptionRecord;
        if (!self || GetCurrentThreadId() != self->owner ||
            record->ExceptionCode != EXCEPTION_ACCESS_VIOLATION ||
            record->NumberParameters < 2 || record->ExceptionInformation[0] > 1)
            return EXCEPTION_CONTINUE_SEARCH;
        auto address = static_cast<uintptr_t>(record->ExceptionInformation[1]);
        auto base = reinterpret_cast<uintptr_t>(self->memory);
        if (address < base || address - base >= self->byte_count)
            return EXCEPTION_CONTINUE_SEARCH;
        size_t index = (address - base) / self->page_size;
        auto &entry = self->pending[index];
        if (!entry.load) return EXCEPTION_CONTINUE_SEARCH;
        auto *destination = self->memory + index * self->page_size;
        DWORD previous;
        if (!VirtualProtect(destination, self->page_size, PAGE_READWRITE, &previous))
            return EXCEPTION_CONTINUE_SEARCH;
        // No allocation, locks, shared_ptr changes, or exceptions in the VEH.
        if (entry.bytes) std::memcpy(destination, entry.bytes, self->page_size);
        else std::memset(destination, 0, self->page_size);
        entry.load = false;
        ++self->faults;
        self->copied_bytes += self->page_size;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

  public:
    explicit CheckpointArena(size_t bytes) {
        SYSTEM_INFO system;
        GetSystemInfo(&system);
        page_size = system.dwPageSize;
        if (!bytes || bytes > SIZE_MAX - page_size + 1)
            throw std::invalid_argument("Invalid checkpoint arena size");
        page_count = (bytes + page_size - 1) / page_size;
        byte_count = page_count * page_size;
        current.resize((page_count + leaf_size - 1) / leaf_size);
        pending.resize(page_count);
        written.resize(page_count);
        memory = static_cast<unsigned char *>(VirtualAlloc(nullptr, byte_count,
            MEM_RESERVE | MEM_COMMIT | MEM_WRITE_WATCH, PAGE_READWRITE));
        if (!memory) throw error("VirtualAlloc");
        CheckpointArena *expected = nullptr;
        if (!active.compare_exchange_strong(expected, this, std::memory_order_release)) {
            VirtualFree(memory, 0, MEM_RELEASE);
            throw std::logic_error("Only one checkpoint arena is supported per process");
        }
        handler = AddVectoredExceptionHandler(1, fault);
        if (!handler) {
            active.store(nullptr, std::memory_order_release);
            VirtualFree(memory, 0, MEM_RELEASE);
            throw error("AddVectoredExceptionHandler");
        }
    }
    ~CheckpointArena() {
        // Destruction, like access, must happen after all compiler writes stop.
        RemoveVectoredExceptionHandler(handler);
        active.store(nullptr, std::memory_order_release);
        VirtualFree(memory, 0, MEM_RELEASE);
    }
    CheckpointArena(const CheckpointArena &) = delete;
    CheckpointArena &operator=(const CheckpointArena &) = delete;
    unsigned char *data() { require_owner(); return memory; }
    size_t size() const { return byte_count; }
    size_t granularity() const { return page_size; }
    size_t checkpoint_count() const { return snapshots.size(); }
    uint64_t materialized_pages() const { return faults; }
    uint64_t restored_bytes() const { return copied_bytes; }

    // Windows may probe a buffer in kernel mode without dispatching a user-mode
    // VEH. Materialize before passing arena ranges into ReadFile/WriteFile/etc.
    void prepare_io(size_t offset, size_t length) {
        require_owner();
        if (offset > byte_count || length > byte_count - offset)
            throw std::out_of_range("I/O range escapes checkpoint arena");
        if (!length) return;
        const size_t last = (offset + length - 1) / page_size;
        for (size_t i = offset / page_size; i <= last; ++i) {
            volatile unsigned char byte = memory[i * page_size];
            (void)byte;
        }
    }

    uint64_t capture() {
        require_owner();
        ULONG_PTR count = written.size();
        ULONG granularity = 0;
        auto status = GetWriteWatch(0, memory, byte_count, written.data(), &count, &granularity);
        if (status || granularity != page_size)
            throw std::runtime_error("GetWriteWatch failed or returned unsupported granularity");
        Image image = current;
        std::vector<std::shared_ptr<Leaf>> modified(image.size());
        for (size_t i = 0; i < count; ++i) {
            size_t index = (static_cast<unsigned char *>(written[i]) - memory) / page_size;
            if (pending[index].load) continue;
            auto *source = memory + index * page_size;
            const auto &before = page(current, index);
            // Materialization itself sets write-watch bits. A read-only replay
            // must not create another copy of unchanged snapshot data.
            if (before && std::memcmp(before->data(), source, page_size) == 0) continue;
            if (!before && std::all_of(source, source + page_size,
                                     [](unsigned char byte) { return byte == 0; })) continue;
            size_t leaf_index = index / leaf_size;
            auto &leaf = modified[leaf_index];
            if (!leaf) {
                leaf = image[leaf_index] ? std::make_shared<Leaf>(*image[leaf_index])
                                         : std::make_shared<Leaf>(leaf_size);
                image[leaf_index] = leaf;
            }
            (*leaf)[index % leaf_size] = std::make_shared<Bytes>(source, source + page_size);
        }
        // Keep write-watch bits until every potentially failing allocation is
        // done: allocation failure must not lose uncaptured compiler changes.
        snapshots.push_back({next_id, image});
        if (ResetWriteWatch(memory, byte_count)) {
            snapshots.pop_back();
            throw std::runtime_error("ResetWriteWatch failed");
        }
        current.swap(image);
        return next_id++;
    }

    void restore(uint64_t id) {
        require_owner();
        auto found = std::find_if(snapshots.begin(), snapshots.end(),
                                  [id](const auto &snapshot) { return snapshot.id == id; });
        if (found == snapshots.end()) throw std::invalid_argument("Unknown or invalidated checkpoint");
        Image target = found->image;
        DWORD previous;
        // One protection operation, no traversal of an undo chain and no eager
        // copy of old compiler bytes. Page versions are indexed by the target.
        if (!VirtualProtect(memory, byte_count, PAGE_NOACCESS, &previous))
            throw error("VirtualProtect");
        current.swap(target);
        for (size_t i = 0; i < page_count; ++i) {
            const auto &version = page(current, i);
            pending[i] = {version ? version->data() : nullptr, true};
        }
        snapshots.erase(found + 1, snapshots.end());
        // Materialization will set bits again. No compiler writes may race us.
        if (ResetWriteWatch(memory, byte_count))
            throw std::runtime_error("ResetWriteWatch failed after restore");
    }
};
} // namespace bako::windows
