# BaKoMa revived — feasibility prototype

This repository contains a runnable experiment, not a finished replacement for BaKoMa. It combines retained LuaTeX compiler state with token-source metadata, a selectable preview, and a VS Code webview. **The 150 ms end-to-end target is not met for every workload, including typing bursts, new fonts and dense pages.** Native Windows and Linux use retained checkpoints; measurements and platform limits are documented in the [Windows report](docs/windows-native-20261011.md) and [Linux latency report](docs/preview-latency-20261011.md). The original scope and confirmed decisions are in [the task brief](task20261010_bakoma_revived.md).

Version **0.0.23** preserves the live compiler session when saving source changes already sent by the editor. Save notifications and generated document PDFs no longer force a second complete build; external source and figure changes still refresh. See [the save regression and validation](docs/save-latency-20261011.md).

Version **0.0.22** makes note edits beside unchanged PNG/JPEG figures stream the changed page without finishing the document. VS Code sends versioned text changes after its first buffer update, source spans are materialized on demand, and neighboring pages wait until editing settles after paint. See [the figure-note measurements and validation](docs/figure-note-latency-20261011.md).

Version **0.0.21** fixes edit-time compilation errors in documents using Hyperref or other preamble PDF initialization. The page-stream configuration is now applied before package loading. WSL remains the default. See [the diagnosis and validation](docs/preamble-stream-20261011.md).

Version **0.0.20** fixes VS Code forward synchronization to pages that have never loaded, including late included chapters. The default VSIX uses WSL on Windows and bundles the Linux runtime. See [the diagnosis, validation, and installer](docs/forward-sync-20261011.md).

Version **0.0.19** adds native Windows x64 preview support with retained compiler checkpoints. The separate native Windows VSIX ships one bundled executable, defaults to the native runtime, and needs an installed native TeX Live distribution. It does not need WSL at runtime. The executable verifies and extracts its embedded compiler/renderer DLLs into the user cache. See [Windows implementation, build instructions, validation, and limitations](docs/windows-native-20261011.md).

Version **0.0.18** discovers installed TeX Live binary directories and supports selecting the WSL instance and TeX installation. Startup verifies the selected format and packages with a compatibility compile using the bundled engine. **BaKoMa: Show LaTeX Environment** reports resolved configuration, tools, formats and dependencies; missing inputs name the selected installation and maintenance remedy. See [the implementation and validation](docs/distribution-20261011.md).

Version 0.0.17 supports main documents in subdirectories with shared project assets in sibling directories. The workspace folder defines the project root by default; `bakoma.projectRoot` overrides it. Saved asset changes refresh the preview while preserving unsaved text buffers. Source navigation uses project-relative paths, including aliased inputs. See [the implementation and validation](docs/project-assets-20261011.md).

Version 0.0.16 runs BibTeX, Biber, and MakeIndex from the installed LaTeX distribution during complete builds and idle convergence. Content fingerprints reuse unchanged auxiliary outputs, while bibliography, citation, index-entry, and index-style changes regenerate them. Builds stop after six LaTeX passes and report unresolved references and tool failures. See [the implementation and validation](docs/build-tools-20261011.md).

Version 0.0.15 keeps source-navigation failures local to individual output nodes. Fraction bars, radical bars, overlines and underlines navigate to their source commands; rotated rules retain their shape for click testing. Clicking unmapped content explains why no verified source location is available. See [the implementation and validation](docs/source-mapping-20261011.md).

Version 0.0.14 refreshes supported fonts and glyph subsets without finishing the document. A disposable fork of the paused engine exports a font-only bundle, and the retained renderer imports it for the affected page. Graphics and unsupported font resources keep the complete-PDF fallback. See [the implementation and validation](docs/font-resources-20261011.md).

Version 0.0.13 adds a repeatable browser latency benchmark and separates backend queueing, compilation, resource refresh, delivery, image decoding, text-layer updates, and paint scheduling. Nearby-page prefetch waits briefly during editing so it does not compete with the next keystroke. See [the measurements and validation](docs/preview-latency-20261011.md).

Version 0.0.12 places checkpoints at safe points in the TeX engine, including inside long included chapters. Input read positions determine which compiler state can be reused after an edit. The handwritten root paragraph splitter and its 2,048-block limit have been removed. See [the implementation and validation](docs/engine-checkpoints-20261011.md).

Version 0.0.11 introduced checkpoint reuse for included `.tex` edits using their earliest affected root block. Preamble dependencies still rebuild safely. See [the earlier implementation and validation](docs/included-edits-20261011.md).

Version 0.0.10 moved source tracking into LuaHBTeX's token scanner and macro expansion. The bundled engine carries token origins into text and math nodes; the production source rewriter has been removed. Internal snapshots have also been removed, leaving fork checkpoints. See [the implementation and validation](docs/token-origins-20261011.md).

