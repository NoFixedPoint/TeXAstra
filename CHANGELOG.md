# Release notes

## 0.1.0

- Live LaTeX typesetting with source ↔ document navigation in VS Code.
- Incremental text, math, TikZ, image, and table updates.
- White document canvas and a persistent, collapsed compile-error header.
- Separate Windows x64 and Ubuntu 22.04 WSL packages, with matching source archives.

Install one VSIX variant from the release. TeX Live must be installed in the
selected environment; it supplies packages, fonts, bibliography tools, and indexes.
The Windows variant runs without WSL or Python.

This first public release uses manual installation and unsigned binaries.
Validation covers Windows x64 and Ubuntu 22.04 under WSL on one machine, not a
clean-machine or broad compatibility matrix. There is no macOS, ARM, or MiKTeX
support. Editing takes place in the source editor; the rendered page provides
navigation and selection. See [validation](VALIDATION.md) and [licensing](LICENSING.md).
