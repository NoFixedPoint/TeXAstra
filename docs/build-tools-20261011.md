# Bibliography and index orchestration — 0.0.16

Complete builds now run BibTeX, Biber, and MakeIndex from the installed LaTeX
distribution. Opening a project no longer requires a prebuilt bibliography or
index. Ordinary body edits still restore compiler checkpoints immediately;
after two seconds of inactivity, the existing background worker regenerates
changed auxiliary outputs, converges the document, and adopts fresh checkpoints.
Bibliography, style, and preamble edits require a complete rebuild.

The engine/runtime remains our shipping responsibility. Executables, bibliography
styles, packages, and updates remain the external distribution's responsibility.
The current supported environment is still Ubuntu-22.04 WSL with TeX Live.
No package installation or update is performed.

## Detection and dependencies

`native/build_tools.hpp` owns tool discovery, execution, output reuse, and build
diagnostics. `Engine` calls it between complete LaTeX passes. The current `.fls`
recorder identifies generated control files, so obsolete `.bcf` and `.idx` files
left in a build directory do not independently trigger tools.

- A current job `.bcf` selects Biber. Its local data-source names and the complete
  control file participate in the fingerprint. Biber runs with `--noconf` so
  untracked user/system configuration cannot alter a cached result.
- Otherwise, bibliography-owning `.aux` files select BibTeX. Citation, database,
  and style directives are fingerprinted, recursively following included `.aux`
  files. Unrelated labels do not trigger another BibTeX invocation.
- Generated `.idx` files select MakeIndex. Index entry/page changes invalidate
  the output. A main document `paper.tex` uses `paper.ist` when present, including
  in live mode where the internal job name is `main`. Otherwise `<index-job>.ist`
  is used when present; without a style file, MakeIndex uses its defaults.

Database/style contents are hashed rather than relying on modification times.
Project files resolve in the isolated build directory; distribution files resolve
through `kpsewhich`. Executable path and size/modification stamp, arguments,
control data, and resolved input content determine the output-cache key.
Content-addressed outputs are published atomically below
`$XDG_CACHE_HOME/bakoma-revived/auxiliary-v2` (or `~/.cache/...`). Independent
background sessions can restore identical outputs without rerunning the tool.
Cached output content is checked against its stored digest before reuse.

The extension forwards unsaved `.bib`, `.bst`, `.ist`, `.bbx`, `.cbx`, and `.lbx`
changes. Generated `.bbl`, `.ind`, logs, and other build files remain in the user
cache; no build artifacts or editor buffer saves are written into the source
project. Generated text does not gain navigation back to database entries.

## Convergence and diagnostics

The build compares content hashes of `.aux`, `.toc`, `.out`, `.lof`, `.lot`,
`.nav`, `.snm`, `.ptc`, `.bcf`, `.idx`, `.bbl`, and `.ind` across passes. A tool run
or restored output requires another LaTeX pass. Six LaTeX passes is the limit,
including the initial priming pass. The last complete PDF remains usable when
the limit is reached, with a provisional flag and `convergence-limit` warning;
it is not labelled converged or reused as a converged startup cache. Further edits
rebuild instead of restoring checkpoints against unstable generated inputs.

Per-pass completion, failure, and active-process markers are cleared before
restarting. This fixes a prior multi-pass race: a long preamble could encounter
the previous pass's dead active child and be reported as a compilation failure.

Tools receive argument arrays directly, with no shell-built commands. Each runs
in its own process group, with cancellation and a 90-second limit. Failed runs
restore the preceding generated output, preventing a truncated `.bbl` or `.ind`
from blocking a subsequent repaired build. Missing executables identify the
required distribution tool; missing data names the input; failed commands include
their output. Tool warnings and stable-but-undefined citations/references appear
in frame warnings. Build diagnostics are captured once and retained for page
navigation rather than rereading logs on the interactive path.

Frames from complete builds expose `passes` and a `buildTools` array containing
`tool`, `input`, and `reused` for each auxiliary check. These records distinguish
actual tool runs from restored/unchanged output. Body-edit frames do not run or
report a new auxiliary build.

## Validation

The C++ backend rebuilt without warnings. The following checks passed locally:

| Suite | Checks | Coverage |
| --- | ---: | --- |
| `check_build_tools.py` | 77 | Real BibTeX, Biber, MakeIndex; exact pixels and selection against full builds; reopening and idle-worker reuse; unsaved databases, citations and index styles; included aux files; failures, recovery, missing inputs/tools, cancellation and six-pass bound |
| `check_cpp.py` | 346 | Existing 100-page differential rendering/edit regressions |
| `check_included_edits.py` | 189 | Retained edits, dependency invalidation and background adoption |
| `check_source_mapping.py` | 167 | Source mapping, math rules and localized failures |
| `check_external_project.py` | 25 | LuaLaTeX, XeLaTeX and pdfLaTeX full-build paths, overlays, error recovery and source preservation |
| `check_extension_live.js` | 12 | Mock VS Code host, including forwarding unsaved bibliography and style edits |

Total: **816 checks**. Reports are in [build-tools.json](../results/build-tools.json),
[cpp-correctness.json](../results/cpp-correctness.json),
[included-edits.json](../results/included-edits.json),
[source-mapping.json](../results/source-mapping.json),
[external-projects-tools.json](../results/external-projects-tools.json), and
[extension-live.json](../results/extension-live.json).

The VSIX is built and byte-verified by `scripts/package_extension.py`; its version
and runtime hashes are recorded in [package-0.0.16.json](../results/package-0.0.16.json).
It is not installed automatically. No new latency claim is made: the existing
0.0.15 browser measurements still exceed the 150 ms p95 target for typing bursts
and new fonts. Actual VS Code host performance has not been measured here.

## Remaining limits

This supports literal local Biber data sources and conventional BibTeX/MakeIndex
jobs. Remote/globbed data sources, Biber configuration files, custom command
chains/options, Xindy, glossary tools, and bibliography-to-source navigation are
not implemented. Packages that invoke their own index tools through shell escape
retain their own behavior; this orchestrator does not interpret package-specific
tool options. For orchestrated MakeIndex use the conventional `.idx` workflow.

General assets outside the main document directory, distribution discovery,
compatibility preflight, and live watching of external package updates remain
future work. Reopen the preview after distribution or externally saved dependency
changes. A tool's transitive runtime libraries are not fingerprinted individually;
the tool cache, like the existing build cache, has no automatic eviction policy.
