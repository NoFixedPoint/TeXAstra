# Native Windows implementation status — 2026-10-11

**Native Windows preview support is not complete.** The implemented work is a
checkpoint-memory foundation and a standalone native validation executable.
LuaHBTeX is not using it yet. No Windows VSIX release or performance-parity claim
is made; version 0.0.18 remains the existing Linux/WSL release.

The user requires retained incremental performance and prefers one native binary
plus the extension package. A full-recompile preview does not satisfy that
requirement. The [platform research](windows-checkpoint-research-20261011.md)
explains why Windows PSS, fibers, and a Cygwin build are not established drop-in
replacements for the current fork checkpoints.

## Implemented checkpoint memory

[`native/windows/checkpoint_arena.hpp`](../native/windows/checkpoint_arena.hpp)
owns a fixed-address `VirtualAlloc` reservation with `MEM_WRITE_WATCH`.
Capture retains immutable versions of changed pages. Two-level page tables share
unchanged leaves and page contents across checkpoints. After capture, write-watch
is reset only once all required allocations have succeeded.

Restore selects a checkpoint's page table directly, invalidates its successors,
and marks the arena inaccessible in one `VirtualProtect` call. A narrowly scoped
vectored exception handler materializes the selected version when a page is
first read or written. Restoration does not replay an undo chain or eagerly copy
all historical bytes. Freeing invalidated versions still costs time and is
included in the measurements below. Reading the full restored state still costs
time too; lazy restoration postpones that work rather than eliminating it.

The handler does not allocate, acquire locks, modify shared ownership counts, or
throw C++ exceptions. It handles only expected read/write faults on pending arena
pages in the owning thread. Execute faults, faults outside the arena, and faults
from other threads continue through the normal Windows exception machinery.

The interface provides `data`, `capture`, `restore`, and `prepare_io`, plus size
and diagnostic counters. The caller supplies all mutable state inside the arena;
this module is not an allocator or a whole-process snapshot. Checkpoint IDs are
monotonic. Restoring an earlier ID invalidates all later IDs. Unsaved writes are
discarded on restore. The arena's address and capacity remain stable.

Only one arena per process is currently supported. Construction, access,
capture, restore and destruction belong to one thread. No concurrent writers are
allowed. Checkpoint tables, control flow and bookkeeping live outside the arena.
Pages passed into kernel I/O must first be materialized with `prepare_io`:
kernel buffer probing does not guarantee dispatch of a user-mode handler.

History is retained in ordinary process memory until a branch is invalidated or
the arena is destroyed. There is no persistent checkpoint file, memory-budget
eviction, automatic arena growth, or rollback of kernel resources. Allocation
failure during capture leaves the previous checkpoint history and pending
write-watch information intact. No production memory-pressure guarantee is made.

## Native build and validation

```powershell
python scripts/check_windows_checkpoint.py
# Equivalent:
npm run check:windows-checkpoint
```

The script locates installed MSVC x64 tools and a Windows SDK, invokes the
compiler directly, and statically links the CRT. It does not invoke WSL. The
output is `.work/windows-checkpoint/check-checkpoint.exe`; Python is only its
build/test driver. Import inspection confirms that this validation executable
depends only on `KERNEL32.dll`. This proves single-file packaging for the
checkpoint proof, not for the future compiler/renderer.

The check passes **655 assertions**, including randomized branching against an
independent full-memory reference, uncaptured writes, zero pages, page-edge
writes, repeated old-checkpoint restoration, invalidated IDs, capture of partially
materialized state, cross-thread control rejection, handler teardown/recreation,
I/O range overflow checks, and actual `WriteFile` from a prepared arena range.
Three separate child processes verify that foreign-thread, unrelated-memory and
execute faults terminate with Windows access-violation status instead of being
swallowed by the handler. The build uses `/W4 /WX`.

The recorded run used Windows 10 x64 (build 19045), Intel Core i9-13900K,
MSVC 14.36.32532, and Windows SDK 10.0.22000.0. The synthetic arena is 128 MiB.

| Operation | Measured time |
| --- | ---: |
| Capture after changing 1 MiB, p95 over 1,920 captures | 0.649 ms |
| Restore across 96 checkpoints and read the first page, p50 over 20 trials | 18.954 ms |
| Same far rollback, p95 | 23.626 ms |
| Same far rollback, maximum | 24.866 ms |
| Warm rollback plus reading 64 KiB, p50 over 100 trials | 0.722 ms |
| Same warm rollback, p95 | 0.893 ms |
| Touch every page of the restored 128 MiB, one trial | 105.386 ms |

The far rollback includes releasing 96 MiB of invalidated page versions and
uncaptured writes. An assertion checks that its first access materializes exactly
one page. Full replay checks every page's value. These are memory microbenchmarks,
not TeX compilation, edit-to-payload, or edit-to-visible measurements. The previous
Linux snapshot and current browser benchmarks measure different workloads and
cannot be compared directly with these numbers. Physical memory pressure and
other Windows versions were not tested.

Raw results, executable/source hashes, toolchain identity, CPU and DLL imports
are in [`results/windows-checkpoint.json`](../results/windows-checkpoint.json).

## Integration still required

1. **Owned compiler state and execution.** Route TeX/Lua/font-library allocations
   and mutable globals into the rollback domain; include allocator metadata,
   source origins, garbage-collector state, and input buffers. The globals and
   `realloc` calls in `engine/origins.c` are one concrete example of currently
   unowned state. Replace the assumption that returning from the callback resumes
   a forked stack with an explicit resumable engine entry at the safe points in
   `engine/patch.py`. Copying memory alone does not restore a C stack or Windows
   fiber. Arbitrary native Lua modules need an explicit state contract.
2. **File and resource rollback.** Replace `prototype/snapshot.c`'s POSIX file
   descriptors, process snapshots, stop/continue signals, Unix sockets and memfd
   output. Restore logical input positions and output prefixes, including deleted
   files and error recovery. Adapt font-bundle export, which also forks today.
3. **Native worker and distribution.** Build the patched LuaHBTeX and renderer for
   Windows; port process launch/cancellation, cache locks, path/Unicode handling,
   and native TeX Live discovery in `native/compiler.hpp`, `cache.hpp`, and
   `distribution.hpp`. Validate formats with the bundled engine. Native installed
   TeX Live 2025 is present locally, but compatibility with the pinned 1.14 engine
   has not been established.
4. **Full correctness and latency gates.** Run the existing Chinese/math/TikZ,
   source mapping, included-file, font-resource, auxiliary-tool, error recovery
   and browser interaction suites against the real Windows engine. Compare its
   end-to-end p95 and distant-page edits with the fork backend using matching
   inputs. A pass of this memory check does not satisfy those gates.
5. **One binary and VSIX.** Prefer `bakoma-backend.exe` serving the existing JSON
   protocol, with compiler-worker mode in the same executable and statically
   linked engine/renderer dependencies. Multiple processes can run one installed
   binary. This retains crash isolation from VS Code and avoids a Node native
   addon ABI. Engine Lua helpers can be embedded resources. Distribution packages,
   fonts, bibliography tools, source distributions and license notices remain
   separate from the binary count. Verify PE imports, then teach `native/launch.js`
   and `scripts/package_extension.py` to select and validate the native artifact.

The shipping path is deliberately not switched to this checkpoint proof: it has
no compiler or preview protocol. A Windows package built from the current release
would still launch the Linux backend through WSL.
