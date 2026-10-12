# Release notes

## 0.1.5 - First release

TeXAstra brings live LaTeX typesetting and precise source and document navigation
to VS Code on Windows x64, Ubuntu 22.04 WSL, and macOS 15+ (Apple Silicon and Intel).

- Live text, math, TikZ, figure, table, and Beamer editing.
- Source and document navigation and a collapsible compile-error header.
- LuaLaTeX incremental compilation and token navigation.
- PDFLaTeX character navigation and retained compiler updates on Linux/WSL with
  matching pdfTeX 1.40.22; full compilation with SyncTeX for other PDFLaTeX
  installations and XeLaTeX.
- Bibliography processing through the selected TeX installation.
- Platform packages, corresponding sources, licenses, and SHA-256 checksums.

Install one package from the [release](https://github.com/NoFixedPoint/TeXAstra/releases/tag/v0.1.5).
See [installation](README.md#install), [validation](VALIDATION.md), and
[licensing](LICENSING.md). Editing takes place in the source editor; rendered
pages support navigation and selection. TeX Live supplies document packages and
fonts. macOS requires the compatible isolated TeX Live 2021 setup described in
the installation guide.
