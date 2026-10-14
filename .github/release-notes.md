TeXAstra brings live LaTeX typesetting and precise source and document navigation to VS Code.

**First release for Windows, WSL, and macOS.**

- Edit text, math, TikZ, figures, tables, and Beamer presentations with live rendering.
- Navigate between source and output and inspect compile errors in a collapsible header.
- Use LuaLaTeX with incremental compilation and token navigation, or select PDFLaTeX or XeLaTeX.
- On Linux/WSL, matching pdfTeX 1.40.22 provides character navigation and retained compiler updates. Other PDFLaTeX installations and XeLaTeX use full compilation with SyncTeX source-line navigation.
- Process bibliographies using tools from the selected TeX installation.

### Install

Install VS Code; Windows/WSL also need TeX Live. Download **one** package:

| Asset | Use |
| --- | --- |
| `texastra-windows-x64.vsix` | Native Windows x64; no WSL or Python needed |
| `texastra-wsl.vsix` | Windows VS Code with TeX Live inside Ubuntu 22.04 WSL |
| `texastra-macos-arm64.vsix` | Native Apple Silicon VS Code; macOS 15+ |
| `texastra-macos-x64.vsix` | Intel VS Code; macOS 15+ |

Run **Extensions: Install from VSIX...**, reload VS Code, open a trusted LaTeX project, and run **TeXAstra: Open Document**.

On macOS, first use automatically installs compatible TeX Live 2021 with progress and cancellation. No Python, Terminal commands, or settings changes are needed; existing MacTeX stays unchanged. See the [installation instructions](https://github.com/NoFixedPoint/TeXAstra#install) and [build guide](https://github.com/NoFixedPoint/TeXAstra/blob/master/BUILDING.md).

Editing takes place in the source editor; rendered pages provide navigation and selection. The selected TeX installation supplies packages and fonts. Automatic dependency installation and MiKTeX integration are not supported.

### Validation

Release checks exercise the extracted platform runtimes, source navigation, preservation of project files, and text, TikZ, figure, and table rendering against fresh compilation. Native macOS checks also audit architecture, signatures, and library dependencies. See [validation and scope](https://github.com/NoFixedPoint/TeXAstra/blob/master/VALIDATION.md).

Interactive VS Code GUI testing and a broad OS compatibility matrix are not included. Windows binaries are unsigned; macOS binaries are ad-hoc signed.

### Sources and integrity

Original code is MIT except identified upstream-derived material. Bundled compiler and renderer components retain their GPL/AGPL licenses. Matching project and dependency sources are supplied in `texastra-sources.zip`, `texastra-darwin-arm64-sources.zip`, and `texastra-darwin-x64-sources.zip`.

`SHA256SUMS` covers all four VSIX packages and all three source archives. Use the supplied archives for complete corresponding sources; GitHub's automatic source download does not include dependency source kits.
