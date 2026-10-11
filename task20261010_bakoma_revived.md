I have this software C:\BaKoMa.TeX which is a latex editor that use incremental rendering so that dvi is rendered in time when editing tex files and can be updated while typing with almost no latency; the underlying technology maybe an incremental rendering modified latex compiler. The source code, however, is lost. It also has the great functionality that can click on the rendered result (the rendered result is like a pdf viewer that has a text cursor, and we can select text, and by clicking the text cursor, it syncs to the exact location at the text window, even in the math environment); of course, by clicking on the latex source, I can sync to the rendered result as well. Even tikz can be rendered and text in tikz can be synced.

I want you to port the implementation to a cross-platform vscode plugin, so when editing in vscode editor, can have a such a window to do live updating/rendering with very low latency, and also has the above feature for sync and reverse sync.

Consider use a latex distribution that supports modern features (e.g., native unicode support so as to support Chinese)

## Design interview — 2026-10-10

Confirmed requirements:

- First deliverable: a feasibility prototype proving incremental preview speed and precise source/preview synchronization before building the full extension.
- Synchronization: token-level mapping for ordinary text, math, and TikZ text; use the source argument or macro invocation for generated content without a unique source character. Line-level mapping alone does not satisfy the target.
- Preview interaction: selection, visible caret, and navigation. Edits remain in the VS Code source editor.
- Warm-edit latency target: below 150 ms for 95% of ordinary text/math edits, measured from the last keystroke to visible updated content. Record hardware and document size. Measure initial loading and expensive TikZ redraws separately. This is an acceptance target, not an established result.
- Continuous typing must also produce visible progress. Record update frequency, longest visible freeze, and caret/scroll stability; avoid flicker and scroll jumps. Passing isolated-edit timing alone does not establish a smooth experience.
- Reimplement the editing experience using available technology; use installed BaKoMa as a behavioral reference. Recovering its original compiler is not a prerequisite.
- TeXpresso is only one candidate. The user has experienced bugs and missing features with it, and finds BaKoMa substantially smoother. Evaluate alternatives before choosing an engine or rendering architecture.
- A separate preview window is acceptable for the feasibility prototype. The finished extension must provide an embedded VS Code preview panel.
- The prototype design must accommodate that embedded panel from the outset: compiler state, rendering data, and source mappings must not depend on a particular top-level preview window.
- Acceptance corpus: a reproducible 100-page, multi-file document containing Chinese/English text, repeated words, custom macros, fractions/subscripts, cross-references, and TikZ labels. Test ordinary edits near the beginning, middle, and end.
- During invalid intermediate input, retain the last successful preview with a visible stale/error indicator and recover automatically. Disable stale navigation unless its mapping to current source has been validated.
- WSL is acceptable for initial feasibility experiments. The finished product must run natively on Windows, macOS, and Linux; a successful WSL experiment does not establish native Windows feasibility.
- Apply the 150 ms target to the correct visible-page update for ordinary edits. Off-screen pages and cross-references may converge afterward, with provisional results indicated. Measure full-document convergence separately.
- Modifying and maintaining an open-source TeX engine is acceptable if necessary for latency or source mapping. Assess compatibility, maintenance cost, and native-platform feasibility before choosing a fork.
- The user's remembered TeXpresso limitations are missing character-level navigation, especially forward/reverse synchronization within math, and its separate preview window. The agreed token-level mapping with macro-origin fallback defines the synchronization requirement; the separate-window limitation is deferred only for the prototype.

Observation to investigate:

- The user reports that BaKoMa feels smoother than TeXpresso and appears to compile and incrementally render entirely in memory. The in-memory architecture is a hypothesis to verify, not yet an established implementation fact.
- The user observes that an edit updates the current and nearby pages quickly, and later pages adapt quickly when scrolled into view. Investigate retained compiler state, selective invalidation, cached rendering, and demand-driven continuation. Do not infer that every edit has only local semantic effects or that visually unchanged pages prove identical compiler state.

Local evidence gathered:

- `C:/BaKoMa.TeX/BaKoMa/TeXWord/StartUp.ctr:570` and `:582` call `tex.touch` with a comment identifying page invalidation after buffer modifications.
- `C:/BaKoMa.TeX/BaKoMa/TeXWord/File.ctr:787-803` continues compilation through the full document before explicit DVI export. `StartUp.ctr:503` describes the first page having been processed at startup.
- `C:/BaKoMa.TeX/BaKoMa/TeXWord/File.ctr:425-441` flushes auxiliary/bibliography buffers for an external BibTeX run. This supports buffered internal processing with external-tool boundaries, rather than proving a completely disk-free workflow.
- `C:/BaKoMa.TeX/BaKoMa/TeXWord/SyncPreview.ctr:29-35` and `:78-82` expose file/line/column source lookup and a DVI caret.
- These findings support persistent, buffer-aware, demand-driven processing. They do not establish the internal checkpoint mechanism, precise invalidation granularity, or zero disk I/O. Measure those properties where observable; do not assume the cause of BaKoMa's responsiveness.

