# Release validation

## 0.1.2 - macOS

Published as a regular release for Apple Silicon and Intel. Both native jobs
passed on **macOS 15.7.9**, targeting macOS 15.0 or later.

[CI run](https://github.com/NoFixedPoint/TeXAstra/actions/runs/38226791788) |
[Release](https://github.com/NoFixedPoint/TeXAstra/releases/tag/v0.1.2)

Both extracted VSIX packages passed the CV regression: a valid UTF-8 project
compiles and retains source mappings with an unrelated non-UTF-8 TeX file in
its folder. Text, TikZ, figure and table edits match fresh compilation, and
project files remain unchanged. Long paths, included-file checkpoints, syntax
error recovery, architecture, signatures and dependency audits also passed.

The build commit is `675f0075f2bba4e0f24ad54c600147b6ebb53745`. GitHub's uploaded
asset digests match the published checksum manifests; both VSIX digests match
the native test reports. See [asset identities](results/macos-release-0.1.2.json),
[Apple Silicon package checks](results/release-packages-darwin-arm64.json), and
[Intel package checks](results/release-packages-darwin-x64.json). The dependency
source archives also contain their corresponding validation reports.

Local extension unit checks, Python syntax compilation, source-index tests,
and the WSL compile/edit encoding regression passed before native CI.

Limitations: no interactive VS Code GUI test, Developer ID signing,
notarization, macOS 15.0-specific test, or broader OS matrix was performed.
The compatible TeX Live 2021 setup remains required. This release adds no
automatic dependency installation and contains macOS packages only;
Windows/WSL downloads remain at 0.1.0.

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