Version 0.0.8 made **Open Experimental Preview** start a live LuaHBTeX session for ordinary projects, regardless of older PDFs, compiler comments or legacy preview settings. It added paragraph-boundary checkpoints, token/macro-origin navigation, reusable build files in the user's cache, and continuous scrolling with nearby pages loaded on demand. The original project receives no generated build files. See [live-project validation and limitations](docs/live-projects-20261011.md).

Internal differential snapshots have been removed to reduce maintenance. Linux retains fork checkpoints; Windows uses owned memory, stack, and file checkpoints. The [historical snapshot report](docs/internal-snapshots-20261011.md) records why that experiment was retired.

The shipping architecture is to bundle our preview engine and supporting runtime while using the user's existing LaTeX distribution for packages, classes, fonts, and supporting tools. Package installation and updates remain with that distribution's manager. Validated integrations include native Windows TeX Live 2025 and TeX Live inside Ubuntu-22.04 WSL. Other Linux x86-64/WSL installations can be selected and must pass preflight; this does not establish compatibility with arbitrary TeX Live releases. macOS, Windows ARM64 and MiKTeX runtimes remain unsupported. See [the package ownership decision](docs/adr/0007-external-latex-distribution.md).

The [BaKoMa binary investigation](docs/bakoma-binary-pipeline.md) motivated separating live page output from document finalization. Ordinary edits now send page drawing commands to the retained renderer without finalizing, transporting, or reopening a document PDF. New supported fonts and glyphs arrive in a small font-only PDF bundle. Complete document PDFs still seed resources at startup, during convergence, and for unsupported resource changes. This is a page-buffer implementation using LuaTeX's PDF drawing language, not a DVI engine.

## Run the interactive demo

Windows defaults to the native x64 backend. To build it from source, install MSVC C++ tools and a Windows SDK; the compiler cross-build also uses Ubuntu-22.04 WSL as a build tool. Close running previews before rebuilding:

```powershell
python scripts/build_windows_engine.py
python scripts/build_windows_cpp.py
python scripts/bundle_windows.py
node native/demo.js
```

Open <http://127.0.0.1:8765>. Edit the source pane, click individual rendered math symbols or TikZ text to select their source, or click a source token to highlight its output. Drag across the preview to select rendered text. Demo edits remain in memory; the original corpus files are not changed.

The default `cpp` backend bundles patched LuaHBTeX **1.14**. TeX Live supplies installed packages and fonts; the demo corpus uses CTeX, TikZ and Fandol. Build-time Python is not part of the edit/render path. Native Windows build files live in `%LOCALAPPDATA%/bakoma-revived`. Formats are generated there with the bundled compiler, leaving installed distribution formats unchanged.

Linux builds still use `scripts/build_engine.py` and `scripts/build_cpp.py`. Windows can explicitly select an existing Linux runtime using `node native/demo.js --runtime-mode wsl`; that comparison requires WSL and its TeX Live installation. Linux build prerequisites include GCC/G++, libdeflate/zlib development libraries and the dependencies documented in the build recipes.

For the Python comparison, install `requirements.txt` and run `node native/demo.js --engine stream`. Use `python -m prototype.demo --engine snapshot` to compare with finalized-PDF output on every edit. `python -m prototype.demo` also launches the C++ demo by default.

Checkpoint selection follows the platform: Windows uses retained native state; Linux/WSL uses fork checkpoints. The retired internal Linux snapshot setting remains removed.

For the slower native full-build comparison, run `python -m prototype.demo --engine native`. This needs LuaLaTeX and the same packages on the local PATH. Native full builds do not demonstrate incremental compilation.

## Run in VS Code

Open this repository in VS Code and press F5 using **Run BaKoMa prototype**. In the Extension Development Host, run **BaKoMa: Open Experimental Preview**. The extension discovers an active root document, its `% !TEX root` comment, `main.tex`, or the repository's `corpus/main.tex`; otherwise it prompts for a file. Set `bakoma.mainFile` to override discovery. The extension runs only in a trusted workspace.

Alternatively, install the default WSL package with `code --install-extension artifacts/bakoma-revived-prototype-0.0.23.vsix --force`, reload VS Code, and run the same preview command. It includes the Linux runtime and requires WSL with TeX Live when running on Windows. Build it with `python scripts/package_extension.py`. The separate native Windows package recipe remains available through `npm run package:windows`.

For another project, open its folder and main `.tex` file, then run **BaKoMa: Open Experimental Preview**. Example workspace settings:

```json
{
  "bakoma.mainFile": "paper.tex"
}
```

