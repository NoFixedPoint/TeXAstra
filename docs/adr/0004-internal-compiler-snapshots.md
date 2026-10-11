# Differential snapshots inside the retained compiler

Version 0.0.6 adds an alternative to the fork-per-checkpoint mechanism: a C++
snapshot runtime loaded into the pinned Linux LuaHBTeX process. The compiler
keeps one PID while edits restore an earlier state and resume execution. The
existing fork adapter remains the default: internal snapshots improve the median
but regress p95 when rolling back across many retained boundaries. Users can
select `internal` explicitly while this tradeoff is addressed.

The BaKoMa investigation established retained compiler execution, internal state
records and difference encoding. It did not establish its complete state schema
or snapshot format. This implementation adopts those mechanisms without copying
BaKoMa code or claiming an identical implementation.

## State ownership

`native/internal_snapshot.cpp` owns a control stack, saved register contexts,
descriptor records, a shadow image, and an undo journal in a separate virtual
memory reservation. Compiler writable memory includes TeX globals and arrays,
Lua/package objects, native-library globals, the C allocator and the compiler
stack. Read-only code and resources stay in place. The control runtime is
excluded from restoration and uses direct system calls on its control stack:
calling the libc allocator or stdio while restoring libc would corrupt state.

Snapshots are taken at the existing explicit input boundaries, after flushing
stdio. Linux soft-dirty bits identify candidate changed pages; comparison with
the shadow image retains runs of changed 16-byte blocks. Densely changed pages
use whole-page undo records. An untouched region has one shadow image rather
than one copy per checkpoint. Snapshot registers include the continuation,
callee-saved integer registers, and floating-point state.

Rollback first discards writes since the latest boundary. It then walks the
retained undo interval from the requested boundary forward, taking the earliest
saved value for each changed block. Each affected compiler page is installed
once. Later checkpoints and their file handles are invalidated, obsolete journal
pages are released, file positions/output prefixes are restored, and execution
returns from the saved checkpoint callback. This avoids replaying every
intermediate memory image and does not fork a replacement compiler.

Output descriptors retain read-only handles to their original inodes. A restore
can therefore recover an output prefix even when a TeX error removed its file.
Interactive PDF drawing output resumes into a memfd; complete PDF export remains
the resource-seed fallback. Successful completion and recoverable errors park the
compiler, allowing another edit to restore it. A hard process crash still
requires a rebuild.

The malloc configuration reserves spare heap address space, disables large
malloc allocations through independent mmap regions, and disables heap trimming.
This stabilizes allocation addresses and avoids marking the whole heap newly
dirty on each small growth. Unpopulated heap pages remain lazy in the shadow;
swapped pages and file-backed data are copied.

## Boundary and tradeoff

This is **in-process compiler-memory rollback**, not a serializer with explicit
TeX-array/Lua-object schemas. It is a step toward the engine-managed architecture,
but it is still coupled to Linux process memory and allocator behavior. It does
not make checkpoints portable to native Windows, provide arbitrary paragraph
checkpoints, detect equivalent suffix state, or support arbitrary native Lua
modules/external side effects.

The supported proof remains the trusted, single-threaded LuaHBTeX 1.14 corpus on
Linux x86-64 (Windows through WSL). The runtime rejects nonregular compiler
descriptors at checkpoint boundaries and writable outputs outside the generated
session. Additional threads, changes to memory mappings by native modules,
shared writable mappings, subprocess/network state, and destructive external I/O
are outside this adapter's contract. The snapshot address budget is 2 GiB of
tracked writable compiler pages and 9 GiB of undo records, within a 12 GiB virtual
reservation; actual resident memory depends on the document and edit history.
The fixture supports up to 102 retained boundary records and 64 regular open
compiler descriptors per boundary. These are explicit prototype bounds.

The fork backend remains available through `--checkpoint fork` in the Node demo,
`--checkpoint fork` in the native executable, or `bakoma.checkpointMode` in VS
Code. A separate process still handles idle full-document convergence.

## Platform references

Linux documents the dirty-bit protocol and the fact that expanded mappings are
marked dirty in [Soft-Dirty PTEs](https://docs.kernel.org/admin-guide/mm/soft-dirty.html).
The allocator controls are documented in
[mallopt(3)](https://man7.org/linux/man-pages/man3/mallopt.3.html).
These explain the platform mechanism; corpus differential tests establish this
adapter's narrower correctness evidence.
