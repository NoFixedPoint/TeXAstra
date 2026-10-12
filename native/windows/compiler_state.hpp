#pragma once
#include "checkpoint_arena.hpp"
#include <array>
#include <cstdio>
#include <map>
#include <malloc.h>

namespace bako::windows {
// The allocator's entire metadata lives in the rollback domain. DLL/CRT and
// controller allocations remain outside; engine malloc calls use this allocator.
class CompilerHeap {
    struct Header { uint64_t capacity, next; };
    struct State { uint64_t used; uint64_t bins[64]; };
    CheckpointArena arena;
    State *state;
    static unsigned bin(size_t size) {
        unsigned result = 5;
        while ((uint64_t(1) << result) < size) ++result;
        return result;
    }
  public:
    explicit CompilerHeap(size_t capacity) : arena(capacity, sizeof(State)) {
        state = reinterpret_cast<State *>(arena.data());
        state->used = (sizeof(State) + 15) & ~size_t(15);
    }
    bool owns(const void *pointer) {
        auto address = reinterpret_cast<uintptr_t>(pointer);
        auto start = reinterpret_cast<uintptr_t>(arena.data());
        return address >= start && address - start < arena.size();
    }
    void *allocate(size_t size) {
        if (size > arena.size() - sizeof(Header)) return nullptr;
        unsigned bucket = bin(std::max(size, size_t(1)) + sizeof(Header));
        size_t amount = size_t(1) << bucket;
        uint64_t offset = state->bins[bucket];
        if (offset) state->bins[bucket] = reinterpret_cast<Header *>(arena.data() + offset)->next;
        else {
            if (amount > arena.size() - state->used) return nullptr;
            offset = state->used;
            state->used += amount;
            arena.track(state->used);
        }
        auto *header = reinterpret_cast<Header *>(arena.data() + offset);
        header->capacity = amount;
        header->next = 0;
        return header + 1;
    }
    void release(void *pointer) {
        if (!pointer) return;
        auto *header = static_cast<Header *>(pointer) - 1;
        unsigned bucket = bin(header->capacity);
        header->next = state->bins[bucket];
        state->bins[bucket] = reinterpret_cast<unsigned char *>(header) - arena.data();
    }
    void *resize(void *pointer, size_t size) {
        if (!pointer) return allocate(size);
        if (!size) { release(pointer); return nullptr; }
        auto capacity = (static_cast<Header *>(pointer) - 1)->capacity - sizeof(Header);
        if (size <= capacity && size > capacity / 2) return pointer;
        void *result = allocate(size);
        if (!result) return nullptr;
        std::memcpy(result, pointer, std::min(size, capacity));
        release(pointer);
        return result;
    }
    uint64_t capture() { return arena.capture(); }
    void restore(uint64_t id) { arena.restore(id); }
    size_t used() { return state->used; }
    void prepare_io(const void *pointer, size_t size) {
        if (owns(pointer)) arena.prepare_io(static_cast<const unsigned char *>(pointer) - arena.data(), size);
    }
};

// The compiler is a separate PE module. Its writable sections belong to the
// engine; the host's controller, STL, CRT and checkpoint metadata do not.
class CompilerState {
    struct Section { unsigned char *address; size_t size; };
    struct Snapshot {
        uint64_t heap_id;
        CONTEXT context;
        std::vector<unsigned char> stack;
        std::vector<std::vector<unsigned char>> globals;
    };
    std::vector<Section> sections;
    std::map<int, Snapshot> snapshots;
    Snapshot *target = nullptr;
    bool resumed = false;
    int limit = 10000;
    // No owning automatic C++ objects may remain between restoring the stack
    // and RtlRestoreContext. Run beneath the target stack before copying it.
    [[noreturn]] __declspec(noinline) void restore_stack() {
        volatile unsigned char marker = 0;
        auto here = reinterpret_cast<uintptr_t>(&marker);
        size_t reserve = 65536 + (here > target->context.Rsp ? here - target->context.Rsp : 0);
        auto *scratch = static_cast<volatile unsigned char *>(_alloca(reserve));
        scratch[0] = 0;
        std::memcpy(reinterpret_cast<void *>(target->context.Rsp), target->stack.data(), target->stack.size());
        RtlRestoreContext(&target->context, nullptr);
        std::abort();
    }
  public:
    CompilerHeap heap;
    explicit CompilerState(size_t capacity = size_t(2) * 1024 * 1024 * 1024) : heap(capacity) {}
    void attach(HMODULE module) {
        auto *base = reinterpret_cast<unsigned char *>(module);
        auto *dos = reinterpret_cast<IMAGE_DOS_HEADER *>(base);
        auto *nt = reinterpret_cast<IMAGE_NT_HEADERS64 *>(base + dos->e_lfanew);
        auto *section = IMAGE_FIRST_SECTION(nt);
        for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; ++i, ++section) {
            if ((section->Characteristics & IMAGE_SCN_MEM_WRITE) && section->Misc.VirtualSize)
                sections.push_back({base + section->VirtualAddress, section->Misc.VirtualSize});
        }
    }
    bool returning() {
        if (!resumed) return false;
        resumed = false;
        return true;
    }
    int requested_limit() const { return limit; }
    void capture(int index, const CONTEXT &context) {
        Snapshot snapshot;
        snapshot.context = context;
        auto top = reinterpret_cast<uintptr_t>(reinterpret_cast<NT_TIB *>(NtCurrentTeb())->StackBase);
        if (context.Rsp >= top || top - context.Rsp > 4 * 1024 * 1024)
            throw std::runtime_error("Compiler continuation exceeds supported stack range");
        snapshot.stack.assign(reinterpret_cast<unsigned char *>(context.Rsp),
                              reinterpret_cast<unsigned char *>(top));
        for (const auto &section : sections)
            snapshot.globals.emplace_back(section.address, section.address + section.size);
        snapshot.heap_id = heap.capture();
        snapshots[index] = std::move(snapshot);
    }
    bool contains(int index) const { return snapshots.count(index) != 0; }
    [[noreturn]] void restore(int index, int requested) {
        auto found = snapshots.find(index);
        if (found == snapshots.end()) throw std::runtime_error("Checkpoint is unavailable");
        snapshots.erase(std::next(found), snapshots.end());
        target = &found->second;
        heap.restore(target->heap_id);
        for (size_t i = 0; i < sections.size(); ++i)
            std::memcpy(sections[i].address, target->globals[i].data(), sections[i].size);
        resumed = true;
        limit = requested;
        restore_stack();
    }
};
} // namespace bako::windows
