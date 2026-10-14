# Release validation

## TeXAstra 0.1.5

The release uses extension version 0.1.5 on Windows x64, Ubuntu 22.04 WSL,
Apple Silicon macOS, and Intel macOS. Native macOS builds target macOS 15.0.

### Packaged runtimes

Each VSIX is extracted into a path containing spaces. Package checks exercise:

- Compilation and source mappings with an unrelated legacy-encoded TeX file.
- Text, TikZ, figure, and table edits matching a fresh compilation exactly.
- Preservation of every original project file.

Windows/WSL checks run locally. Both macOS architectures build and run checks on
native GitHub Actions runners. macOS checks also audit architecture, ad-hoc
signatures, dependencies, long paths, included-file checkpoints, and syntax-error
recovery. macOS release directories include package validation reports under
`validation/` beside the matching source archives.

### Smaller republished 0.1.5 packages

Separating build-source archives reduces the published VSIX downloads as follows
(decimal MB):

| Package | Original | Replacement | Reduction |
| --- | ---: | ---: | ---: |
| WSL | 221.5 MB | 27.7 MB | 87.5% |
| Windows x64 | 193.1 MB | 17.9 MB | 90.7% |
| macOS Apple Silicon | 303.6 MB | 22.0 MB | 92.8% |
| macOS Intel | 304.4 MB | 22.9 MB | 92.5% |

Runtime binaries, retained runtime files, and executable permissions match the
original published packages byte-for-byte. Removed archives are preserved in
the companion source ZIPs. The release text and all ten asset names are unchanged.
The collector changes only source-reference file contents in the tested VSIXs
and regenerates checksums; its report records both tested and published hashes.

`python scripts/check_package_sources.py` checks all five target layouts,
unchanged executable/license contents, preservation of source/build recipes,
and rejection of missing, altered, or mismatched source kits. This check also
runs in CI. `node scripts/check_unit.js` and Python syntax checks pass.
`python scripts/check_release_packages.py` validates both smaller Windows/WSL
packages, their source ZIP integrity, source mappings, project preservation, and
text/TikZ/figure/table edits against complete compilation. Release collection
checks the source ZIP hashes before writing checksums.

Both smaller Mac packages passed native architecture/signature checks and the
full extracted-package suite in [the repackaging workflow](https://github.com/NoFixedPoint/TeXAstra/actions/runs/38329557732).
They reuse the SHA-256-pinned original released binaries; no compiler rebuild was
needed. [Runtime preservation](results/repackage-runtime-preservation.json) and
[publication verification](results/release-small-0.1.5.json) record package sizes,
source preservation, uploaded asset hashes, unchanged release text, and removal
of superseded Actions package artifacts. Interactive VS Code GUI testing and a
broad OS compatibility matrix remain outside this validation.

### Compiler and navigation coverage

Linux/WSL pdfTeX 1.40.22 checks cover character provenance, retained state,
output-prefix restoration, earlier/later edits, preamble invalidation, error
recovery, consumed definitions, input streams, and reference convergence.
The validated 55-page PDFLaTeX fixture matches stock rendering before and after
an unsaved edit, with original project files preserved.

Windows/WSL coverage also includes citation startup, compiler selection, Beamer
navigation, and LuaLaTeX source mapping. Extension checks exercise configuration,
project discovery, document opening, saves, and frame delivery. Python syntax
checks cover the engine, scripts, and Python package.

### Scope and limits

Windows/WSL testing uses one Windows machine with Ubuntu 22.04 WSL. There is no
clean-machine or broad OS compatibility matrix, or interactive VS Code GUI
validation. Automated browser and engine checks do not establish general
Unicode or package compatibility. XeLaTeX rendering is not independently tested.

Retained pdfTeX updates are available on Linux/WSL with matching pdfTeX 1.40.22.
Other PDFLaTeX versions/platforms and XeLaTeX use external compilation with
SyncTeX. Retained updates compile the remaining suffix into a complete PDF.

Windows binaries are unsigned. macOS binaries are ad-hoc signed, not Developer
ID signed or notarized. macOS 15.0 itself is not tested. macOS requires the
compatible isolated TeX Live 2021 setup; newer MacTeX formats are not assumed
compatible. The selected TeX installation supplies document packages and fonts.
Automatic dependency installation and MiKTeX integration are not supported.

Private project sources and rendered documents are excluded from release materials.

### Release evidence

The original full-size native macOS builds passed in [GitHub Actions](https://github.com/NoFixedPoint/TeXAstra/actions/runs/38321363874).
[Release preflight](results/release-preflight-0.1.5.json),
[Windows/WSL package checks](results/release-packages.json),
[Apple Silicon checks](results/release-packages-darwin-arm64.json), and
[Intel checks](results/release-packages-darwin-x64.json) record the tested package identities.

### Automatic macOS setup in the replacement 0.1.5 packages

[Native validation](https://github.com/NoFixedPoint/TeXAstra/actions/runs/38503902074)
passed on macOS 15 Apple Silicon and Intel at commit `48c2813`. Both jobs installed
TeX Live through the extension's JavaScript setup code into paths containing
spaces, generated matching formats, compiled LuaLaTeX and PDFLaTeX documents,
and reused the completed installation. Extension tests cover cancellation,
failed-install cleanup/retry, explicit settings, trust, and waiting before launch.
Runtime audits, PDFLaTeX provenance/state/navigation checks, and extracted-package
rendering and source-navigation checks also passed. The first Intel package run
failed during a retained TikZ edit; the unchanged job passed on retry. This does
not establish interactive VS Code GUI coverage or broader OS compatibility.

Publication uses the existing macOS VSIX/source asset names, verifies the tested
package hashes and source kits, changes only source references during collection,
and regenerates release checksums. Windows/WSL assets keep their existing hashes.

[Publication verification](https://github.com/NoFixedPoint/TeXAstra/actions/runs/38505106843)
confirmed all ten uploaded asset identities and their SHA-256 digests. The
published Apple Silicon VSIX is `6eb1d929696bf6b2b29141f6a870df0caf409b49f1f61843a60cf6120ca074e2`;
the Intel VSIX is `0e32f582298c3fd64acb214f60e30cee5b09d095cce94550c1ced66f6c06506f`.
