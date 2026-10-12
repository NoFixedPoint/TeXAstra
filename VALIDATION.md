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
recovery. Matching macOS source archives include package validation reports.

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

Both native macOS jobs passed in [GitHub Actions](https://github.com/NoFixedPoint/TeXAstra/actions/runs/38321363874).
[Release preflight](results/release-preflight-0.1.5.json),
[Windows/WSL package checks](results/release-packages.json),
[Apple Silicon checks](results/release-packages-darwin-arm64.json), and
[Intel checks](results/release-packages-darwin-x64.json) record the tested package identities.
