# BaKoMa live pipeline: installed documentation and scripts

Investigated 2026-10-10. Read-only inspection of the installed documentation and readable control scripts; no BaKoMa binary was executed or modified for this note. This complements the separate binary investigation.

## Findings established by installed first-party material

**BaKoMa's live pipeline is built around an incremental TeX session and a DVI-facing viewer; PDF generation is a separate export operation.** This is substantially different from repeatedly finalizing a PDF and reopening it for preview.

| Evidence | What it establishes | Source |
|---|---|---|
| The user guide explains an extra save of TeX state after `\\begin{document}`, avoiding initialization and package loading when editing page one. | Actual compiler-state reuse is documented, rather than merely cached images or faster process startup. The guide says the command must begin a line for this extra save. | [guide.tex:97](C:/BaKoMa.TeX/BaKoMa/TeXWord/doc/guide.tex:97), lines 97–104 |
| Startup loads a selected processor through `tex.processor` and begins work with `tex.start`. | TeX is exposed as a persistent callable component to the editor's control language. This script alone does not identify its memory management implementation. | [StartUp.ctr:473](C:/BaKoMa.TeX/BaKoMa/TeXWord/StartUp.ctr:473), lines 473–489 |
| After an edit to an editor buffer, `tex.touch` is called with a comment saying modified buffers invalidate pages. | Edits are coupled to incremental invalidation, without a visible save-to-disk/build-process loop in these procedures. | [StartUp.ctr:566](C:/BaKoMa.TeX/BaKoMa/TeXWord/StartUp.ctr:566), lines 566–584 |
| `PrepareDVIFile` calls `1000000 tex.continue`; comments and status text describe processing the entire document for printing/export. `ExportDVI` then calls `dvi.export`. | Ordinary editing may leave the document only partly processed. Continuing to completion and serializing a DVI file are explicit separate operations. | [File.ctr:787](C:/BaKoMa.TeX/BaKoMa/TeXWord/File.ctr:787), lines 787–803 |
| The Last Page command also calls `tex.continue` before selecting the final page. | Navigation can request more computation on demand. | [TeXView.ctr:847](C:/BaKoMa.TeX/BaKoMa/Common/TeXView.ctr:847), lines 847–850 |
| Generate PDF calls `PrepareDVIFile` and then the PDF generation dialog. The command-line PDF documentation invokes `dview.exe` on a DVI file, with font embedding/compression flags. | PDF is a downstream export, not a prerequisite identified in the live preview procedures. | [TeXView.ctr:711](C:/BaKoMa.TeX/BaKoMa/Common/TeXView.ctr:711), lines 711–715; [genpdf.txt:5](C:/BaKoMa.TeX/BaKoMa/doc/genpdf.txt:5), lines 5–31 |
| Version 8.10 introduced independently controlled caches for imported graphics and PowerDot backgrounds. Version 8.03 describes an LRU page cache which discards cached pages and saves video memory. | Rendered pages and expensive imported graphics are reused in addition to compiler state. This is not evidence of arbitrary TikZ macro execution caching. | [changes7.html:708](C:/BaKoMa.TeX/BaKoMa/doc/changes7.html:708), lines 708–742 |
| Synchronization takes file, line, column, and page; it selects a DVI page, paints to generate stop points, then sets the caret. | Caret geometry is connected to the live viewer's generated stop points rather than necessarily recovered by parsing PDF. | [SyncPreview.ctr:78](C:/BaKoMa.TeX/BaKoMa/TeXWord/SyncPreview.ctr:78), lines 78–82 |

## Historical web corroboration

The [author's 2004 CTAN release announcement](https://mailman.ctan.org/hyperkitty/list/ctan-ann%40ctan.org/thread/NAT3FQHYY3JZZNW6APGVXFO6A5CYRF2X/) explicitly describes character-precision forward/reverse DVI search, synchronized carets, and keystrokes in the DVI window being sent back to the source editor and reprocessed by TeX. That is direct author material preserved by CTAN. It establishes the early DVI-based interaction architecture; it does not by itself establish every detail of the later TeXWord implementation.

The [surviving FAQ mirror](https://bakoma-tex.daniel-aldrich.ca/support/faq) says the original site is no longer available and its maintainer is not the creator. Its historical FAQ text says processing usually stops at the visible page, the live TeX log remains open, and page/image caches improve responsiveness. Treat this as corroborating mirrored documentation, not independently authenticated current first-party documentation. The installed export and continuation scripts above independently support the partial-document behavior.

The [mirrored change log](https://bakoma-tex.daniel-aldrich.ca/downloads/change-log), version 11.30, describes synchronization modes for visible pages, processed document, and heuristically extending processing to find a source position. An October 2017 entry removes the unrestricted “Entire Document (Hard)” mode. This supports demand-driven scheduling, but supplies neither timing data nor an algorithm for state equivalence.

## Reasonable inference and unresolved details

The evidence supports this architecture:

```text
editor buffers → invalidate affected compiler/page state
               → restore/reuse TeX state, continue far enough
               → DVI-facing live page data + source positions
               → native viewer, cached pages/graphics/fonts

explicit print/export → continue whole document → DVI/PDF/etc.
```

The precise live representation may be DVI byte buffers, interpreted DVI objects, richer internal display lists, or a combination. The `dvi.*` interface and explicit `dvi.export` do **not** prove that every ordinary edit serializes a `.dvi` file to disk. They also do not prove zero disk I/O: fonts, images, source files and external tools can require it.

The saved-state format, checkpoint frequency, compression/delta strategy, handling of TeX side effects, and whether later unchanged suffixes are reused through state-convergence detection remain unknown from these documents. It would be incorrect to attribute an INC-TeX-style quiescence algorithm to BaKoMa without additional evidence.

## Implication for this prototype

Bypassing PDF finalization and PDF reparsing is a justified experiment. A streaming page display list with glyph origins would remove an intermediate artifact and allow the compiler/viewer to exchange only changed pages. However, the existing compiler-stage measurement combines typesetting and finalization; it does not measure how much of that stage is PDF serialization. No numerical speedup follows from this investigation alone.

The larger architectural lesson is to combine persistent compiler state, demand-driven continuation, source metadata carried into rendering, and page/graphics caching. Merely switching a cold or whole-document build from PDF to DVI would reproduce only one part of BaKoMa's design.
