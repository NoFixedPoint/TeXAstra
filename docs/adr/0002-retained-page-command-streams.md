# Retain renderer resources and stream page commands before document finalization

The installed BaKoMa binaries show a memory DVI interface, retained compiler state,
and separate document export. The first implementation of that separation here
uses LuaTeX's existing PDF drawing language so that font placement, math rules,
clipping, and TikZ transformations continue to come from the real backend.

The `stream` adapter retains the existing input-boundary process checkpoints. A
resumed child writes its drawing output to a Linux `memfd`, preserving the output
prefix expected by LuaTeX. After shipout, a small C adapter flushes the backend
buffer and reads the new bytes from that memory descriptor. Lua supplies glyph
coverage and page identity. An AF_UNIX message carries page commands to the worker;
only the requested page crosses the Windows/WSL pipe. MuPDF keeps its resource
document open and replaces the page's content stream without serializing or
reopening a PDF on the ordinary edit path.

Complete PDFs still seed the renderer at startup, during background convergence,
and on resource misses. A glyph/font signature absent from the seed, changed page
dimensions, a missing page-font resource, or external graphics resource operations
cause the suspended child to continue to a complete output. This refresh is
explicit in diagnostic results. It is slower but preserves rendering semantics.
The page stream is not a standalone PDF and is not DVI; a fully independent DVI
renderer is not required to test removal of per-edit document finalization.

The compiler pauses after the changed input returns, rather than at its first
shipout, so an error later in that input is not silently bypassed. The final input
pauses in `finish_pdffile` before final document work. Later input boundaries are
reused or replayed on demand; no unchanged-suffix equivalence is claimed.

The C adapter currently requires Linux LuaHBTeX 1.14 and its exported `pdf_flush`
and `static_pdf` symbols. It does not depend on private struct offsets. Lua callback
timing follows the installed LuaTeX manual: `finish_pdfpage` follows page-stream
assembly; `wrapup_run` follows closing output files. The latter makes complete
resource export safe from the retained memory descriptor. Other engine versions
must be adapted and tested before enabling this output path.

This decision changes output and renderer lifetime. It does not implement native
Windows state snapshots, arbitrary-source rollback, or a filesystem-free TeX
environment: source copies, logs, auxiliary state, and metadata still use the
isolated session directory. The `snapshot` adapter remains available as a
finalized-PDF comparison; `native` remains the full-build fallback.
