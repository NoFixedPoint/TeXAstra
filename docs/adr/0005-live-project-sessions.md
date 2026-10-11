# Own the live compilation session for ordinary projects

Opening the experimental preview must activate token synchronization and live
updates independently of whichever compiler or PDF the user previously used.
The command therefore always launches the C++ controller and LuaHBTeX live path.
Root discovery remains configurable; old engine/compiler/full-preview settings
cannot silently select a preview without provenance. The full-build CLI remains
available for differential tests.

For an ordinary root document, `LiveDocument` separates its preamble, body, and
end-document suffix. It splits body input at paragraph boundaries outside macro
arguments, math and environments. A fixed driver inputs the generated blocks.
The driver survives restoration even when edits change the number of blocks.
One retained checkpoint per newly shipped physical page saves the partially
built page, floats, macros and compiler state before the next safe block. An edit
restores the latest checkpoint preceding the changed block. Since version 0.0.11,
included `.tex` edits also reuse checkpoints: a journal of actual TeX input reads
identifies the first affected root block. Preamble dependencies and inputs without
usable history reconstruct the session. See [the included-edit design and checks](../included-edits-20261011.md).
The existing acceptance corpus
continues to use its explicit page-file checkpoints; fork remains the default.

The general source instrumenter retains original Unicode offsets and UTF-16
editor positions across generated blocks. Ordinary supported text and math use
token attributes; unrecognized macros/environments use their invocation range.
Literal body inputs are instrumented recursively. It is a bounded scanner, not a
TeX macro-expansion parser. Preamble inputs and computed filenames do not receive
the same coverage. Brace-delimited attribute setters preserve source whitespace;
control-word delimiters and blank-line paragraph tokens must also be preserved.
Generated driver lines end in `%` to avoid adding glue. These details are checked
against uninstrumented LuaLaTeX pixels, not merely against another instrumenter.

MuPDF's synthetic Unicode continuation entries for ligatures have no additional
physical glyph. The trace excludes these entries. On glyph-count mismatch it
also tries a page-operator trace excluding form XObjects, since imported PDF
figures have no corresponding TeX glyph nodes. Mapping is installed only when
the resulting counts agree. Imported figure text remains outside token mapping.

Each project uses a locked directory in the user's WSL/Linux cache, outside the
project. Source copies, generated blocks, logs, auxiliaries and resource seeds
persist there. Input hashes, runtime identity, compiler identity and external
dependency stamps gate reuse of converged build data. Reopening still reconstructs
live process checkpoints. Concurrent sessions and background convergence use
separate locked directories; successful convergence atomically updates a registry
pointer. Stale PID files are removed without signalling their historical PIDs.
The cache currently has no automatic eviction policy.

The viewer reserves continuous page-sized placeholders and loads nearby page
images and selectable text. Offscreen decoded images and text layers are evicted.
Page and forward-sync requests are queries: they do not advance the source
revision or cancel an idle convergence build. Source revisions and compiler
generations guard against stale payloads and navigation. A source lookup can
resolve an unloaded physical page, fetch it, scroll to its region, and display
the caret. The same viewer works in the VS Code webview and browser demo.
When a token occurs in both a heading and the contents or running header, forward
navigation prefers the occurrence nearest the current viewport. Included-file
instrumentation saves and restores its caller's source attribute. Shipout tracing
also visits leader boxes, so repeated contents-page dots remain in glyph order.

Resource-refresh continuation must drain subsequent page publishers while
waiting for a complete seed PDF. Otherwise the compiler can suspend after another
paragraph while the controller waits forever for finalization. Retained-page
updates still avoid complete export when all required resources are present.

The compiler remains LuaHBTeX 1.14 on Linux/WSL. This change does not make
XeLaTeX-specific documents universally compatible or implement native Windows
compiler snapshots. Generated files remain real files in the user cache; the
ordinary page-drawing transport remains memory backed.
