# TeXAstra

**Write LaTeX. See it take shape.** Live typesetting and precise source ↔ document navigation in VS Code.

![Text, TikZ, figure, and table edits rendered live](https://raw.githubusercontent.com/NoFixedPoint/TeXAstra/master/assets/demo.gif)

*Real edits in the shared browser viewer, at recorded speed. In VS Code, edit the source and view the document beside it.*

## Install

1. Install [VS Code](https://code.visualstudio.com/) and [TeX Live](https://www.tug.org/texlive/). For WSL, install TeX Live **inside Ubuntu 22.04** (`sudo apt install texlive-full`).
2. Download **[Windows x64](https://github.com/NoFixedPoint/TeXAstra/releases/latest/download/texastra-windows-x64.vsix)** (no WSL needed) or **[WSL](https://github.com/NoFixedPoint/TeXAstra/releases/latest/download/texastra-wsl.vsix)**. In VS Code, run **Extensions: Install from VSIX…** and choose the file. Install one variant.
3. Reload VS Code, open your trusted LaTeX project, and run **TeXAstra: Open Document**.

Type in the source editor to update the document. Click rendered text to jump to its source; move the source cursor to find its output. Compile errors appear behind the collapsible header.

Optional: set `texastra.mainFile` for a project with multiple roots, or run **TeXAstra: Show LaTeX Environment** to check your installation. TeX Live supplies packages and fonts; MiKTeX is not supported. The native macOS
preview targets macOS 15+ on Apple Silicon and Intel; see the
[macOS build and installation guide](docs/macos.md) for its TeX Live 2021 requirement.

[Build & test](BUILDING.md) · [Release notes](https://github.com/NoFixedPoint/TeXAstra/releases) · [Security](SECURITY.md)

Original code is [MIT](LICENSE); bundled GPL/AGPL components retain their licenses. See [licensing and source availability](LICENSING.md).
