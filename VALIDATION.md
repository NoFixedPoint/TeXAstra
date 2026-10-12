# Release validation

## 0.1.1 - macOS preview

Both native jobs passed on **macOS 15.7.9**, using ARM64 and Intel x86-64
GitHub runners. The deployment target is macOS 15.0.

[CI run](https://github.com/NoFixedPoint/TeXAstra/actions/runs/38210954504) |
[Published preview](https://github.com/NoFixedPoint/TeXAstra/releases/tag/v0.1.1-macos)

| Check | Apple Silicon | Intel |
| --- | --- | --- |
| Native engine, controller and checkpoint module build | Passed | Passed |
| Architecture, ad-hoc signature and dynamic-library audit | Passed | Passed |
| Isolated TeX Live 2021 with matching LuaHBTeX 1.14 formats | Passed | Passed |
| Extension configuration, project discovery, editing, save and frame delivery | Passed | Passed |
| Extracted VSIX: text, TikZ, figure and table edits equal fresh compilation | Passed | Passed |
| Long nested paths and included-file edits resume a later-page checkpoint | Passed | Passed |
| Syntax-error recovery and unchanged project source | Passed | Passed |
| Published VSIX hashes match the tested packages | Passed | Passed |

The release build is `de4e64b44d87d8536399d25c00875aab44834e1b`.
[Published asset identities](results/macos-release-0.1.1.json),
[ARM package results](results/release-packages-darwin-arm64.json),
[Intel package results](results/release-packages-darwin-x64.json), and the
[ARM](results/macos-runtime-arm64.json) / [Intel](results/macos-runtime-x64.json)
dependency audits are recorded here. Package results and dependency audits
also accompany the corresponding release source archives.
All published VSIX/source-archive digests were checked against their checksum
manifests; both VSIX identities match the native test reports.

Local regression checks also passed: Linux engine/controller builds, 31 Linux
distribution checks, source-edit checks, the POSIX checkpoint fixture, extension
unit tests, Python compileall, and diff validation. The macOS runtime has no
Homebrew or Python runtime dependency.

Limitations: no interactive VS Code GUI run, Developer ID signing, notarization,
macOS 15.0-specific test, other macOS-version testing, or latency benchmark was
performed. Newer MacTeX formats are not assumed compatible. The initial
`check_live_mode.py` invocation against the one-page demo was unsuitable for its
later-page assertion; the dedicated two-page checkpoint fixture passes instead.

## 0.1.0 - Windows and WSL

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
