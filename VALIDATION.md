# Release validation: 0.1.0

Tested on Windows x64 with TeX Live and Ubuntu 22.04 under WSL.

| Check | Result |
| --- | --- |
| Extension configuration, project discovery, live edits, save handling, frame delivery | Passed |
| Chromium rendering, queued frames, collapsible compile-error header | 27 checks passed |
| WSL incremental vs. complete builds, including preamble PDF objects and error recovery | 54 checks passed |
| Windows incremental vs. complete builds: 30 pages, TikZ, fonts, reflow, mappings, repeated edits | Passed |
| Windows BibTeX, Biber, makeindex, PDF assets, concurrent sessions, crash recovery | 20 checks passed |
| Windows bundle with restricted PATH, Unicode paths, damaged cache repair | Passed |
| Windows compiler through Chromium: 100 pages, Chinese text, math, TikZ, navigation, error recovery | 26 checks passed |
| README GIF: real text, TikZ, figure, and table source edits | Passed |

Automated GitHub checks cover the extension and browser viewer. Full native
compiler checks require the local toolchains and TeX Live; they are not run by
GitHub Actions. These results do not establish compatibility with every LaTeX
package, TeX Live version, Windows installation, or WSL distribution.

The release includes SHA-256 checksums and the corresponding source materials.
Binaries are unsigned. Signing and clean-machine installation coverage remain
future release work.

## macOS port ? 0.1.1

Local Windows validation: Python compileall, the extension/viewer unit suite,
and `git diff --check` pass. Native macOS compilation, dependency auditing,
and extracted-VSIX edit/render comparisons are delegated to the macOS Actions
matrix; results will be recorded after those jobs finish. No local Mac runtime
or GUI extension-host validation has been performed.

The first macOS CI attempt exposed missing libraries in Ubuntu's repacked TeX
source; the Mac build now restores the same SHA-256-pinned upstream dependency
trees used by Windows. Local Linux controller rebuild and source-edit checks pass.
The one-page demo is unsuitable for `check_live_mode.py`'s later-page checkpoint
assertion; its render comparisons passed before that fixture-specific assertion.

`python scripts/check_posix_runtime.py` passes on Linux/WSL: long nested paths,
included-file edits resumed from a later-page checkpoint, exact fresh-render
equality, syntax-error recovery, and source preservation. The Mac package check
now runs the same fixture against the extracted release runtime.

The second Mac build exposed a classic-Mac conditional in the historical bundled
zlib under the modern Apple SDK. macOS now uses Apple's system zlib; other
engine dependency libraries remain statically linked from pinned sources.

Mac SDK build follow-up: corrected the historical libpng classic-Mac detection,
and retained exported engine symbols for the Lua checkpoint module. Inspection
of the TeX Live 2021 Mac binary confirmed LuaHBTeX 1.13.2; the explicit isolated
installer now installs our bundled 1.14 engine and regenerates its formats.
Python compileall and diff checks pass; native CI is still in progress.

The fourth Mac attempt reached engine compilation; it exposed unrelated optional
MetaPost/MFLua targets pulling in Cairo. The Mac configuration now disables those
targets explicitly and invalidates cached sub-configurations when flags change.
The Linux controller rebuild and POSIX checkpoint fixture still pass after the
accepted-socket blocking fix. Python compileall also passes.

The fifth ARM build reached final engine linking and exposed missing optional
libpng NEON objects in the historical makefile. The Mac recipe now selects
libpng's portable implementation. Syntax/diff validation passes.
