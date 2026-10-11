# BaKoMa revived — feasibility prototype

This repository contains a runnable experiment, not a finished replacement for BaKoMa. It combines retained LuaTeX compiler state with token-source metadata, a selectable preview, and a VS Code webview. **The latest local 13-page browser benchmark is below 150 ms p95 in all four tested scenarios.** This does not establish performance for arbitrary projects or the real VS Code host. The original scope and confirmed decisions are in [the task brief](task20261010_bakoma_revived.md).

Version **0.0.14** refreshes supported fonts and glyph subsets without finishing the document. A disposable fork of the paused engine exports a font-only bundle, and the retained renderer imports it for the affected page. Graphics and unsupported font resources keep the complete-PDF fallback. See [the implementation and validation](docs/font-resources-20261011.md).

Version 0.0.13 adds a repeatable browser latency benchmark and separates backend queueing, compilation, resource refresh, delivery, image decoding, text-layer updates, and paint scheduling. Nearby-page prefetch waits briefly during editing so it does not compete with the next keystroke. See [the measurements and validation](docs/preview-latency-20261011.md).

Version 0.0.12 places checkpoints at safe points in the TeX engine, including inside long included chapters. Input read positions determine which compiler state can be reused after an edit. The handwritten root paragraph splitter and its 2,048-block limit have been removed. See [the implementation and validation](docs/engine-checkpoints-20261011.md).

Version 0.0.11 introduced checkpoint reuse for included `.tex` edits using their earliest affected root block. Preamble dependencies still rebuild safely. See [the earlier implementation and validation](docs/included-edits-20261011.md).

Version 0.0.10 moved source tracking into LuaHBTeX's token scanner and macro expansion. The bundled engine carries token origins into text and math nodes; the production source rewriter has been removed. Internal snapshots have also been removed, leaving fork checkpoints. See [the implementation and validation](docs/token-origins-20261011.md).

Version 0.0.8 made **Open Experimental Preview** start a live LuaHBTeX session for ordinary projects, regardless of older PDFs, compiler comments or legacy preview settings. It added paragraph-boundary checkpoints, token/macro-origin navigation, reusable build files in the user's cache, and continuous scrolling with nearby pages loaded on demand. The original project receives no generated build files. See [live-project validation and limitations](docs/live-projects-20261011.md).

Internal differential snapshots have been removed to reduce maintenance. Fork checkpoints are the only supported implementation. The [historical snapshot report](docs/internal-snapshots-20261011.md) records why that experiment was retired.

The shipping architecture is to bundle our preview engine and supporting runtime while using the user's existing LaTeX distribution for packages, classes, fonts, and supporting tools. Package installation and updates remain with that distribution's manager. Today the supported integration is TeX Live inside Ubuntu-22.04 WSL on Windows; distribution discovery, compatibility diagnostics, and environment reporting remain future work. See [the package ownership decision](docs/adr/0007-external-latex-distribution.md).

The [BaKoMa binary investigation](docs/bakoma-binary-pipeline.md) motivated separating live page output from document finalization. Ordinary edits now send page drawing commands to the retained renderer without finalizing, transporting, or reopening a document PDF. New supported fonts and glyphs arrive in a small font-only PDF bundle. Complete document PDFs still seed resources at startup, during convergence, and for unsupported resource changes. This is a page-buffer implementation using LuaTeX's PDF drawing language, not a DVI engine.

## Run the interactive demo

On this Windows machine, Node and Ubuntu-22.04 under WSL are already available. The packaged backend is Linux x86-64; Windows launches it through WSL. To build from source, close running C++ previews first:

```powershell
python scripts/build_engine.py
python scripts/build_cpp.py
node native/demo.js
```

Open <http://127.0.0.1:8765>. Edit the source pane, click individual rendered math symbols or TikZ text to select their source, or click a source token to highlight its output. Drag across the preview to select rendered text. Demo edits remain in memory; the original corpus files are not changed.

