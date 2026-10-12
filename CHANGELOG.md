# Release notes

## 0.1.1 ? macOS preview

- Native Apple Silicon and Intel macOS VSIX builds, targeting macOS 15+.
- Darwin process control, short Unix-socket paths, and file-backed checkpoints.
- MacTeX discovery and an explicit isolated TeX Live 2021 setup with matching
  LuaHBTeX 1.14 formats.
- Architecture and dynamic-library audits, ad-hoc signing, complete source kits,
  and extracted-package rendering/checkpoint checks in the macOS Actions matrix.

See the [macOS guide](docs/macos.md) for build and installation commands.
The macOS preview is separate from the Windows/WSL 0.1.0 release. It is not
Developer ID signed or notarized, and no interactive VS Code GUI test is claimed.

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
