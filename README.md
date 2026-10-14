# TeXAstra

**Write LaTeX. See it take shape.** Live typesetting and precise source ↔ document navigation in VS Code.

![Text, TikZ, figure, and table edits rendered live](https://raw.githubusercontent.com/NoFixedPoint/TeXAstra/master/assets/demo.gif)

*Real edits in the shared browser viewer, at recorded speed. In VS Code, edit the source and view the document beside it.*

## Install

### Windows and WSL

1. Install [VS Code](https://code.visualstudio.com/) and [TeX Live](https://www.tug.org/texlive/). For WSL, install TeX Live **inside Ubuntu 22.04** (`sudo apt install texlive-full`).
2. Download **[Windows x64](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.5/texastra-windows-x64.vsix)** (no WSL needed) or **[WSL](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.5/texastra-wsl.vsix)**. In VS Code, run **Extensions: Install from VSIX…** and choose the file. Install one variant.
3. Reload VS Code, open your trusted LaTeX project, and run **TeXAstra: Open Document**.

### macOS

1. On **macOS 15+**, install [VS Code](https://code.visualstudio.com/).
2. Download **[Apple Silicon](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.5/texastra-macos-arm64.vsix)** or **[Intel](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.5/texastra-macos-x64.vsix)**. In VS Code, run **Extensions: Install from VSIX?** and choose the file.
3. Open your trusted LaTeX project and run **TeXAstra: Open Document**. First use automatically downloads and prepares compatible TeX Live; allow a few minutes.

No Python, Terminal commands, or settings changes are needed. Existing MacTeX stays unchanged. [Setup details and troubleshooting](docs/macos.md).

Type in the source editor to update the document. Click rendered text to jump to its source; move the source cursor to find its output. Compile errors appear behind the collapsible header.

Optional: set `texastra.mainFile` for a project with multiple roots, or run **TeXAstra: Show LaTeX Environment** to check your installation. TeX Live supplies packages and fonts; MiKTeX is not supported.

`texastra.compiler` defaults to `auto`, following the root's `% !TEX program`
comment or saved `.log`, then falling back to LuaLaTeX. PDFLaTeX supports
**character-level source sync and retained compiler updates** with matching
pdfTeX 1.40.22; other versions and XeLaTeX use SyncTeX line navigation.
LuaLaTeX provides incremental updates and token-level navigation. Reopen the
document after changing the compiler setting.

[Build & test](BUILDING.md) · [Release notes](https://github.com/NoFixedPoint/TeXAstra/releases) · [Security](SECURITY.md)

Motivated by [BaKoMa-Tex](https://bakoma-tex.daniel-aldrich.ca/) and [TexPresso](https://github.com/let-def/texpresso).

Original code is [MIT](LICENSE); bundled GPL/AGPL components retain their licenses. See [licensing and source availability](LICENSING.md).