The command always uses C++ and LuaHBTeX live compilation. Legacy `bakoma.engine`, `bakoma.previewMode` and `bakoma.latexCompiler` settings no longer select a reduced-feature preview. `% !TEX root` still selects the root; `% !TEX program` does not choose our compiler. Close the preview and reopen it after changing the main file. The default VSIX uses **WSL on Windows**. Optionally set `bakoma.wslDistribution`; `bakoma.texBinDirectory` must be a Linux path such as `/usr/bin`, or empty for discovery. The separate native Windows VSIX defaults to `bakoma.runtimeMode=native` and uses native TeX Live paths such as `C:\texlive\2025\bin\windows`. Each package includes only its own platform runtime. Reopen after changing selection or maintaining system packages. Run **BaKoMa: Show LaTeX Environment** for a JSON report. XeLaTeX-specific source may need adaptation to LuaLaTeX; opening our preview does not silently switch to a compiler without source mapping.

Live builds copy supported TeX, image, font and data assets beneath the project root, preserving the directory layout and compiling from the mirrored main-file directory. For example, `paper/main.tex` can reference `../figures/chart.pdf` and `../shared/references.bib`. The project root defaults to the containing workspace folder, or the main-file directory without a workspace. Set `bakoma.projectRoot` to a common ancestor when shared files live outside that folder; relative settings resolve against the workspace, or the main-file directory without a workspace. Close and reopen the preview after changing either project setting.

Root and included-body text edits restore the latest retained engine checkpoint that has not read the changed text. Preamble dependencies, package/asset edits, and files without usable dependency history rebuild the session. A debounced VS Code watcher refreshes saved changes, creations and deletions of supported project files, preserving currently dirty buffers. Initial loading and idle convergence compile the complete document and run required bibliography/index tools. Build files stay in the cache. Hidden directories and `node_modules` are excluded; files outside the chosen project root and absolute project paths are not remapped. The extension never saves editor buffers automatically; saving in VS Code still writes the file you opened, so use a separate copy to edit a read-only project.

The webview and browser demo share their renderer. The compiler service exchanges versioned source updates and page payloads over JSON lines. Its source mapping and compiler state do not depend on a separate native window.

## What the experiments establish

- `scripts/generate_corpus.py` creates a deterministic 100-page, multi-file Chinese/English, math, macro, and TikZ corpus, plus edit scenarios.
- `engine/` adds token origins to LuaHBTeX; `native/source.hpp` indexes unchanged source text and translates engine spans into editor positions. `prototype/provenance.lua` marks glyphs and rules without changing text positioning. `native/mapping.hpp` checks each marked output node independently; a mismatch leaves other regions navigable.
- `prototype/snapshot.c` retains Linux fork checkpoints. `native/windows/` restores compiler-owned memory, execution state and file positions in one persistent Windows worker process.
- The service keeps a visibly stale preview on invalid input and disables navigation from stale output. During sustained typing it displays completed intermediate revisions, labels them stale, and coalesces queued edits. Complete builds run after an idle interval to converge references and downstream layout and supply a fresh set of reusable checkpoints.
- A separately built TeXpresso checkout is used for comparison; it is not a dependency of the LuaTeX prototype.

## Important limits of the proof

- General projects retain at most one checkpoint per shipped page, between completed TeX commands in outer vertical mode. Long paragraphs, boxes, and macro arguments read ahead of their output can require earlier replay. Preamble dependencies and coalesced edits to multiple files still rebuild the session. The supplied comparison corpus retains explicit page-file checkpoints. Source origins currently support up to 2,146 registered files, each smaller than one million Unicode characters; root documents are now indexed as whole files too.
- Root body text and project `.tex` inputs get engine token origins. Macro arguments retain their token locations; generated macro content falls back to the calling command token. Math rules with retained origins are clickable but do not add text to copied selections. Generated bibliography/index text has no mapping back to `.bib` entries or index definitions. Automatic tools cover BibTeX, Biber with local data sources, and conventional MakeIndex jobs; custom tool chains and Xindy remain unsupported.
- The compiler provenance and checkpoint patches are experimental. Arbitrary Lua-generated nodes, transformed input buffers, external token manipulation, and file reads performed directly by external Lua modules are outside the validated cases.
- Windows x64 checkpoints own compiler heap/globals/stack and tracked file state; Linux/WSL retains forks. Arbitrary external native Lua modules and their threads/state are outside Windows checkpoint ownership. macOS and Windows ARM64 are unsupported. Windows currently reserves a fixed 2 GiB compiler arena; histories have no memory-budget eviction.
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
python scripts/check_source_mapping.py
python scripts/check_build_tools.py
python scripts/check_project_assets.py
python scripts/check_distribution.py
node scripts/check_launcher.js
node scripts/check_project.js
node scripts/check_extension_live.js
python scripts/check_mapping_browser.py
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
