# Native Windows retained compiler checkpoints

Research date: 2026-10-11. This is a feasibility assessment, not evidence that a
Windows compiler or its latency target has been implemented. The requirement is
to preserve incremental compilation performance; recompiling the full document
on every edit does not meet it.

## Recommendation

Build a native compiler with explicitly owned mutable state and resumable engine
safe points. Use supported Windows virtual-memory APIs to version that state,
with file and resource rollback managed separately. Retain the existing Linux
fork implementation as the correctness and performance reference while developing
the Windows implementation. A Windows executable serving the existing protocol
is a practical first packaging target; a DLL is a subsequent integration choice,
not a solution to checkpointing.

There is no documented drop-in executable `fork()` equivalent in the Windows
APIs reviewed here. PSS offers efficient memory capture, but its public contract
does not offer restoration or execution of a captured continuation. Cygwin offers
fork compatibility with copying costs and another runtime DLL. Fibers offer
suspension and resumption of a live execution, not arbitrary historical rewind.
These conclusions follow from the API contracts below, rather than a claim that
all possible undocumented Windows mechanisms have been exhausted.

## Existing project evidence

The current engine retains interpreter checkpoints with input read frontiers,
including inside included files. Changes cannot merely restart at an arbitrary
paragraph: already scanned macro arguments, buffered input, groups and output
routines constrain valid resume points. The Windows implementation must preserve
these semantics. See [engine checkpoints](engine-checkpoints-20261011.md) and
[ADR 0008](adr/0008-engine-checkpoints.md).

The removed Linux internal snapshot implementation already demonstrated a
correctness-preserving but slower-tail alternative. In its paired historical
100-page run, fork input-to-visible p95 was 185 ms and internal snapshots were
325 ms. Large backwards jumps restored roughly 135–170 MB and took 181–230 ms
in the restore stage. Moving that mechanism to Windows does not establish
performance parity. See the measurements and caveats in
[internal snapshots](internal-snapshots-20261011.md) and the state-ownership
description in [ADR 0004](adr/0004-internal-compiler-snapshots.md).

## Mechanism comparison

| Mechanism | Documented capability | Missing requirement | Assessment |
| --- | --- | --- | --- |
| PSS VA clone | Efficient address-space capture and query | Supported execution/restore operation, external-state rollback | Useful research building block; not an executable fork replacement |
| `MEM_WRITE_WATCH` arena | Identify pages written since reset | Previous bytes, historical versions, continuation, I/O state | Suitable dirty tracking after allocator/state isolation |
| `VirtualProtect` plus VEH | Protection faults handled before stack unwinding | Version storage, fault discipline, complete ownership | Candidate first-write undo or lazy restore implementation |
| Fibers | Cooperatively suspend/resume stack and saved registers | Clone/rewind API and historical heap/global state | Scheduling aid, not a complete checkpoint mechanism |
| Cygwin fork | POSIX compatibility using process creation and copying | COW economics and single runtime binary | Possible compatibility experiment; parity cannot be assumed |

The assessments in this table are engineering inferences. The documented
capabilities and their sources follow.

## PSS is a capture interface

Microsoft describes Process Snapshotting as capturing data for diagnostics. Its
overview documents capture, query and walk operations. Its portal explicitly
states that efficient virtual-address capture uses Windows' internal POSIX fork
clone capability. This supports using PSS for snapshot storage; it does not
document a public executable fork contract. Sources:
[PSS overview](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/proc_snap/overview-of-process-snapshotting)
and [PSS portal](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/proc_snap/process-snapshotting-portal).

