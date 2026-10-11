# C++ backend — 2026-10-11

Prototype 0.0.5 runs source instrumentation, compiler control, page-buffer
reception, MuPDF rendering, glyph geometry, and frame serialization in a
persistent C++17 process. It is the default for both VS Code and the Node browser
demo. The interactive path no longer invokes Python. Build and comparison tools
still use Python. The underlying compiler remains LuaHBTeX with the existing C
checkpoint adapter.

The next integration step is implemented: compiler page buffers arrive directly
in the process that owns retained rendering resources and source spans. This
removes the Python worker bridge and Python glyph-object allocation. It does not
add engine-managed state deltas or arbitrary source-position rollback. See
[the architecture decision](adr/0003-native-preview-backend.md).

## Measurements

Both backends used the same Node HTTP adapter, Chromium harness, 100-page corpus,
and 36 ordinary text/math edits at pages 100, 50, and 1. Runs were sequential on
this shared Windows/WSL machine. These are a small paired workload comparison,
not a performance guarantee. Environment and final implementation hashes are in
[cpp-environment.json](../results/cpp-environment.json).

| Measurement | Python stream | C++ |
|---|---:|---:|
| Input-to-visible median | 189 ms | 154.5 ms |
| Input-to-visible p95 | 279 ms | 206 ms |
| Input-to-visible mean | 198.4 ms | 158.8 ms |
| Backend pipeline mean | 129.7 ms | 92.9 ms |
| Compiler interval mean | 90.6 ms | 74.6 ms |
| Render/extraction/PNG mean | 24.4 ms | 15.3 ms |
| Source mapping mean | 7.60 ms | 0.75 ms |
| Visible time beyond backend pipeline, mean | 68.7 ms | 65.9 ms |

**The p95 <150 ms target still fails.** Median improved about 18%, p95 about
26%, and backend pipeline mean about 28%. Compiler algorithms did not change in
this migration; the observed compiler interval also depends on system load and
receipt scheduling, so its difference should not be attributed wholly to C++.
Timing uses decoded images, installed text layers, and two animation-frame
callbacks, not a physical display measurement. Substage means do not add to
percentiles and omit small preparation/serialization gaps.

Within C++ compilation, measured means were 15.2 ms for fork, 1.1 ms for restore,
47.7 ms for typesetting, and 9.5 ms for shipout/publication. Within rendering,
display-list construction took 0.49 ms, rasterization 1.62 ms, origin extraction
1.27 ms, selection text 0.71 ms, and PNG encoding 11.08 ms. Source mapping and
glyph extraction have become small; compiler work, PNG, and delivery/display are
the remaining substantial costs.

Immediate adjacent-page navigation measured 199 ms; jumping to page 100 before
convergence measured 7,671 ms. Sequential replay of invalidated later pages
remains a limitation. In the final interaction check, editing page 100 after
convergence resumed checkpoint 100 and displayed in 166 ms. Sustained input
produced 20 frames in 2.65 seconds (7.54 updates/s), with a 212 ms longest visible
freeze; scroll position remained stable and the preview caret returned.

Raw comparison: [Python](../results/cpp-python-baseline.json),
[C++](../results/cpp-latency.json), and
[final interaction check](../results/cpp-browser.json). The latency run preceded
the final child-descriptor isolation fix; that fix changes compiler launch and
recovery, not the ordinary-edit pipeline measured here.

## Validation

- 104 source-instrumentation comparisons passed, including every corpus file,
  Unicode/UTF-16 columns, macros, CRLF, and replacement of an edited file.
- 343 differential assertions passed: all 100 pages have exact matching RGB
  pixels, source regions, and selection geometry; edit cases include text,
  math, transformed/colored TikZ, new Chinese glyph resources, cached follow-up
  edits, invalid-input recovery, reflow, and adjacent-page continuation.
- The final Chromium run passed 15 interaction checks, including repeated math
  symbols, fraction/subscript navigation, Chinese text, rotated TikZ text,
  macro-origin fallback, selection, stale/error handling, background convergence,
  and reuse of the far-page checkpoint. No browser errors were reported.

The final lifecycle check exposed an integration-specific descriptor leak:
after invalid TeX deleted its output PDF, the retained renderer still held that
inode open. A new compiler inherited the descriptor and checkpoint restoration
tried reopening the deleted pathname. Compiler launch now redirects stdin to
`/dev/null` and closes all nonstandard descriptors after installing log output.
The previously failing error-to-convergence check passes with this fix.

Results: [mapper](../results/cpp-mapper.json),
[differential checks](../results/cpp-correctness.json).

## Reproduction and scope

Close C++ previews before rebuilding on Windows. The build downloads pinned,
checksum-verified MuPDF 1.26.12 and nlohmann JSON dependencies. WSL requires G++,
GCC, libdeflate/zlib development packages, LuaHBTeX 1.14, CTeX, TikZ, and Fandol.
The VSIX includes the Linux x86-64 runtime and MuPDF notices. See
[third-party dependencies](../native/THIRD_PARTY.md).

```powershell
python scripts/build_cpp.py
python scripts/check_cpp_mapper.py
python scripts/check_cpp.py
node native/demo.js --port 8765
# In another terminal:
python scripts/check_browser.py http://127.0.0.1:8765
python scripts/benchmark_browser.py http://127.0.0.1:8765 --output cpp-latency.json --assert-target
# Separately, for the same-transport Python comparison:
node native/demo.js --engine stream --port 8766
python scripts/benchmark_browser.py http://127.0.0.1:8766 --output cpp-python-baseline.json
```

The target assertion intentionally fails while p95 exceeds 150 ms. Comparison
tests require the Python packages in `requirements.txt` and Playwright/Chromium.

Windows still launches Linux C++ through Ubuntu-22.04 WSL. Native Windows and
macOS snapshots, BaKoMa-style internal differential compiler state, fine-grained
rollback, and general LaTeX provenance remain unimplemented. Full PDFs still seed
resources at initialization, convergence, and resource misses. Ordinary edits
use in-memory page commands; auxiliary files and metadata still use the session
directory. The bounded corpus compatibility limits remain those in the README.
