# Incremental font resources — version 0.0.14

New fonts and glyphs can now reach the preview without typesetting the remaining
document. The renderer requests a font-only resource bundle from the paused
compiler and continues with the existing page drawing stream. LuaHBTeX remains
responsible for font encoding, embedding, subsetting, metrics and Unicode maps.
The installed LaTeX distribution continues to supply font/package files.

## Resource protocol

The C++ service keeps the page publisher's socket open while that compiler is
paused. A font miss requests the canonical font IDs referenced by the page's
`Tf` operators. The publisher forks a disposable exporter and waits for it. The
exporter creates a fresh, memory-backed PDF containing only those font objects
and their dependencies, with an empty page tree and a `BakoFonts` dictionary.
It writes no page streams, does not finish the document, and does not run further
typesetting. Font aliases at different sizes merge their used glyph sets using
the engine's existing logic.

Only the child changes the engine's PDF tables or font writer state. Its writable
log/recorder/output descriptors are redirected, and its output is a separate
memory-backed descriptor. The parent returns the bytes over the same socket and
parks again. This ties the resource reply to the paused compiler revision that
produced the page. The export has a ten-second child deadline, at most 256
requested fonts and a 32 MB bundle limit. Ordinary edits with available resources
do not fork an exporter. The Python comparison adapter retains its earlier
complete-PDF fallback protocol.

The renderer validates the requested font dictionary entries and grafts their
object graphs into its retained PDF using MuPDF. It installs a separate resource
dictionary for the affected page. Glyph coverage is tracked per refreshed page:
importing a subset on one page must not make another page's older font dictionary
appear up to date. Rollback can reuse font IDs for different families, so coverage
includes the existing font identity and glyph metadata and is replaced with each
import rather than accumulated across incompatible subsets. The requested page's
font dictionary is exported together, including already-known fonts it uses;
this first implementation does not send per-glyph binary font patches.

The renderer now loads its document seed into owned memory. MuPDF lazily reads
PDF objects, and an early compiler checkpoint can rewrite or remove the on-disk
output file. Retaining immutable seed bytes prevents those writes from damaging
the existing preview. The runtime cache fingerprint also includes the checkpoint
module, alongside the backend, engine, and Lua adapters.

## Fallback and limits

OpenType, TrueType, and ordinary mapped Type 1 fonts use the new path. Type 3
fonts, custom font attributes, unknown font resource names, rejected exports,
external graphics, changed page sizes, and new physical pages retain the normal
complete-document resource export when needed. A rejected bundle resumes the
same parent compiler; the child's changes never enter its state. Arbitrary
Lua mutation of font definitions is outside the validated cases.

Font subsets are recomputed in a disposable fork, not incrementally patched in
place. A miss still costs a fork, font writing, transfer and object import. Very
large fonts can exceed the bundle limit and fall back. Repeated imports retain
older PDF objects until a resource seed or idle convergence replaces the renderer.
The implementation requires Linux/WSL fork support and the bundled patched
LuaHBTeX 1.14. Native Windows/macOS checkpointing is unchanged.

## Reproduce

```powershell
python scripts/build_engine.py
python scripts/build_cpp.py
python scripts/check_font_resources.py
python scripts/check_cpp.py
python scripts/benchmark_preview.py --repeats 20 --output preview-latency-fonts.json
```

`fontRefreshMs` measures requesting, exporting, importing, and applying the font
bundle; `fontResourceBytes` records its size. The output stays `page-stream`.
`resourceRefreshMs` continues to identify the full-document fallback. The browser
benchmark now requires a new-font sample to stream with a font bundle; it no
longer accepts a complete-PDF export for that scenario.

## Validation and measurements

Validation passed 83 new font-resource checks, 346 C++ corpus checks, 67 engine
checkpoint checks, 13 real-browser scrolling/navigation checks, 10 viewer timing
checks, and seven mocked extension checks: 526 checks in total. The new fixtures
compare exact pixels, selection text/geometry, and token source spans for new
OpenType, TrueType and Type 1 fonts, new glyphs, reused subsets, font size aliases,
rollback to different fonts, earlier rollback, error recovery, and multiple
buffered pages. Rejected font attributes and external graphics exercise normal
finalization fallback. Late font refreshes leave the seed file unchanged and the
document unfinished. Earlier rollback checks cover the retained seed's isolation
from rewritten output files.

The 100-page corpus now streams a previously unused Chinese glyph without
finalization, with exact pixels, source regions and selection geometry. Reports:
[font-resources.json](../results/font-resources.json),
[cpp-correctness.json](../results/cpp-correctness.json),
[engine-checkpoints.json](../results/engine-checkpoints.json),
[scrolling.json](../results/scrolling.json),
[viewer-latency.json](../results/viewer-latency.json), and
[extension-live.json](../results/extension-live.json).

The final browser benchmark ran 20 samples per scenario with other project tests
and builds stopped. It uses Windows, Ubuntu-22.04 WSL and headless Chromium.

| Scenario | Median | p95 |
| --- | ---: | ---: |
| Root body | 76 ms | 77 ms |
| Late chapter | 74 ms | 88 ms |
| Typing burst, final input | 114 ms | 123 ms |
| Previously unused font | 129 ms | 139 ms |

All four scenarios passed the 150 ms p95 threshold in this local run. Every
new-font sample stayed on the page-stream path and transferred a 32,525-byte
font-only bundle; median font refresh was 27 ms. The prior v0.0.13 run recorded
237 ms median / 315 ms p95 for new fonts, including 80 ms median full-resource
refresh. Ordinary edits were also faster in this run, so differences between
these separate runs must not all be attributed to font streaming. This is not
a controlled cross-version speedup or a guarantee for other machines/documents.
The full report, including timings and source/runtime hashes, is
[preview-latency-fonts.json](../results/preview-latency-fonts.json).

As before, the endpoint is decoded image and installed text followed by two
animation frames, not physical display latency. Twenty bursts contain 160 input
events: 20 final inputs painted current output and 140 were superseded. Real
VS Code host latency remains unmeasured, and native Windows/macOS engines remain
unsupported. The v0.0.14 VSIX is packaged and byte-verified locally; it has not
been installed into a running editor. Its manifest and hashes are recorded in
[package-0.0.14.json](../results/package-0.0.14.json).
