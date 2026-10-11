# Internal compiler snapshots — prototype 0.0.6

**Historical record: this mode has been removed. Fork checkpoints are the only supported implementation.**

The new C++ snapshot runtime retains one LuaHBTeX process and restores its
compiler memory, Lua state, execution continuation, file positions, and output
prefixes from in-memory undo records. It does not fork at checkpoint capture or
on edits. The controller, renderer and source-mapping protocol remain compatible
with the existing C++ backend.

This implements the retained-execution and differential-state mechanisms found
in the BaKoMa investigation. It is **not a reconstruction of BaKoMa's private
snapshot format or a portable TeX-object serializer**. The rollback domain is
the pinned compiler's writable process memory, including its allocator and Lua
VM. Read the [architecture decision](adr/0004-internal-compiler-snapshots.md) for
the storage format, excluded control stack, file recovery and platform contract.

## Delivery decision

**Internal snapshots are experimental and opt-in. Fork remains the default.**
Correctness checks pass, and ordinary repeated edits improve. However, restoring
a boundary far behind the current state regresses tail latency. Making this mode
the default would worsen the stated p95 goal.

```powershell
python scripts/build_cpp.py
node native/demo.js --checkpoint internal --port 8792
# Comparison, in a separate terminal:
node native/demo.js --checkpoint fork --port 8793
```

In VS Code, install `artifacts/bakoma-revived-prototype-0.0.6.vsix`, keep
`bakoma.engine` set to `cpp`, and set `bakoma.checkpointMode` to `internal`.
Close existing previews before changing modes or rebuilding. Windows still
uses Ubuntu-22.04 WSL; this does not add native Windows checkpoints.

## Same-harness measurements

Sequential runs used the same Node adapter, Chromium harness, 100-page corpus,
and 36 text/math edits at pages 100, 50, and 1. Internal ran first, then fork.
Other shared-machine activity can influence the results; this is one workload
comparison, not a latency guarantee.

| Measurement | Fork checkpoints | Internal snapshots |
|---|---:|---:|
| Input-to-visible median | 155 ms | 137.5 ms |
| Input-to-visible p95 | 185 ms | 325 ms |
| Input-to-visible mean | 157.8 ms | 154.5 ms |
| Compiler interval mean | 74.8 ms | 65.3 ms |
| Render/extraction/PNG mean | 15.7 ms | 15.1 ms |
| Source-mapping mean | 0.70 ms | 0.73 ms |
| Request-to-payload mean | 101.7 ms | 90.1 ms |
| Fork interval mean | 14.25 ms | 0 ms |
| Restore interval mean, all edits | 1.03 ms | 24.45 ms |

The internal median is about 11% lower. The **150 ms p95 target still fails**,
and p95 is worse than fork. The first internal rollback from page 100 to page 50
displayed in 389 ms; the subsequent jump to page 1 took 325 ms. Their restore
intervals were 230 and 181 ms, respectively. They restored about 170 MB and
135 MB of distinct undo bytes even after eliminating repeated intermediate
copies. The same-boundary restore mean, excluding the first edit at each page,
was 13.7 ms. Reporting only that warm subset would hide the regression.

Compiler stage labels include allocation, copy-on-write/dirty-page faults, and
scheduling. The lower measured typesetting interval does not establish a new
TeX layout algorithm. Browser timing ends after image decoding, text-layer
installation, and two animation-frame callbacks; it is not a physical display
measurement. Stage means do not add to percentiles.

Raw results: [internal](../results/internal-latency.json),
[fork](../results/internal-fork-baseline.json), and
[environment/source hashes](../results/internal-environment.json).
Timing runs preceded the final append/close-on-exec descriptor-flag restoration
fix; the added append-file regression checks validate that fix. The compiler
memory algorithm measured here is unchanged.

A separate interaction check produced 20 frames in 2.536 seconds (7.89 updates/s)
with a 169 ms longest visible freeze, stable scrolling and restored preview
caret. After idle convergence, editing page 100 resumed checkpoint 100 and
displayed in 169 ms. This correctness run is separate from the paired benchmark.

## Memory and correctness

The measured internal session retained 100 snapshots in one compiler PID, with
no checkpoint children. A post-convergence observation measured about 1,625 MiB
compiler PSS. The fork session's 100 retained compiler processes summed to about
1,675 MiB PSS. These are contextual observations after different interaction
histories, not a controlled memory-savings claim. The internal benchmark retained
about 543 MB of shadow address coverage and 622 MB of undo records before
invalidation. Virtual reservation is larger than resident memory. Raw
[memory observations](../results/internal-memory.json) exclude the C++ renderer
and browser.

Validation passed:

- **343 differential assertions**: exact RGB pixels, glyph/source regions and
  selection geometry on all 100 pages; ordinary text and math edits; transformed
  and colored TikZ; new font-glyph resource refresh; error recovery; reflow; and
  adjacent-page continuation. [Results](../results/internal-correctness.json).
- **118 internal-state checks**: repeated rollback through forced Lua garbage
  collection and global TeX register updates, output-file rewinding and append
  descriptor semantics, bounded
  journal use, identical compiler PID, no checkpoint children, prompt recovery
  from invalid TeX and `os.exit`, upstream changes, and reuse of a rebuilt later
  checkpoint against a full-build reference.
  [Results](../results/internal-state-correctness.json).
- **15 Chromium interaction checks**, including math reverse navigation,
  selection/caret behavior, stale/error handling, continuous input, convergence
  and far-page checkpoint reuse. No browser errors.
  [Results](../results/internal-browser.json).

The runtime source passes G++ warning checks; Python and JavaScript syntax checks
also pass. The compiler runtime uses no libc allocation/stdio calls on its
isolated control stack. Error shutdown is distinguished from successful PDF
completion before parking, so a failed TeX run does not wait for a nonexistent
complete PDF.

```powershell
python scripts/check_cpp.py --checkpoint internal
python scripts/check_internal_snapshot.py
python scripts/check_browser.py http://127.0.0.1:8792
python scripts/benchmark_browser.py http://127.0.0.1:8792 --output internal-latency.json
python scripts/benchmark_browser.py http://127.0.0.1:8793 --output internal-fork-baseline.json
```

## Remaining work

The next performance problem is the large memory rollback when switching to an
earlier boundary. A narrower engine/allocator state domain or an indexed lazy
restoration scheme needs its own correctness proof; removing the fork alone does
not solve it. Internal snapshots still require explicit corpus input boundaries,
Linux x86-64, a single compiler thread, and controlled file I/O. Arbitrary native
Lua modules, external effects, arbitrary paragraph rollback, equivalent-suffix
detection, and native Windows/macOS snapshots are not implemented. Complete PDFs
still seed resources at initialization, convergence and resource misses.
