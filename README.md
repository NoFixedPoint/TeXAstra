# BaKoMa revived — feasibility prototype

This repository contains a runnable experiment, not a finished replacement for BaKoMa. It combines retained LuaTeX compiler state with token-source metadata, a selectable preview, and a VS Code webview. **The 150 ms latency target has not been met.** The original scope and confirmed decisions are in [the task brief](task20261010_bakoma_revived.md).

Version **0.0.8** makes **Open Experimental Preview** start our own live LuaHBTeX compiler for ordinary projects, regardless of older PDFs, compiler comments or legacy preview settings. It adds paragraph-boundary checkpoints, token/macro-origin navigation, reusable build files in the user's cache, and continuous scrolling with nearby pages loaded on demand. The original project receives no generated build files. See [live-project validation and limitations](docs/live-projects-20261011.md).

Version 0.0.6 adds experimental **internal differential compiler snapshots**: one retained compiler process restores its TeX/Lua memory, continuation, and file state from undo records, without forking per checkpoint or edit. The comparison measured 137.5 ms median versus 155 ms for fork checkpoints, but p95 regressed to 325 ms versus 185 ms on large backward rollbacks. **Fork remains the default; internal snapshots are opt-in.** Source mapping, compiler control, page-buffer reception, and rendering remain in C++; Python is only a build/test tool. Read the [internal snapshot report](docs/internal-snapshots-20261011.md) and [architecture decision](docs/adr/0004-internal-compiler-snapshots.md) for validation and the Linux-specific memory contract. Earlier work is recorded in the [C++ report](docs/cpp-backend-20261011.md) and [feasibility report](docs/feasibility-20261010.md).

The [BaKoMa binary investigation](docs/bakoma-binary-pipeline.md) motivated separating live page output from document finalization. Ordinary edits now send page drawing commands to the retained renderer without finalizing, transporting, or reopening a PDF. Complete PDFs still seed fonts/resources at startup, during convergence, and when an edit needs new resources. This is a page-buffer implementation using LuaTeX's PDF drawing language, not a DVI engine.

## Run the interactive demo

On this Windows machine, Node and Ubuntu-22.04 under WSL are already available. The packaged backend is Linux x86-64; Windows launches it through WSL. To build from source, close running C++ previews first:

```powershell
python scripts/build_cpp.py
node native/demo.js
```

Open <http://127.0.0.1:8765>. Edit the source pane, click individual rendered math symbols or TikZ text to select their source, or click a source token to highlight its output. Drag across the preview to select rendered text. Demo edits remain in memory; the original corpus files are not changed.

The default `cpp` backend requires Linux LuaHBTeX **1.14**, CTeX, TikZ, Fandol fonts, and system libdeflate/zlib. Building also requires Python, G++, GCC, `libdeflate-dev`, and `zlib1g-dev`. Pinned MuPDF and JSON dependencies are fetched by the build script; Python is only a build/test tool for this backend. On Windows it uses the existing `Ubuntu-22.04` WSL distribution. Its C checkpoint module requires a trusted TeX process with Lua dynamic loading enabled. Live drawing output uses a memory-backed descriptor. General-project build files live in `$XDG_CACHE_HOME/bakoma-revived`, defaulting to `~/.cache/bakoma-revived` inside WSL; corpus/comparison sessions use `/tmp/bakoma-cpp-*`.

For the Python comparison, install `requirements.txt` and run `node native/demo.js --engine stream`. Use `python -m prototype.demo --engine snapshot` to compare with finalized-PDF output on every edit. `python -m prototype.demo` also launches the C++ demo by default.

For the C++ process-checkpoint comparison, run `node native/demo.js --checkpoint fork`. Omitting the option also selects `fork`. Internal snapshots require Linux `/proc` soft-dirty tracking and a single-threaded compiler. They reserve virtual address space for the shadow/journal and can retain substantial memory on a 100-page document; this is still a bounded feasibility backend.

For the slower native full-build comparison, run `python -m prototype.demo --engine native`. This needs LuaLaTeX and the same packages on the local PATH. Native full builds do not demonstrate incremental compilation.

## Run in VS Code

Open this repository in VS Code and press F5 using **Run BaKoMa prototype**. In the Extension Development Host, run **BaKoMa: Open Experimental Preview**. The extension discovers an active root document, its `% !TEX root` comment, `main.tex`, or the repository's `corpus/main.tex`; otherwise it prompts for a file. Set `bakoma.mainFile` to override discovery. The extension runs only in a trusted workspace.

Alternatively, install the local package with `code --install-extension artifacts/bakoma-revived-prototype-0.0.8.vsix --force`, reload VS Code, and run the same preview command. Set `bakoma.checkpointMode` to `internal` to try internal snapshots on the corpus; `fork` remains the default. The package includes the C++ executable, snapshot runtime, and MuPDF library; its TeX/WSL prerequisites still apply.

