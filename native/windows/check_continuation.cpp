#include "compiler_state.hpp"
#include <iostream>
using bako::windows::CompilerState;
static CompilerState *compiler;
static int phase = 0;
__declspec(noinline) int checkpoint(int index) {
    CONTEXT context;
    RtlCaptureContext(&context);
    if (compiler->returning()) return 1;
    compiler->capture(index, context);
    return 0;
}
__declspec(noinline) void restore_shallow() { compiler->restore(1, 7); }
__declspec(noinline) int exercise() {
    volatile unsigned char stack_data[32768];
    for (size_t i = 0; i < sizeof(stack_data); ++i) stack_data[i] = static_cast<unsigned char>(i);
    auto *buffer = static_cast<unsigned char *>(compiler->heap.allocate(4000));
    std::memset(buffer, 31, 4000);
    checkpoint(1);
    if (phase == 0) {
        phase = 1;
        std::memset(buffer, 41, 4000);
        compiler->heap.release(buffer);
        auto *reuse = compiler->heap.allocate(4000);
        if (reuse != buffer) throw std::runtime_error("Allocator reuse failed");
        auto *later = compiler->heap.allocate(600000);
        std::memset(later, 99, 600000);
        return 0;
    }
    if (buffer[0] != 31 || buffer[3999] != 31 || compiler->requested_limit() != 7)
        throw std::runtime_error("Heap/context restoration failed");
    for (size_t i = 0; i < sizeof(stack_data); ++i)
        if (stack_data[i] != static_cast<unsigned char>(i)) throw std::runtime_error("Stack restoration failed");
    auto *discarded = static_cast<unsigned char *>(compiler->heap.allocate(600000));
    if (discarded[0] != 0 || discarded[599999] != 0)
        throw std::runtime_error("Allocation high-water rollback failed");
    std::cout << "{\"ok\":true,\"retainedContinuation\":true,\"restoredStackBytes\":32768}\n";
    return 1;
}
int main() {
    try {
    // Controller state must not live on the stack that is being restored.
    compiler = new CompilerState(4 * 1024 * 1024);
    if (!exercise()) restore_shallow();
    delete compiler;
    return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
