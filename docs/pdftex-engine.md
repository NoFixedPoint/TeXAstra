# Native pdfTeX provenance and retained updates

The Linux/WSL and macOS runtimes can build actual pdfTeX 1.40.22 from the existing
checksum-pinned, security-patched TeX Live sources:

```sh
python scripts/build_pdftex.py
python scripts/build_cpp.py
python scripts/check_pdftex.py
python scripts/check_citations.py --output citations-pdftex-provenance.json
```

`engine/pdftex_patch.py` applies checked edits to Web2C's generated C. The WEB
typesetting algorithms, memoryword layout, format ABI, line breaking, font
metrics, and PDF position/rounding calculations are unchanged. A separate
array carries source spans through scanning, token lists, macro arguments,
stored definitions, character nodes, copied boxes, ligatures, and math fields.
Project literal macro text points to its definition; untracked package text
can inherit a macro invocation. These destinations are source origins, not a
claim that every rendered character has a unique editable source character.

PDF marked-content scopes carry the ID and length of each emitted glyph's
origin. They split only the syntax of the existing TJ string/array, preserving
pdfTeX's positioning accumulators. The renderer reads these scopes and uses the
actual transformed glyph geometry. Input sources are indexed, never rewritten.
UTF-8 byte offsets are converted to source scalar/UTF-16 editor coordinates.
External PDF forms remain deliberately unmapped.

The controller enables this engine only when the selected pdfTeX version
matches. Other versions and native Windows retain their existing compiler
and SyncTeX path; the bundled engine must not silently replace a different
version's typesetting. The macOS build includes this engine on both Apple Silicon
and Intel; its validation uses the isolated TeX Live 2021 tree described in
[BUILDING.md](../BUILDING.md#macos-apple-silicon-and-intel).

Validation on 2026-10-12: `results/pdftex.json` covers repeated words, reordered
arguments, captured definitions, ligatures, copied boxes, math, included files,
and character-level navigation. Both article pages match stock PDFLaTeX pixels
exactly. `results/citations-pdftex-provenance.json` validates all citation variants,
three Beamer pages against stock PDFLaTeX, browser navigation, stale-response
rejection, and unsaved included-file edits. These checks do not establish
universal correctness for arbitrary packages, virtual fonts, or encodings.

## Retained compilation

On Linux/WSL and macOS, `engine/pdftex_state.c` forks dormant compiler snapshots at project
scanner boundaries. Fork retains the complete TeX/token/node/provenance state,
PDF objects, font resources, compression buffers, and C stacks. This avoids
trying to reproduce the engine's private object graph in an external serializer.

Each snapshot records full input-line read frontiers. The controller compares
hashes of every consumed source prefix before resuming; a definition captured
on an earlier page invalidates later snapshots even if its text is displayed
much later. Package/font/graphics dependencies and the source manifest must
also remain unchanged. A changed document class or unsupported snapshot falls
back to full compilation.

Writable descriptors and already-closed recorder outputs have immutable prefix
copies (Linux memfds or unlinked session-local files on macOS). Resume restores
these bytes, positions, and file descriptions, removes
outputs created after the checkpoint, and refreshes source indices. TeX input
streams are repositioned to their saved logical offsets so libc's read-ahead
cannot conceal an unsaved edit. Output outside the generated session disables
that checkpoint. Original project files are never checkpoint output targets.

The controller owns the checkpoint process groups and terminates them when the
session closes or a full rebuild replaces them. Retention is bounded to 12
preamble/first-page states and 64 subsequent page states after a pass; capture
is limited to 256 states per compiler lineage. This trades memory for avoiding
repeated package loading and prefix typesetting. No state is reused across
application sessions.

macOS resolves descriptor paths with `F_GETPATH`, scans the process descriptor
limit, and uses POSIX sockets with close-on-exec flags. The controller connects
through its private short socket-directory symlink, so deeply nested projects
do not exceed Darwin's Unix socket path limit. These changes preserve the same
source-prefix validation, rollback, and process-group ownership as Linux.

The current implementation resumes through the document's remaining suffix and
finalizes a complete PDF. It does **not** yet stop at the visible page or skip an
unchanged suffix. Reference/bibliography changes still trigger convergence passes.
It is retained-state updating, not a promise of sub-frame latency on every deck.

`scripts/check_pdftex_state.py` verifies closed-output rollback, recovery after
a failed edit, captured-definition invalidation, and reference convergence against
fresh PDFLaTeX pixels. `scripts/check_pdftex_project.py PROJECT MAIN --edit-title
TITLE --page N` validates a real project without changing its files. On the
reported 55-page deck, the tested title edit restored after 33 pages and completed
in about 2.1 seconds, versus about 8.4 seconds for the cold converged build. These
are local compiler timings, not end-to-end browser latency measurements.

## macOS port validation (2026-10-13)

`build_macos.py` builds and signs pdfTeX, includes its license and build metadata,
and supplies the corresponding source kit. Both macOS CI architectures now run
the provenance and retained-state suites. The runtime audit checks pdfTeX's
architecture, signature, dependencies, and recorded binary hash. The packaged
runtime check also requires character navigation and retained included-file
edits under long paths, fresh-build pixel equality, and error recovery.

Local validation used the rebuilt Linux runtime through Ubuntu-22.04 WSL:
39 [provenance/navigation/pixel checks](../results/pdftex-macos-port-wsl.json),
28 [adversarial retained-state checks](../results/pdftex-state.json),
the [long-path PDFLaTeX check](../results/posix-runtime-pdftex.json), and the
JavaScript unit suite passed. Python syntax
and Git whitespace checks passed. Native macOS compilation, signatures, and
execution could not be tested on this Windows host; the ARM64 and Intel CI jobs
must pass before shipping Mac binaries. No macOS performance claim is made.

Descriptor-path handling follows Apple's [`F_GETPATH` definition](https://github.com/apple/darwin-xnu/blob/main/bsd/sys/fcntl.h).
