# Compiler and renderer optimization — prototype 0.0.4

This update reduces ordinary edit latency further, but does not implement all of
BaKoMa's architecture. The measured 150 ms p95 gate still fails.

## What changed

- Preserve MuPDF's font/glyph store across content updates. The installed
  PyMuPDF 1.26.7 implementation of `Document.reload_page()` calls
  `TOOLS.store_shrink(100)`. Calling it after every `update_stream()` defeated
  our persistent renderer's cache. The adapter now replaces only the validated
  content stream and builds a fresh display list. Resource or dimension changes
  still take the complete-seed path. No previous edit's display list is reused.
- Use the same display list for rasterization and selection-text extraction.
  Source origins continue to use the actual glyph trace and explicit source IDs.
- Use [python-zlib-ng](https://github.com/pycompression/python-zlib-ng) for
  lossless PNG compression, with a standard-library fallback. On one real page's
  scanlines, isolated compression fell from about 11.1 to 3.5 ms; compressed size
  rose from 234,236 to 335,458 bytes. End-to-end measurements include this larger
  payload. Neither image resolution nor RGB precision is reduced.
- Build font/glyph coverage once per distinct font/character on each shipped
  page, instead of rebuilding an identical signature for every occurrence.
  The per-page set is reset before each page, including reflowed pages.
- Replace the previous compiler child with `SIGKILL`, which also terminates a
  suspended publisher, and reap it in the checkpoint parent after forking the new
  child. Kernel teardown can overlap new typesetting; discarded TeX code cannot
  continue against restored session files. The earlier synchronous child wait
  measured about 8 ms on average in a diagnostic run.
- Assign source attributes through TeX's `attributedef` control sequence,
  shortening repeated input without changing source IDs or mapping semantics.
- Expose `compilerStagesMs` and `renderStagesMs` through the browser measurements.
  `scripts/profile_pipeline.py` isolates the backend and also measures Python GC
  pauses. Timings remain diagnostic, not separate latency promises.

## Browser comparison

The same harness drove 36 ordinary text/math edits on pages 100, 50, and 1 of the
100-page corpus, first before these changes and then after. Runs were sequential
on the same shared machine; other machine activity and run order can influence
the results. These are new samples, not a comparison with historical 0.0.3 runs.

| Measurement | Before | After |
|---|---:|---:|
| Median edit to preview | 187.5 ms | 155.5 ms |
| p95 edit to preview | 272 ms | 251 ms |
| Mean edit to preview | 192.4 ms | 175.1 ms |
| Mean compiler/page stage | 79.9 ms | 69.9 ms |
| Mean rendering stage | 36.9 ms | 25.3 ms |
| Median rendering stage | 29.1 ms | 17.7 ms |
| Mean backend pipeline | 133.0 ms | 113.7 ms |

Median visible latency improved about 17%, p95 about 8%, and mean rendering
about 32%. The target assertion still fails at 251 ms. Raw results are
[before](../results/compiler-render-before.json) and
[after](../results/compiler-render-after.json).

After-change mean compiler subintervals were: child replacement 0.02 ms,
fork/scheduling 12.66 ms, descriptor restoration 0.88 ms, execution up to the
shipout callback 44.83 ms, and shipout/publication preparation 9.25 ms.
The last two include provenance work; they are not measurements of bare TeX
layout alone. Worker receipt/parsing and scheduling account for the remaining
time in the broader compiler stage. For multi-page reflow the timing callback
describes the last shipped page, so these subdivisions apply to the ordinary
single-page samples above.

Mean rendering subdivisions were: page access 0.10 ms, display-list creation
0.74 ms, rasterization 1.69 ms, origin extraction 8.35 ms, selection text 5.74 ms,
and PNG preparation/encoding 8.53 ms. Allocation and garbage collection can occur
inside these stages. A separate replay captured a 28.5 ms generation-2 Python
collection inside text extraction; the stage label alone does not attribute that
spike to MuPDF. No global GC disabling or deferred-collection trick is applied.

## How much of BaKoMa is implemented?

The [binary findings](bakoma-binary-pipeline.md) distinguish observed mechanisms
from guesses about undocumented scheduling policy.

| Mechanism | Current implementation |
|---|---|
| Retain compiler state and resume near an edit | Yes, process snapshots at explicit corpus input boundaries |
| Publish live page commands in memory | Yes, PDF drawing commands through a memory descriptor/socket |
| Stop after requested pages and continue on demand | Yes, within the corpus checkpoint model |
| Retain renderer font/glyph resources | Yes; this change removes the accidental cache flush |
| Engine-managed differential snapshots | No; still POSIX `fork`, not compact TeX-aware state deltas |
| Fine source-position checkpoints | No; no arbitrary paragraph/line rollback |
| Native compiler/viewer calls in one process | No; Windows/WSL worker and browser transport remain |
| Native viewer/page/graphics caches | Only MuPDF resource caching; no equivalent complete native viewer or page/graphics cache policy |
| Engine-integrated arbitrary-source provenance | No; the existing bounded source instrumenter remains |
| Independent live DVI output, PDF only for export | No; complete PDFs still seed resources and convergence |

State-equivalence detection for reusing an unchanged suffix was not established
by the BaKoMa inspection and must not be treated as a confirmed missing trick.
Native Windows checkpoints remain unimplemented. Fork cost, the roughly 45 ms
execution interval, Python allocation pauses, and browser delivery are remaining
optimization targets.

## Validation and reproduction

`scripts/check_renderer.py` compares alternating translated content against a
fresh renderer and checks exact pixels, selection text/geometry, RGB colors,
and both PNG compressor paths. The expanded `scripts/check_page_stream.py`
compares the 100-page seed with an uninstrumented full build, validates shared
display-list selection extraction, and covers text, math, rotation, colored TikZ,
new Chinese glyph resources, error recovery, and reflow against complete builds.
The browser harness checks real selection, navigation, continuous typing, and
convergence. Results are recorded alongside the benchmarks.

Final validation passed **39 compiler/stream assertions, 7 renderer checks, and
15 browser interaction checks**, with no browser JavaScript errors. The browser
interaction run overlapped differential compilation and is used for correctness,
not for the latency comparison above. Python compilation and JavaScript syntax
checks also passed.

```powershell
python -m pip install -r requirements.txt
python scripts/check_renderer.py
python scripts/check_page_stream.py
python scripts/profile_pipeline.py
python -m prototype.demo --engine stream --port 8765
# Separate terminal:
python scripts/check_browser.py http://127.0.0.1:8765
python scripts/benchmark_browser.py http://127.0.0.1:8765 --assert-target
```

The last command remains expected to fail the 150 ms gate on this machine.