`PSS_CAPTURE_VA_CLONE` includes private memory and shareable mapped/image
sections. Thread-related flags capture thread IDs and context records. Capturing
those records does not mean PSS has created resumable threads. The API can expose
a VA-clone process handle, but that handle alone provides no documented promise
that the clone can execute the application. Sources:
[capture flags](https://learn.microsoft.com/en-us/windows/win32/api/processsnapshot/ne-processsnapshot-pss_capture_flags)
and [VA clone information](https://learn.microsoft.com/en-us/windows/win32/api/processsnapshot/ns-processsnapshot-pss_va_clone_information).

Inference: do not ship a path that injects a new thread into a PSS clone and calls
it supported checkpoint restoration. Such a path needs independent proof for the
Windows loader, CRT, synchronization and handle state, as well as an API support
contract. A failed experiment cannot be repaired by treating captured thread
contexts as runnable threads.

A narrower experiment could use a PSS clone as an immutable source from which
the application restores selected owned memory. That still requires a complete
ownership map and a resumable engine. It also needs benchmarks: capture cost,
retained clone overhead, page retrieval, memory pressure, and long-distance
rollback. It is not an already validated alternative to the arena design.

## Dirty tracking and undo storage

`MEM_WRITE_WATCH` must be requested when reserving an allocation with
`VirtualAlloc`. `GetWriteWatch` returns addresses of written pages and their
granularity; it does not return the contents before a write. Reset must be atomic
with observation or coordinated so writes cannot be lost between querying and
resetting. Sources:
[VirtualAlloc](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc)
and [GetWriteWatch](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-getwritewatch).

Inference: write-watch cannot be added after the fact to arbitrary allocations
from the CRT, Lua, TeX, font libraries and DLLs. Route compiler allocations into
owned reservations and account explicitly for mutable globals. To build undo
history with write-watch, retain a previous shadow image and compare/copy the
reported pages at each checkpoint. This resembles the removed internal design
and therefore needs an answer to its large backwards-copy regression.

`VirtualProtect` changes committed page protections. Microsoft warns against
protecting ordinary heap blocks because multiple allocations can share a page
and the heap manager assumes writable memory. Vectored exception handlers run
before stack unwinding, after the debugger's first-chance notification. Sources:
[VirtualProtect](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect)
and [vectored exception handling](https://learn.microsoft.com/en-us/windows/win32/debug/vectored-exception-handling).

Inference: in dedicated arenas, read-only protection and a narrowly scoped
handler can preserve old bytes on the first write, then make that page writable.
Preallocate the journal and keep handler/control allocations outside the rollback
domain. Recognize only expected faults in registered regions and let unrelated
faults propagate. Handle journal exhaustion explicitly. A first-write handler
changes capture economics but does not itself eliminate the cost of restoring a
large old state. An indexed or lazy page-version scheme is a separate design and
correctness problem, especially for pages passed into system calls.

## Continuations remain an engine problem

Fibers save their own stack and a subset of registers; they share their executing
thread's TLS. `CreateFiberEx` creates a new fiber at a supplied entry function
with a stack allocated by the system. The documented APIs expose scheduling and
deletion, not copying an existing fiber or restoring its historical contents.
Sources: [fibers](https://learn.microsoft.com/en-us/windows/win32/procthread/fibers)
and [CreateFiberEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createfiberex).

Inference: a control fiber is useful to keep the rollback driver off the compiler
stack, but it does not make historical compiler continuations available. Prefer
explicit engine state at safe points that can return to a stable driver entry.
If a custom stack/context snapshot is chosen instead, specify the exact compiler,
architecture and ABI contract; account for stack growth, exception/unwind state,
TLS and floating-point registers. Do not call opaque fiber-object copying a
supported Windows API technique.

## Cygwin compatibility and packaging

Cygwin's guide describes its fork as non-copy-on-write. It documents address
layout constraints and failures caused by DLL placement, ASLR and injected DLLs.
Its FAQ says an application using the Cygwin API requires `cygwin1.dll`; static
linking cannot produce an independent self-contained executable. Sources:
[process creation](https://cygwin.com/cygwin-ug-net/highlights.html)
and [Cygwin FAQ](https://cygwin.com/faq/index.html).

Inference: Cygwin could reduce the initial POSIX porting work, but each retained
checkpoint still pays copying costs. It is therefore unsuitable as an assumed
performance-equivalent replacement for Linux COW checkpoints, and requires at
least the application plus its runtime DLL. It might be evaluated if measured
latency and the extra runtime are acceptable; that acceptance is not established
by this research.

The project's package policy already sources packages, classes, fonts, formats
and auxiliary tools from an external distribution. A single shipped backend does
not remove those dependencies. Native Windows must discover and validate a
compatible native distribution and compatible format data separately. See
[distribution discovery](distribution-20261011.md). The current format and engine
compatibility restrictions remain material.

## Implementation and release gates

The following are proposed acceptance gates, not completed validation:

1. **Own all mutable compiler state.** Inventory TeX arrays/globals, Lua objects
   and allocator metadata, source tables, font/resource libraries, input state,
   output state and continuations. Keep controller, renderer and communications
   memory outside rollback. Preserve pointer validity through restores.
2. **Prove repeatable restoration.** Restore multiple old checkpoints after
   allocation/free cycles, Lua GC, included-file edits, length changes, errors,
   EOF appends and resource additions. Reuse the project's full-build pixel and
   source-span differential oracle. A memory-arena microbenchmark is insufficient.
3. **Virtualize file effects.** Restore logical read offsets with stale buffers
   discarded; restore output prefixes and reopen deleted outputs. Kernel handle
   state is not recovered merely by copying a `FILE` structure or memory arena.
4. **Measure the actual edit path.** Compare paired native Windows and Linux
   baseline runs with identical document/edit workloads. Include cold capture,
   repeated late edits, page-100-to-50-to-1 jumps, memory pressure, checkpoint
   invalidation and error recovery. Report p50/p95, worst backwards rollback,
   capture cost and committed/resident memory; do not report only warm edits.
5. **Verify the shipped artifact.** Check imported DLLs and bundled dependencies,
   launch from the VSIX on Windows without WSL, resolve the selected distribution,
   and validate path/Unicode/cancellation behavior. An isolated executable worker
   fits the existing protocol and keeps compiler failure outside the extension
   host; whether it becomes a DLL can be decided after checkpoint correctness.

No measured evidence gathered here establishes Windows incremental latency
parity. The main blocker is complete, efficiently restorable compiler state and
execution, not the extension package format.