The default `cpp` backend bundles patched Linux LuaHBTeX **1.14** and requires installed LaTeX packages, CTeX, TikZ, Fandol fonts, and system libdeflate/zlib. Building also requires Python, G++, GCC, `libdeflate-dev`, and `zlib1g-dev`. Pinned MuPDF and JSON dependencies are fetched by the build script; Python is only a build/test tool for this backend. On Windows it uses the existing `Ubuntu-22.04` WSL distribution. Its C checkpoint module requires a trusted TeX process with Lua dynamic loading enabled. Live drawing output uses a memory-backed descriptor. General-project build files live in `$XDG_CACHE_HOME/bakoma-revived`, defaulting to `~/.cache/bakoma-revived` inside WSL; corpus/comparison sessions use `/tmp/bakoma-cpp-*`.

For the Python comparison, install `requirements.txt` and run `node native/demo.js --engine stream`. Use `python -m prototype.demo --engine snapshot` to compare with finalized-PDF output on every edit. `python -m prototype.demo` also launches the C++ demo by default.

The C++ backend uses fork checkpoints. The former internal snapshot mode and its VS Code setting have been removed; saved extension settings no longer select it.

For the slower native full-build comparison, run `python -m prototype.demo --engine native`. This needs LuaLaTeX and the same packages on the local PATH. Native full builds do not demonstrate incremental compilation.

## Run in VS Code

Open this repository in VS Code and press F5 using **Run BaKoMa prototype**. In the Extension Development Host, run **BaKoMa: Open Experimental Preview**. The extension discovers an active root document, its `% !TEX root` comment, `main.tex`, or the repository's `corpus/main.tex`; otherwise it prompts for a file. Set `bakoma.mainFile` to override discovery. The extension runs only in a trusted workspace.

Alternatively, install the local package with `code --install-extension artifacts/bakoma-revived-prototype-0.0.14.vsix --force`, reload VS Code, and run the same preview command. The package includes the C++ executable, snapshot runtime, and MuPDF library; its TeX/WSL prerequisites still apply.

For another project, open its folder and main `.tex` file, then run **BaKoMa: Open Experimental Preview**. Example workspace settings:

```json
{
  "bakoma.mainFile": "paper.tex"
}
```

The command always uses C++ and LuaHBTeX live compilation. Legacy `bakoma.engine`, `bakoma.previewMode` and `bakoma.latexCompiler` settings no longer select a reduced-feature preview. `% !TEX root` still selects the root; `% !TEX program` does not choose our compiler. Close the preview and reopen it after changing the main file. Windows uses packages/fonts installed in **Ubuntu-22.04 WSL**. XeLaTeX-specific source may need adaptation to LuaLaTeX; opening our preview does not silently switch to a compiler without source mapping.

Live builds copy supported TeX, image, font and data assets below the main file's directory. Root and included-body edits restore the latest retained engine checkpoint that has not read the changed text. Preamble dependencies, package/asset edits, and files without usable dependency history rebuild the compiler session. Initial loading and idle convergence still compile the complete document. Assets outside that directory and automatic bibliography/index tools are not yet supported. Build files are isolated from the source directory and reused when inputs and dependencies match. The extension never saves editor buffers automatically; saving in VS Code still writes the file you opened, so use a separate copy to edit a read-only project.

The webview and browser demo share their renderer. The compiler service exchanges versioned source updates and page payloads over JSON lines. Its source mapping and compiler state do not depend on a separate native window.

## What the experiments establish

- `scripts/generate_corpus.py` creates a deterministic 100-page, multi-file Chinese/English, math, macro, and TikZ corpus, plus edit scenarios.
- `engine/` adds token origins to LuaHBTeX; `native/source.hpp` indexes unchanged source text and translates engine spans into editor positions. `prototype/provenance.lua` records glyph origins in actual output order. The renderer pairs these IDs with its glyph trace, including TikZ transforms; a glyph-count mismatch disables navigation for that page.
- `prototype/snapshot.c` retains compiler processes at checkpoints; edits fork from the preceding checkpoint and resume typesetting.
- The service keeps a visibly stale preview on invalid input and disables navigation from stale output. During sustained typing it displays completed intermediate revisions, labels them stale, and coalesces queued edits. Complete builds run after an idle interval to converge references and downstream layout and supply a fresh set of reusable checkpoints.
- A separately built TeXpresso checkout is used for comparison; it is not a dependency of the LuaTeX prototype.

