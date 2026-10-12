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
| README GIF: real text, TikZ, figure, and table source edits | Passed |

Automated GitHub checks cover the extension and browser viewer. Full native
compiler checks require the local toolchains and TeX Live; they are not run by
GitHub Actions. These results do not establish compatibility with every LaTeX
package, TeX Live version, Windows installation, or WSL distribution.

The release includes SHA-256 checksums and the corresponding source materials.
Binaries are unsigned. Signing and clean-machine installation coverage remain
future release work.
