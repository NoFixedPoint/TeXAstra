# Incremental included-file edits — version 0.0.11

Editing an included chapter previously rebuilt the general-project compiler
session. Body `.tex` inputs can now resume a retained root paragraph checkpoint
before their first read. This covers `\input`, `\include`, computed filenames,
nested inputs, and files read multiple times. Source indexing is refreshed for
the edited file, preserving forward and reverse token navigation.

`prototype/inputs.lua` installs the existing buffered input reader before the
preamble and journals each successful open with the current root block number.
Block zero denotes preamble and other reads before the first body checkpoint.
The controller compares canonical paths and selects a retained checkpoint no
later than the earliest recorded read of the edited file. A file used both in
the preamble and body therefore requires a session rebuild.

The journal remains open across fork checkpoints. The existing descriptor restore
truncates it to the saved position on rollback, removing reads from the abandoned
suffix. The controller remembers which files it has previously observed, without
reusing their old block positions. If a partial replay has not reached a known
file yet, its absence from the current prefix proves that the surviving
checkpoints precede its next read. This lets a later chapter be edited while the
preview is still provisional, and allows dependencies to move after root edits.

Checkpoint placement is unchanged: there are no new checkpoints inside included
files. A long chapter replays from its entry block, and a repeated file resumes
before its earliest use. Preamble dependencies, non-`.tex` assets/packages,
unobserved files, missing dependency metadata, or lack of an earlier checkpoint
use the service's existing rebuild path. Coalesced edits to multiple files still
rebuild. Arbitrary file reads performed directly by external Lua modules are
outside this TeX input journal's coverage.

Ordinary edits retain provisional page output. New resources can still trigger a
complete resource export, and shrinking documents can retain the previous page
count until idle convergence. Convergence reconstructs the input history and
checkpoints for the new complete document. Generated files and edits remain in
the session cache; original project files are unchanged.

Validation uses `python scripts/check_included_edits.py` and records outcomes in
[included-edits.json](../results/included-edits.json): all 189 checks pass. The fixture compares exact
pixels with complete LuaLaTeX builds, checks source spans and forward navigation,
and exercises nested/repeated/computed inputs, `\include`, filenames with spaces,
newly introduced dependencies, body-only macro definitions, syntax-error recovery, growth and shrinkage, and
dependency history after rollback. The asynchronous service checks cover
checkpoint reuse, convergence, and preamble fallback with unsaved body overlays.
Timings in this correctness run are backend observations, not an end-to-end p95
benchmark.

Additional validation passes all 80 token-origin checks, 75 syntax checks, 344
checks on the 100-page C++ corpus, six mocked extension-command checks, and 13
Chromium scrolling/selection/error-recovery checks. The browser check now requires
an included-file edit to report checkpoint reuse. Validation ran with Linux
binaries through Ubuntu-22.04 WSL; the VS Code command was mocked, not exercised
in a real Extension Development Host.
