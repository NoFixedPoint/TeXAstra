# Live projects and continuous scrolling — version 0.0.8

**BaKoMa: Open Experimental Preview** now starts the C++/LuaHBTeX live session for
ordinary projects. Existing PDFs, `% !TEX program`, and legacy `previewMode`,
`latexCompiler` or `engine` settings do not select a reduced-feature mode.
`% !TEX root` and `bakoma.mainFile` still select the root document. Fork checkpoints
remain the default. The extension uses unsaved editor buffers without saving them.

The preview scrolls continuously through page placeholders. Nearby images and
selectable text load on demand; distant decoded pages are evicted. Clicking a
mapped glyph selects its source token or macro invocation. Source navigation can
fetch an unloaded page. Repeated headings prefer the output nearest the current
viewport. Page queries do not advance source revisions or cancel convergence.

General documents get checkpoints at safe paragraph boundaries, including inside
appendix containers. A changed paragraph resumes the earlier retained compiler
state. Long environments may require more replay; preamble and included-file
edits rebuild the live session. Complete builds still establish fonts/resources
and converge references. Newly needed resources can also require complete export.

Generated blocks, source copies, auxiliaries, logs and resource PDFs stay under
`$XDG_CACHE_HOME/bakoma-revived`, normally `~/.cache/bakoma-revived` in Ubuntu-22.04
WSL. Successful build data is reused when input hashes, runtime/compiler identity
and dependency stamps match. Reopening reconstructs process checkpoints; it does
not deserialize a compiler process saved across VS Code restarts. Concurrent
sessions use separate locked directories. There is no cache eviction UI yet.

## Validation

The read-only external manuscript produces 85 pages under LuaLaTeX. The live
rendering is compared pixel for pixel with uninstrumented LuaLaTeX, and source
ranges are checked against the original text. Tests also exercise middle-document
edits, retained checkpoints, cache reuse, and a complete before/after input hash
manifest. Aggregate results are in [live-mode.json](../results/live-mode.json);
private source and rendered manuscript pages are not included in the repository.
All 85 pages have mapped source regions, and all 653 original files retained their
hashes. The three measured edits on page 43 resumed checkpoint 43 and matched
complete LuaLaTeX builds exactly. Their backend pipelines took 181.3, 165.3 and
161.4 ms; compiler work accounted for 69.6, 62.6 and 58.8 ms respectively. These
three observations exclude browser transport/painting and do not establish p95.

The reproducible 12-page [fixture](../scripts/live_fixture.py) covers ordinary
text/math, italic punctuation, display spacing, leader dots, an unbraced macro
argument, appendix boundaries, an included table and an imported PDF figure.
[Its differential results](../results/live-fixture.json) include three retained
edits, forward navigation and cache reuse. [Chromium checks](../results/scrolling.json)
exercise continuous scrolling, bounded decoded pages, navigation to an unloaded
page, reverse selection, unsaved updates, convergence without scrolling jumps,
included-file edits, stale output on errors and recovery. The VS Code command
itself is tested with mocked extension APIs and deliberately obsolete settings;
[extension-live.json](../results/extension-live.json) records those checks.

The existing 100-page corpus remains covered by 343 C++ differential checks of
pixels, source regions, text selection, math/TikZ edits, resource misses, reflow
and error recovery. The mapper also passes 104 comparisons against its independent
Python reference. These are correctness checks, not a p95 latency benchmark.

## Boundaries

This remains an experimental LuaHBTeX 1.14 backend running through WSL on Windows.
It is not a native Windows compiler, and XeLaTeX-only source may need adaptation.
The source instrumenter is bounded: supported text and math have token mappings;
opaque arguments and environments have macro-origin ranges. Arbitrary catcode
changes, dynamically computed input names and all TeX macro conventions are not
covered. Imported PDF figure text has no TeX source token, while surrounding text
and captions remain mapped. Literal body inputs are instrumented; preamble inputs
do not get body-token mapping. Automatic bibliography/index tools and assets
outside the root file's directory remain unsupported.

The 150 ms p95 edit-to-preview target is still unproven. Initial builds, preamble
changes, reference convergence and new resources can take seconds. Per-edit
compiler/render timing appears in the preview and the BaKoMa output channel.
The architecture and whitespace/shipout invariants are described in
[ADR 0005](adr/0005-live-project-sessions.md).

## Install and use

```powershell
code --install-extension D:\macro_local\bakoma_new\artifacts\bakoma-revived-prototype-0.0.8.vsix --force
```

Run **Developer: Reload Window**, open the main `.tex` file and run
**BaKoMa: Open Experimental Preview**. There is no manual intermediate build or
separate synchronization setup. Old preview panels should be reopened after
updating. Saving source in VS Code still writes the file that was opened; use an
editable copy when testing a read-only project.