Candidate investigations (no architecture selected):

- Use [TeXpresso](https://github.com/let-def/texpresso) as one incremental-compilation baseline. Record failures and unsupported features. Its documented [editor protocol](https://github.com/let-def/texpresso/blob/main/EDITOR-PROTOCOL.md) supplies line-based synchronization, which does not satisfy the agreed mapping requirement.
- Investigate LuaTeX callbacks, node metadata, and additional source instrumentation as a distinct source-mapping path. The [LuaTeX manual](https://texdoc.org/serve/luatex/0) documents these extension points; exact token origins and correct incremental rollback remain unproved.
- Evaluate checkpoint/invalidation design separately from output transport. A persistent engine still needs a correct way to undo invalidated execution state.
- Compare direct DVI/XDV or another in-memory display representation with PDF-based rendering. Direct output must preserve relevant font and graphics semantics, including TikZ transforms and clipping; removing disk round trips alone does not establish low latency or correctness.
- Measure compiler work, output transport, visible rendering, and source-mapping accuracy separately. Compare incremental output with a complete build using matching engine, package, and font versions. Use BaKoMa as the interaction reference.

## Feasibility work plan for shared-understanding confirmation

1. Create the reproducible 100-page corpus and edit/navigation scenarios. Include repeated text and symbols on the same source line, nested fractions and scripts, macro-generated symbols, Chinese text, repeated TikZ labels, and edits in included files. Record engine/package/font versions, hardware, and the exact workload.
2. Establish complete-build correctness references and available BaKoMa interaction observations. Measure startup, isolated edits, sustained typing, scrolling into invalidated later pages, and expensive TikZ edits separately. Count debounce, compilation, transport, and display work in edit-to-visible timing rather than reporting compilation time alone.
3. Investigate at least two engine strategies: the TeXpresso/custom-XeTeX family and a LuaTeX instrumentation/modification path. Test source provenance and incremental state restoration explicitly. Treat an in-memory transport as a candidate optimization, not a substitute for retained computation or correct invalidation.
4. Prove both directions of token-level navigation, including individual math symbols on a shared source line and text inside TikZ. Report exact source spans, macro-origin fallbacks, unsupported cases, and failures. A line jump or approximate text search alone does not satisfy the requirement.
5. Stress correctness after changes that may affect later content: paragraph reflow, page breaks, macro definitions, counters/references, included files, and recovery from incomplete input. Validate the latest visible output and its mappings against the corresponding source revision, then compare converged output with a complete build.
6. Combine speed, mapping, and rendering in one working candidate before declaring the core capabilities proved. A fast engine without precise mapping and a separate slow mapping experiment do not together constitute a pass. Keep the compiler/rendering interface suitable for a future VS Code webview and document native Windows portability gaps.
7. Deliver runnable prototype code, the corpus, reproducible measurement instructions/results, and an evidence-based engine recommendation. Report unmet targets explicitly. Building the complete embedded, native cross-platform extension follows successful proof of the core capabilities.

No engine, checkpoint mechanism, or output representation has been selected. All interview questions Q1–Q13 have been answered. The user confirmed this consolidated scope with "go"; feasibility implementation is authorized.

## Feasibility delivery

The runnable prototype, shared browser/VS Code preview, 100-page corpus, local VSIX, and reproducible checks have been implemented. See [the feasibility report](docs/feasibility-20261010.md) and [run instructions](README.md).

The core feasibility gate is only partially satisfied: stateful incremental compilation and precise tested glyph/source mappings operate together, and the instrumented 100-page rendering matches the reference. End-to-end latency measured 277 ms at the 95th percentile, above the 150 ms target; the worst case was 4,558 ms after downstream checkpoints were invalidated. General-document rollback and native Windows/macOS checkpointing are not established. The complete cross-platform replacement remains unfinished; no passing production engine has been selected.

The subsequent latency optimization is delivered as prototype 0.0.2. A back-to-back comparison under the current machine load reduced p95 from 305 to 251 ms; the 150 ms target remains unmet. Idle convergence now restores compiler checkpoints, removing the later-page edit replay once convergence finishes. Immediate far jumps before convergence still require sequential work. Rendering equivalence, token navigation, and syntax-error recovery are retained. See [the optimization report](docs/latency-20261010.md) for measurements and limitations.

The user subsequently authorized implementing the page-buffer direction from the
BaKoMa binary investigation. Prototype 0.0.3 adds memory-backed live drawing
output, socket transport, and a persistent renderer. Ordinary edits skip complete
PDF finalization and reopening; cold initialization, convergence, and resource
misses still use complete PDFs. A paired browser comparison measured 242/372 ms
median/p95 with finalized PDF versus 193.5/253 ms with page commands. Exact pixels
and source regions are checked against full builds. The 150 ms target, general
rollback, and native Windows/macOS checkpointing remain unproved. See the
[implementation report](docs/page-stream-20261010.md).
