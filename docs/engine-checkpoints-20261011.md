# Engine checkpoints — version 0.0.12

Edits late in an included chapter can now resume near the edited paragraph.
Previously, the entire included file replayed from its entry in a generated root
block. The live compiler now processes original root and included sources through
a startup wrapper and retains checkpoints at safe points in the TeX interpreter.
`native/document.hpp`, the handwritten splitter, and the fixed paragraph driver
have been removed. Computed document boundaries and more than 2,048 paragraphs
are supported by this path.

[ADR 0008](adr/0008-engine-checkpoints.md) describes checkpoint safety and input
read positions. Read-ahead is deliberately conservative: buffered lines and macro
arguments may already be consumed before their output appears. Such edits restore
an earlier checkpoint. Active readers reopen on rollback, and source tables and
prefix mappings survive edits inside open files. Preamble dependencies, package
changes, and coalesced edits to multiple files retain their session rebuild path.

Run `python scripts/build_engine.py`, then `python scripts/build_cpp.py`, followed
by `python scripts/check_engine_checkpoints.py`. The new differential fixture has
a 12-page included chapter with no root paragraph checkpoints. Late edits resume
checkpoint 10, with exact full-build pixels and source spans. It also checks
unchanged-page mappings, length-changing edits, new paragraphs, syntax-error
recovery, EOF appends, root edits with retained chapter changes, long macro
arguments, computed document start, and a root with 2,100 paragraph boundaries.
Results and backend timing observations are in
[engine-checkpoints.json](../results/engine-checkpoints.json). These are correctness
runs, not a controlled end-to-end latency benchmark.

Validation passed 67 engine-checkpoint checks, 189 included-edit checks, 80
token-origin checks, 75 syntax checks, 344 C++ corpus checks, 38 general-project
checks, six mocked extension-command checks, and 13 Chromium checks. The
general-project run also verifies cache reuse and unchanged original files; its
results are in [engine-live-fixture.json](../results/engine-live-fixture.json).
The engine runs under Ubuntu-22.04
WSL on Windows. VS Code command checks use mocked APIs; browser checks exercise
the shared renderer and real backend. Native Windows/macOS checkpointing remains
unimplemented.

There is still at most one retained checkpoint per physical page. A long
paragraph or box can span several pages without an eligible interpreter boundary.
Source IDs retain their existing limit of 2,146 registered files and fewer than
one million Unicode characters per file; the root now shares that whole-file
limit. New fonts/resources may require a complete resource export, and idle
convergence still completes the document and refreshes checkpoints.
