#include "checkpoint_arena.hpp"
#include <chrono>
#include <iostream>
#include <random>
#include <thread>

using bako::windows::CheckpointArena;
using Clock = std::chrono::steady_clock;
static unsigned checks = 0;
static void check(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
    ++checks;
}
template<class F> static void rejects(F action) {
    bool rejected = false;
    try { action(); } catch (const std::exception &) { rejected = true; }
    check(rejected, "Expected rejection");
}
static double milliseconds(Clock::time_point start) {
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
}
static double percentile(std::vector<double> values, double fraction) {
    std::sort(values.begin(), values.end());
    return values[static_cast<size_t>(std::ceil(values.size() * fraction)) - 1];
}
static void correctness() {
    rejects([] { CheckpointArena invalid(0); });
    {
        CheckpointArena arena(2 * 1024 * 1024 + 1);
        rejects([] { CheckpointArena duplicate(4096); });
        auto *bytes = arena.data();
        const auto step = arena.granularity();
        check(arena.size() >= 2 * 1024 * 1024 + 1, "Size rounding");
        auto zero = arena.capture();
        bytes[0] = 42; bytes[step - 1] = 71; bytes[step] = 83;
        bytes[arena.size() - 1] = 99;
        auto first = arena.capture();
        bytes[0] = 11;
        auto second = arena.capture();
        // Includes dirty state never captured, cross-page writes and the last page.
        bytes[step] = 17;
        arena.restore(first);
        check(bytes[0] == 42 && bytes[step - 1] == 71 && bytes[step] == 83 &&
              bytes[arena.size() - 1] == 99, "Restore captured and uncaptured writes");
        rejects([&] { arena.restore(second); });
        auto faults = arena.materialized_pages();
        auto unchanged = arena.capture();
        check(arena.materialized_pages() == faults, "Capture must not load pending pages");
        bytes[step * 7] = 31;
        arena.restore(unchanged);
        check(bytes[step * 7] == 0, "Previously untouched page restores zero");
        arena.restore(zero);
        check(bytes[0] == 0 && bytes[arena.size() - 1] == 0, "Restore initial zero image");
        arena.restore(zero);
        faults = arena.materialized_pages();
        arena.prepare_io(step - 1, 2);
        check(arena.materialized_pages() == faults + 2, "Prepare cross-page I/O buffer");
        arena.prepare_io(arena.size(), 0);
        rejects([&] { arena.prepare_io(arena.size(), 1); });
        rejects([&] { arena.prepare_io(1, SIZE_MAX); });
        // Use a real kernel I/O call, not memcpy, to verify prepared buffers.
        HANDLE output = CreateFileW(L"NUL", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                    nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        check(output != INVALID_HANDLE_VALUE, "Open kernel I/O target");
        DWORD transferred = 0;
        BOOL sent = WriteFile(output, bytes + step - 1, 2, &transferred, nullptr);
        CloseHandle(output);
        check(sent && transferred == 2, "Prepared arena buffer supports WriteFile");
        bool rejected = false;
        std::thread foreign([&] {
            try { arena.capture(); } catch (const std::logic_error &) { rejected = true; }
        });
        foreign.join();
        check(rejected, "Reject cross-thread control");
    }
    // Exercise a second arena after handler teardown, branch histories and
    // arbitrary earlier restores against an independent full-memory model.
    CheckpointArena arena(1024 * 1024);
    auto *bytes = arena.data();
    std::vector<unsigned char> model(arena.size());
    struct Reference { uint64_t id; std::vector<unsigned char> bytes; };
    std::vector<Reference> history{{arena.capture(), model}};
    std::mt19937 random(20261011);
    for (int round = 0; round < 240; ++round) {
        for (int edit = 0; edit < 100; ++edit) {
            auto index = random() % arena.size();
            bytes[index] = model[index] = static_cast<unsigned char>(random());
        }
        if (round % 3 != 0) history.push_back({arena.capture(), model});
        else {
            auto target = random() % history.size();
            arena.restore(history[target].id);
            model = history[target].bytes;
            history.resize(target + 1);
        }
        check(std::memcmp(bytes, model.data(), model.size()) == 0, "Randomized byte equivalence");
        check(arena.checkpoint_count() == history.size(), "Branch invalidation count");
    }
}

int main(int argc, char **argv) {
    try {
        // Child-process probes verify the VEH does not swallow unrelated,
        // executable-memory, or foreign-thread access violations.
        SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
        if (argc == 2) {
            CheckpointArena arena(4096);
            auto *bytes = arena.data();
            auto checkpoint = arena.capture();
            arena.restore(checkpoint);
            const std::string mode = argv[1];
            if (mode == "--foreign-thread-fault") {
                std::thread foreign([&] { bytes[0] = 1; });
                foreign.join();
            } else if (mode == "--unrelated-fault") {
                auto *outside = static_cast<volatile unsigned char *>(VirtualAlloc(
                    nullptr, 4096, MEM_RESERVE | MEM_COMMIT, PAGE_NOACCESS));
                if (!outside) throw std::runtime_error("Fault probe allocation failed");
                *outside = 1;
            } else if (mode == "--execute-fault") {
                reinterpret_cast<void (*)()>(bytes)();
            } else throw std::runtime_error("Unknown fault probe");
            return 2;
        }
        correctness();
        constexpr size_t mib = 1024 * 1024;
        CheckpointArena arena(128 * mib);
        auto *bytes = arena.data();
        std::memset(bytes, 3, arena.size());
        const auto early = arena.capture();
        // A far rollback invalidates 96 checkpoints and 96 MiB of old page
        // versions. Include reclamation and first access in the measurement.
        std::vector<double> far_timings, capture_timings;
        for (int repeat = 0; repeat < 20; ++repeat) {
            for (size_t i = 0; i < 96; ++i) {
                std::memset(bytes + i * mib, static_cast<int>(i + 4), mib);
                auto start = Clock::now();
                arena.capture();
                capture_timings.push_back(milliseconds(start));
            }
            bytes[120 * mib] = 77;
            auto copied = arena.restored_bytes();
            auto start = Clock::now();
            arena.restore(early);
            volatile unsigned char first = bytes[0];
            far_timings.push_back(milliseconds(start));
            check(first == 3, "Far rollback value");
            check(arena.restored_bytes() - copied == arena.granularity(), "Lazy far rollback copied one page");
            check(bytes[120 * mib] == 3, "Far rollback drops uncaptured writes");
        }
        // Repeated local edits after a far restore: capture, dirty 64 KiB,
        // restore, then read every touched page. This includes lazy page cost.
        std::vector<double> timings;
        for (int iteration = 0; iteration < 100; ++iteration) {
            auto checkpoint = arena.capture();
            std::memset(bytes, 8, 64 * 1024);
            auto start = Clock::now();
            arena.restore(checkpoint);
            unsigned sum = 0;
            for (size_t offset = 0; offset < 64 * 1024; offset += arena.granularity())
                sum += bytes[offset];
            timings.push_back(milliseconds(start));
            check(sum == 3 * (64 * 1024 / arena.granularity()), "Warm rollback values");
        }
        // Full replay is deliberately reported separately, so lazy restoration
        // cannot hide the eventual cost of touching the entire historical state.
        arena.restore(early);
        auto start = Clock::now();
        uint64_t sum = 0;
        for (size_t offset = 0; offset < arena.size(); offset += arena.granularity())
            sum += bytes[offset];
        double replay_ms = milliseconds(start);
        check(sum == 3 * (arena.size() / arena.granularity()), "Full replay values");
        std::cout << "{\"ok\":true,\"checks\":" << checks
                  << ",\"arenaMiB\":128,\"farInvalidatedCheckpoints\":96"
                  << ",\"farRestoreSamples\":20"
                  << ",\"farRestoreAndFirstReadP50Ms\":" << percentile(far_timings, .5)
                  << ",\"farRestoreAndFirstReadP95Ms\":" << percentile(far_timings, .95)
                  << ",\"farRestoreAndFirstReadMaxMs\":" << *std::max_element(far_timings.begin(), far_timings.end())
                  << ",\"capture1MiBP95Ms\":" << percentile(capture_timings, .95)
                  << ",\"warmRestore64KiBp50Ms\":" << percentile(timings, .5)
                  << ",\"warmRestore64KiBp95Ms\":" << percentile(timings, .95)
                  << ",\"fullReplay128MiBMs\":" << replay_ms
                  << ",\"materializedPages\":" << arena.materialized_pages()
                  << ",\"compilerIntegrated\":false,\"endToEndLatencyMeasured\":false}\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
