# Engine token tracking — version 0.0.10

The live preview now uses a bundled, patched LuaHBTeX compiler to track source
tokens. The production handwritten LaTeX source rewriter and its comparison
test have been removed. Fork checkpoints are the only supported mode; stale
`bakoma.checkpointMode` settings are ignored by the extension.

The engine patch preserves token values and TeX execution. It adds origin
metadata to scanner results, token storage, macro arguments and node creation.
Generated macro content selects the originating command token, while argument
glyphs select their own tokens. See [ADR 0006](adr/0006-engine-token-origins.md)
for the ownership model and remaining limits.

Validation records:

- [Token-origin regressions](../results/token-origins.json): 80 checks of exact output and
  glyph-position checks for cases the old rewriter could not map precisely.
- [Syntax comparisons](../results/live-syntax.json): 15 earlier compatibility
  cases remain pixel-identical to ordinary LuaLaTeX, including live edits.
- [100-page corpus](../results/cpp-correctness.json): 344 pixel, source-region,
  selection, checkpoint, error-recovery, resource-refresh and reflow checks.
- [101-page manuscript](../results/token-project.json): every page matches plain
  LuaLaTeX, every page has mappings, live edits reuse checkpoint 50, and all 156
  original files remain unchanged.
- [12-page project](../results/token-fixture.json): live edits, navigation and
  cache reuse through the general-project path.

The manuscript validation recorded backend edit times of approximately 230–268
ms. These were correctness runs with other work on the machine, not a controlled
latency benchmark or end-to-end p95 measurement. The 150 ms target remains open.

Build the compiler with `python scripts/build_engine.py`, then the controller
with `python scripts/build_cpp.py`. Packaged extensions include both binaries.
The initial compiler build needs the existing C/C++ toolchain plus Linux
development headers for HarfBuzz, zziplib, libpng, zlib, Graphite2 and GMP/MPFR.
Source builds and logs are cached in `~/.cache/bakoma-engine` inside WSL.

The source archives included with the runtime, `engine/patch.py`, and
`scripts/build_engine.py` provide the corresponding compiler source and build
instructions. The upstream engine remains responsible for macro expansion,
typesetting and page layout; this project maintains its provenance patch.
