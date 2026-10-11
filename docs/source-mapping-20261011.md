# Source navigation coverage — version 0.0.15

Source navigation now survives individual glyph/provenance mismatches. Fraction
bars, radical bars, overlines and underlines with retained origins are clickable;
they select the originating command token. Clicking unmapped output explains why
the preview cannot select its source, while surrounding verified text continues
to work. Text copying remains independent of these navigation regions.

## Independent output markers

The C++ preview enables `BAKO_SOURCE_MARKERS`. At final shipout,
`prototype/provenance.lua` surrounds each glyph node and each supported rule node
with a versioned `BakoSource` PDF marked-content scope. A glyph marker contains
its source ID and expected physical glyph count, including virtual-font draws.
The existing sidecar remains available to comparison tools and forward-page
lookup. Rule origins also enter that page index.

The engine adds a private Lua PDF-literal mode, 6, for these markers. It closes
and reopens an active PDF text array without resetting the text matrix or the
engine's cumulative positioning/rounding state. Ordinary direct literals reset
that state and introduce small rendering differences; this mode preserves the
exact reference pixels and text geometry. It is private to our patched engine,
not an extension expected from an installed LaTeX distribution.

`native/mapping.hpp` tracks marker scopes while the pinned MuPDF run processor
traces the actual page operators. Pending text is flushed before scope changes.
Glyph counts are checked per node instead of pairing two page-wide lists. A
mismatched node produces unmapped rectangles; the next marker independently
establishes its source ID. Untagged draws, missing origins and unknown source IDs
also remain unmapped. Imported form content cannot inherit surrounding TeX
origins. The ordinary display list still supplies pixels and copied text.

Fraction and radical rules already inherit engine origins. The engine patch
also preserves the overline command's origin on its bar, instead of inheriting
the argument's first token. Rule paths produce transformed quadrilaterals as
well as bounding rectangles. The viewer uses the quadrilateral and a one-point
click tolerance, so a rotated fraction bar does not claim its entire bounding
box or take clicks intended for the numerator.

## Diagnostics and navigation

Frames add `unmappedRegions`, each containing a rectangle and a reason:

| Reason | Meaning |
| --- | --- |
| `glyph-count-mismatch` | The node's physical output differs from its marker. |
| `missing-origin` | The compiler retained no source ID for the generated output. |
| `untagged-content` | Output has no source marker. |
| `unknown-source` | An ID cannot be resolved in the current source index. |
| `external-content` | Imported PDF/form text has no verified TeX-token origin. |
| `unclosed-source-scope` | A marker scope did not close. |

Count mismatches, unknown IDs and unclosed scopes also produce summary warnings.
Ordinary generated page numbers may lack origins without making the page
erroneous. Clicking an unmapped region shows a plain-language explanation and
does not navigate to a neighboring token. Stale revisions still cannot navigate.
Unclosed scopes conservatively invalidate the output within their unclosed
extent; arbitrary malformed PDF content is not automatically repaired.

The named `regionFields` schema adds an optional `quad` column (null for glyphs).
Rules use `kind: rule-origin`; their existing file, offset and editor-position
fields refer to the command token, including a calling macro where appropriate.
Rules add no characters to the selection layer. Ligatures continue to use their
retained leading-token origin rather than inventing a multi-token source span.

## Validation

The engine and C++ runtime were rebuilt. Applying `engine/patch.py` to pristine
pinned engine sources and applying it a second time produced identical files.

994 checks passed:

- [Source mapping](../results/source-mapping.json): 167 checks for nested and
  reordered macros, ordinary and virtual-font ligatures, discretionary and
  automatic hyphenation, nested fractions, radicals, overlines, underlines,
  generated expressions, rotated/scaled rules and TikZ text, imported PDF text,
  Lua glyphs without origins, localized marker faults, forward navigation,
  checkpoint rollback and unchanged project sources. Pixels and selectable text
  are compared with ordinary full LuaLaTeX.
- [Browser mapping](../results/mapping-browser.json): 32 real Chromium checks
  against compiler-produced frames, including expression selection, rotated-rule
  hit testing, neighboring text, explanations, and stale-navigation guards. The
  VS Code message transport is mocked.
- [C++ corpus](../results/cpp-correctness.json): 346 checks, including exact pixels,
  glyph source regions and selectable text across 100 pages, resource refresh,
  error recovery and reflow. Its older glyph-only oracle excludes the new rule
  regions, which the source-mapping and browser suites validate separately.
- [Token origins](../results/token-origins.json): 80 checks.
- [Font resources](../results/font-resources.json): 83 checks.
- [Engine checkpoints](../results/engine-checkpoints.json): 67 checks.
- [Included edits](../results/included-edits.json): 189 checks.
- [Scrolling](../results/scrolling.json): 13 real-browser checks.
- [Viewer timing](../results/viewer-latency.json): 10 checks.
- [Extension](../results/extension-live.json): seven mocked-host checks.

Reproduce the new checks with:

```powershell
python scripts/build_engine.py
python scripts/build_cpp.py
python scripts/check_source_mapping.py
python scripts/check_mapping_browser.py
python scripts/benchmark_preview.py --repeats 20 --output preview-latency-mapping.json
```

## Remaining limits

The isolated [browser benchmark](../results/preview-latency-mapping.json) ran
20 samples per scenario with other project tests and builds stopped:

| Scenario | Median | p95 |
| --- | ---: | ---: |
| Root body | 76 ms | 91 ms |
| Late chapter | 91 ms | 105 ms |
| Typing burst, final input | 149 ms | 152 ms |
| Previously unused font | 141 ms | 158 ms |

The typing and new-font scenarios exceed the 150 ms target, unlike the earlier
v0.0.14 measurement. All new-font samples still used font bundles and page
streaming. These separate runs are not a controlled estimate of marker overhead;
system scheduling and transport contribute to the measured change. The endpoint
remains decoded image, installed text and two animation frames. The report
separates superseded typing inputs and records source/runtime hashes.

Markers add PDF bytes, shipout nodes and renderer interpretation work. This is
not a promise that navigation is free or every Lua/package transformation is
supported. Arbitrary Lua mutation that supplies a plausible but wrong source ID
cannot be detected from glyph counts alone. Imported text, generated output
without retained origins, arbitrary graphics paths and unsupported node
transformations may remain unmapped. Their presence no longer shifts ordinary
body-text mappings. Linux/WSL and the bundled patched LuaHBTeX remain required;
packages and fonts still come from the user's installed TeX distribution.

The v0.0.15 VSIX is locally packaged and byte-verified, not installed into a
running editor. See [the package manifest](../results/package-0.0.15.json).
Actual VS Code host interaction and physical display latency remain unmeasured.
