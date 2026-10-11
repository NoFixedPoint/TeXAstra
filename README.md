# BaKoMa revived — feasibility prototype

This repository contains a runnable experiment, not a finished replacement for BaKoMa. It combines actual LuaTeX process checkpoints with token-source metadata, a selectable preview, and a VS Code webview. **The 150 ms latency target has not been met.** The original scope and confirmed decisions are in [the task brief](task20261010_bakoma_revived.md).

Version 0.0.3 adds an **in-memory page-command path and a persistent renderer**. In a paired 36-edit browser comparison, median latency fell from **242 to 193.5 ms** and p95 from **372 to 253 ms**. Read the [page-stream report](docs/page-stream-20261010.md) for measurements and remaining costs, the [earlier latency update](docs/latency-20261010.md), and the [feasibility report](docs/feasibility-20261010.md). Idle convergence restores downstream compiler checkpoints as well as the preview.

The [BaKoMa binary investigation](docs/bakoma-binary-pipeline.md) motivated separating live page output from document finalization. Ordinary edits now send page drawing commands to the retained renderer without finalizing, transporting, or reopening a PDF. Complete PDFs still seed fonts/resources at startup, during convergence, and when an edit needs new resources. This is a page-buffer implementation using LuaTeX's PDF drawing language, not a DVI engine.

## Run the interactive demo

On this Windows machine, Python, PyMuPDF, TeX Live, and Ubuntu-22.04 under WSL are already available:

```powershell
python -m pip install -r requirements.txt
python -m prototype.demo
```

Open <http://127.0.0.1:8765>. Edit the source pane, click individual rendered math symbols or TikZ text to select their source, or click a source token to highlight its output. Drag across the preview to select rendered text. Demo edits remain in memory; the original corpus files are not changed.

The default `stream` backend requires Linux LuaHBTeX **1.14**, CTeX, TikZ, Fandol fonts, and GCC. On Windows it uses the existing `Ubuntu-22.04` WSL distribution. Its C module requires a trusted TeX process with Lua dynamic loading enabled. Live drawing output uses a memory-backed descriptor; other engine files live in isolated `/tmp/bakoma-revived-*` directories. Use `--engine snapshot` to compare with finalized-PDF output on every edit.

For the slower native full-build comparison, run `python -m prototype.demo --engine native`. This needs LuaLaTeX and the same packages on the local PATH. Native full builds do not demonstrate incremental compilation.

## Run in VS Code

Open this repository in VS Code and press F5 using **Run BaKoMa prototype**. In the Extension Development Host, run **BaKoMa: Open Experimental Preview**. The default root is `corpus/main.tex`. The experimental root filename is currently `main.tex`; configure `bakoma.mainFile` if its directory differs. `bakoma.python` selects the Python interpreter and `bakoma.engine` selects the backend. The extension runs only in a trusted workspace.

Alternatively, install the local package with `code --install-extension artifacts/bakoma-revived-prototype-0.0.3.vsix`, open this repository, and run the same preview command. Select `stream` in `bakoma.engine` if you previously set it explicitly to `snapshot`.

The webview and browser demo share their renderer. The compiler service exchanges versioned source updates and page payloads over JSON lines. Its source mapping and compiler state do not depend on a separate native window.

## What the experiments establish

- `scripts/generate_corpus.py` creates a deterministic 100-page, multi-file Chinese/English, math, macro, and TikZ corpus, plus edit scenarios.
- `prototype/instrument.py` instruments an explicitly limited LaTeX subset with source-span identifiers. `prototype/provenance.lua` retains those identifiers on final glyph nodes and records them in actual glyph-output order during shipout. The renderer pairs this sidecar with its glyph trace, including TikZ transforms; a glyph-count mismatch disables navigation for that page. These are explicit identifiers, not repeated-word matching or line-only SyncTeX.
- `prototype/snapshot.c` retains real POSIX process state before each corpus page-file input. Edits invalidate later checkpoints and resume before the changed input. The C/Lua/TeX state and earlier output prefix are retained. Later input can be processed on demand.
- The service keeps a visibly stale preview on invalid input and disables navigation from stale output. During sustained typing it displays completed intermediate revisions, labels them stale, and coalesces queued edits. Complete builds run after an idle interval to converge references and downstream layout and supply a fresh set of reusable checkpoints.
- A separately built TeXpresso checkout is used for comparison; it is not a dependency of the LuaTeX prototype.

## Important limits of the proof

- Checkpoints currently require the corpus's explicit `pages/page-NNN.tex` input boundaries. This is **not** a general mid-paragraph rollback engine. Preamble and structural edits rebuild the session.
- Arbitrary TeX macros, catcode changes, verbatim material, generated files, bibliography tools, images, floats, and arbitrary document classes are not covered by this proof. Unknown commands are left unmapped and reported. Root-document body text is not instrumented. Non-glyph constructs such as fraction rules are not selectable source tokens.
- Source instrumentation is a research technique, not a complete parser or engine-level provenance implementation. Rendering equivalence and source mapping are validated on the supplied fixtures; they must not be generalized to arbitrary LaTeX.
- POSIX snapshots use `fork` and Linux descriptor state. **Native Windows checkpointing is unimplemented.** macOS checkpointing has not been established either. The native full-build backend is a functional fallback, not proof of the final platform/performance goals.
- Ordinary page payloads pass through in-memory drawing commands, PNG, and JSON. Complete PDFs remain necessary for resource seeding and background convergence. New fonts/glyphs or unsupported graphics resources trigger a refresh. TeX still writes auxiliary files, logs, source copies, and metadata inside the session; the complete workflow is not filesystem-free.
- After reflow, input-file index and physical page index may differ. The prototype's cross-file forward-navigation page guess remains limited; current-page token mappings carry exact source ranges.

## Reproduce the checks

```powershell
python scripts/check_mapping.py 100
python scripts/check_snapshot.py
python scripts/check_page_stream.py
python scripts/check_correctness.py
# With the demo running; browser checks additionally require Playwright/Chromium:
python scripts/check_browser.py http://127.0.0.1:8765
python scripts/benchmark_browser.py http://127.0.0.1:8765
```

Raw measurements and screenshots are in `results/`. Browser timing measures an input event through image decoding, text-layer installation, and two animation-frame callbacks; it is not a physical monitor latency measurement. Headless TeXpresso changed-pixel timings are separately labeled and must not be compared as correctness-verified end-to-end results.

The TeXpresso comparison uses the upstream source at commit `e8df7709077b2f86f6e16e6c86ceefb86de06f8d` in an isolated WSL checkout. `scripts/build_texpresso.py` applies MuPDF 1.19 include compatibility fixes and opt-in diagnostic instrumentation, then builds it. `scripts/benchmark_texpresso.py` runs inside WSL. The existing `/home/wenlan/texpresso` installation is unchanged.