## Important limits of the proof

- General projects retain at most one checkpoint per shipped page, between completed TeX commands in outer vertical mode. Long paragraphs, boxes, and macro arguments read ahead of their output can require earlier replay. Preamble dependencies and coalesced edits to multiple files still rebuild the session. The supplied comparison corpus retains explicit page-file checkpoints. Source origins currently support up to 2,146 registered files, each smaller than one million Unicode characters; root documents are now indexed as whole files too.
- Root body text and project `.tex` inputs get engine token origins. Macro arguments retain their token locations; generated macro content falls back to the calling command token. Non-glyph constructs such as fraction rules are not selectable. Existing bibliography output can be copied, but automatic bibliography/index tools are not implemented.
- The compiler provenance and checkpoint patches are experimental. Arbitrary Lua-generated nodes, transformed input buffers, external token manipulation, and file reads performed directly by external Lua modules are outside the validated cases.
- Fork checkpoints require Linux/WSL. Native Windows and macOS checkpoint implementations are unavailable.
- Ordinary page payloads pass through in-memory drawing commands, PNG, and JSON. Complete PDFs remain necessary for resource seeding and background convergence. Supported new fonts/glyphs use font-only bundles; Type 3 fonts, custom font attributes, external graphics, changed page dimensions, and new physical pages can require a complete resource export. TeX still writes auxiliary files, logs, source copies, and metadata inside the session; the complete workflow is not filesystem-free.
- Source navigation uses rendered glyph IDs and physical pages, including pages outside the loaded viewport. Imported PDF figure text has no TeX-token provenance; body text and captions remain navigable.

## Reproduce the checks

```powershell
python -m pip install -r requirements.txt
python scripts/check_token_origins.py
python scripts/check_live_syntax.py
python scripts/check_included_edits.py
python scripts/check_engine_checkpoints.py
python scripts/check_font_resources.py
python scripts/check_cpp.py
python scripts/live_fixture.py
python scripts/check_live_mode.py --project .work/scroll-case --main paper.tex --output live-fixture.json
node scripts/check_extension_live.js
python scripts/check_viewer_latency.py
# Self-contained browser benchmark; starts and closes its own demo server:
python scripts/benchmark_preview.py --repeats 20
# Add --assert-target to fail unless every scenario's p95 is below 150 ms.
# Earlier Python reference backend checks:
python scripts/check_mapping.py 100
python scripts/check_snapshot.py
python scripts/check_page_stream.py
python scripts/check_renderer.py
python scripts/check_correctness.py
# With the demo running; browser checks additionally require Playwright/Chromium:
node native/demo.js --project .work/scroll-case --main paper.tex --port 8799
python scripts/check_scrolling.py http://127.0.0.1:8799
python scripts/benchmark_browser.py http://127.0.0.1:8765
```

Raw measurements and screenshots are in `results/`. Browser timing measures an input event through image decoding, text-layer installation, and two animation-frame callbacks; it is not a physical monitor latency measurement. Headless TeXpresso changed-pixel timings are separately labeled and must not be compared as correctness-verified end-to-end results.

The TeXpresso comparison uses the upstream source at commit `e8df7709077b2f86f6e16e6c86ceefb86de06f8d` in an isolated WSL checkout. `scripts/build_texpresso.py` applies MuPDF 1.19 include compatibility fixes and opt-in diagnostic instrumentation, then builds it. `scripts/benchmark_texpresso.py` runs inside WSL. The existing `/home/wenlan/texpresso` installation is unchanged.
