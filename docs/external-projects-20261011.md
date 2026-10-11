# External LaTeX projects — version 0.0.7

Historical report. Version 0.0.8 replaces the command's compatibility-only mode
with [own live compilation and continuous scrolling](live-projects-20261011.md).

The extension previously discarded the configured main filename, always compiled
`main.tex`, and injected corpus-specific fonts, math and TikZ warm-up code. As a
result, pointing it at another folder was insufficient for normal documents.

## Behavior

- Discover the active document or its `% !TEX root` target, respecting the active
  workspace folder in a multi-root window. A configured main path takes precedence;
  a file picker handles projects without an obvious root.
- Preserve the actual filename and select XeLaTeX, pdfLaTeX or LuaLaTeX. Explicit
  `bakoma.latexCompiler` overrides `% !TEX program`; automatic selection defaults to
  LuaLaTeX when there is no compiler comment.
- Use ordinary full builds for external projects. No source instrumentation,
  warm-up code, compiler preload, checkpoint calls or provenance callbacks are
  injected. The C++ controller and MuPDF renderer are retained.
- Copy supported project assets below the main file's directory into a fresh
  `/tmp/bakoma-cpp-*` session. Apply unsaved buffers there, including initial dirty
  buffers before the first build. Subsequent edits reuse that session and auxiliary
  files instead of copying every asset again. Source files are never saved by the
  backend. Shell escape is disabled and TeX output paths use `openout_any=p`.
- Run at most three passes, comparing auxiliary state. Report failures and retain
  the stale visible preview; reject page navigation until a successful rebuild.
  Detach the previous PDF inode before rebuilding so the renderer cannot read a
  partially overwritten document. Page requests clamp to the available page range.
- Show an explicit full-build label and disable source navigation. Text selection,
  page navigation and preview updates remain available.
- Keep fork checkpoints as the default for the existing corpus. Internal snapshots
  remain opt-in. Automatic corpus detection uses its specific input/macro/TikZ
  signature; explicit incremental mode rejects unrelated documents.

## Validation

`node scripts/check_project.js` checks root discovery, explicit paths, filenames
with spaces, compiler precedence, missing roots and path containment (15 checks).

`python scripts/check_external_project.py` checks actual XeLaTeX, pdfLaTeX and
LuaLaTeX builds. It covers arbitrary filenames, root and included-file unsaved
edits, macros/math, page clamping, errors and recovery, and startup overlays through
the asynchronous extension protocol. An optional read-only project check verifies
its source tree's hashes before and after compilation. Aggregate results are in
[`results/external-projects.json`](../results/external-projects.json); private source,
figures and rendered pages are not committed.

The user's 85-page project compiled successfully with XeLaTeX. The initial observed
build took about 25 seconds, including project preparation and multiple compiler
passes; this is a compatibility result, not an incremental-performance result.
The first and last pages rendered. All 653 source-tree files retained their hashes.

The VS Code extension entrypoint is syntax-checked, root discovery is tested in
Node, and initial unsaved buffers are checked through the actual C++ protocol.
These checks do not constitute an automated end-to-end VS Code UI test.

## Remaining limits

Full mode recompiles the whole document. It provides no token or line-level source
synchronization, and does not satisfy the 150 ms editing target. The fast compiler
and provenance implementation have not been generalized to arbitrary projects.

Compilers, packages and fonts must be available in Ubuntu-22.04 WSL on Windows.
Assets outside the selected main directory, automatic BibTeX/Biber/index runs,
shell-escape packages and arbitrary generated build pipelines are not supported.
Existing `.bbl` files below the main directory are copied. Missing dependencies
appear in the preview diagnostics. Project copies and build outputs remain local.

For a read-only original, open a separate editable project copy. The compiler does
not modify originals, but a user's normal editor Save command writes the opened file.