For another project, open its folder and main `.tex` file, then run **BaKoMa: Open Experimental Preview**. Example workspace settings:

```json
{
  "bakoma.mainFile": "paper.tex"
}
```

The command always uses C++ and LuaHBTeX live compilation. Legacy `bakoma.engine`, `bakoma.previewMode` and `bakoma.latexCompiler` settings no longer select a reduced-feature preview. `% !TEX root` still selects the root; `% !TEX program` does not choose our compiler. Close the preview and reopen it after changing the main file. Windows uses packages/fonts installed in **Ubuntu-22.04 WSL**. XeLaTeX-specific source may need adaptation to LuaLaTeX; opening our preview does not silently switch to a compiler without source mapping.

Live builds copy supported TeX, image, font and data assets below the main file's directory. Body edits restore an earlier paragraph checkpoint; preamble and included-file edits rebuild the compiler session. Initial loading and idle convergence still compile the complete document. Assets outside that directory and automatic bibliography/index tools are not yet supported. Build files are isolated from the source directory and reused when inputs and dependencies match. The extension never saves editor buffers automatically; saving in VS Code still writes the file you opened, so use a separate copy to edit a read-only project.

The webview and browser demo share their renderer. The compiler service exchanges versioned source updates and page payloads over JSON lines. Its source mapping and compiler state do not depend on a separate native window.

## What the experiments establish

- `scripts/generate_corpus.py` creates a deterministic 100-page, multi-file Chinese/English, math, macro, and TikZ corpus, plus edit scenarios.
- `native/source.hpp` instruments an explicitly limited LaTeX subset with source-span identifiers; `prototype/instrument.py` remains its independent reference. `prototype/provenance.lua` retains those identifiers on final glyph nodes and records them in actual glyph-output order during shipout. The renderer pairs this sidecar with its glyph trace, including TikZ transforms; a glyph-count mismatch disables navigation for that page. These are explicit identifiers, not repeated-word matching or line-only SyncTeX.
- `native/internal_snapshot.cpp` stores changed-memory undo records before each corpus page-file input. Edits invalidate later checkpoints, restore C/Lua/TeX state and earlier output prefixes, and resume in the same compiler process. Later input can be processed on demand. `prototype/snapshot.c` supplies the Lua bridge and retains the fork comparison.
- The service keeps a visibly stale preview on invalid input and disables navigation from stale output. During sustained typing it displays completed intermediate revisions, labels them stale, and coalesces queued edits. Complete builds run after an idle interval to converge references and downstream layout and supply a fresh set of reusable checkpoints.
- A separately built TeXpresso checkout is used for comparison; it is not a dependency of the LuaTeX prototype.

## Important limits of the proof

- General projects use safe paragraph boundaries and retain at most one checkpoint per shipped page; the supplied corpus retains explicit page-file boundaries. Long paragraphs and opaque environments can require more replay. Preamble and included-file edits rebuild the session. The root needs explicit `\begin{document}` and `\end{document}`; the current driver allows 2048 paragraph blocks.
- Root body text and literal body inputs are instrumented. Supported text/math get token mappings; opaque macro arguments and environments get invocation ranges. Arbitrary catcodes, generated input and document classes remain outside the proof. Non-glyph constructs such as fraction rules are not selectable source tokens. Existing bibliography output can be copied, but automatic bibliography/index tools are not implemented.
- Source instrumentation is a research technique, not a complete parser or engine-level provenance implementation. Rendering equivalence and source mapping are validated on the supplied fixtures; they must not be generalized to arbitrary LaTeX.
- Internal snapshots use Linux memory/descriptor state and an x86-64 continuation, including the pinned compiler's allocator state. They are not a portable TeX-object serializer. **Native Windows checkpointing is unimplemented.** macOS checkpointing has not been established either. Native modules that alter mappings, additional compiler threads, and arbitrary external I/O are outside the snapshot contract. The fork comparison and native full-build fallback remain available.
- Ordinary page payloads pass through in-memory drawing commands, PNG, and JSON. Complete PDFs remain necessary for resource seeding and background convergence. New fonts/glyphs or unsupported graphics resources trigger a refresh. TeX still writes auxiliary files, logs, source copies, and metadata inside the session; the complete workflow is not filesystem-free.
- Source navigation uses rendered glyph IDs and physical pages, including pages outside the currently loaded viewport. Imported PDF figure text has no TeX-token provenance; body text and captions on those pages remain navigable. Unrecognized macro/environment syntax uses an invocation range where possible. This bounded source instrumenter is not a general TeX parser.

## Reproduce the checks

```powershell
python -m pip install -r requirements.txt
python scripts/check_cpp_mapper.py
python scripts/check_cpp.py
python scripts/live_fixture.py
python scripts/check_live_mode.py --project .work/scroll-case --main paper.tex --output live-fixture.json
node scripts/check_extension_live.js
python scripts/check_internal_snapshot.py
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
