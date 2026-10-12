# TeXAstra

**Write LaTeX. See it take shape.** Live typesetting and precise source ↔ document navigation in VS Code.

![Text, TikZ, figure, and table edits rendered live](https://raw.githubusercontent.com/NoFixedPoint/TeXAstra/master/assets/demo.gif)

*Real edits in the shared browser viewer, at recorded speed. In VS Code, edit the source and view the document beside it.*

## Install

### Windows and WSL

1. Install [VS Code](https://code.visualstudio.com/) and [TeX Live](https://www.tug.org/texlive/). For WSL, install TeX Live **inside Ubuntu 22.04** (`sudo apt install texlive-full`).
2. Download **[Windows x64](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.2/texastra-windows-x64.vsix)** (no WSL needed) or **[WSL](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.2/texastra-wsl.vsix)**. In VS Code, run **Extensions: Install from VSIX…** and choose the file. Install one variant.
3. Reload VS Code, open your trusted LaTeX project, and run **TeXAstra: Open Document**.

### macOS

1. On **macOS 15+**, install [VS Code](https://code.visualstudio.com/) and Python **3.11.8+** (needed only for the one-time TeX setup).
2. Download **[Apple Silicon](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.2/texastra-macos-arm64.vsix)** or **[Intel](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.2/texastra-macos-x64.vsix)**. In VS Code, run **Extensions: Install from VSIX…** and choose the file. Install one variant.
3. In Terminal, run the setup below, replacing `<extension-folder>` with the installed TeXAstra folder under `~/.vscode/extensions/`. In VS Code Settings, set `texastra.texBinDirectory` to the **absolute path printed by the script**.

   ```sh
   python3 "<extension-folder>/scripts/install_test_texlive.py" \
     --destination "$HOME/texastra-texlive-2021"
   ```

4. Reload VS Code, open your trusted LaTeX project, and run **TeXAstra: Open Document**.

The setup installs an isolated **TeX Live 2021** tree compatible with the bundled engine; your existing MacTeX stays unchanged. A newer MacTeX installation may be incompatible. Additional document packages must be installed separately.

Type in the source editor to update the document. Click rendered text to jump to its source; move the source cursor to find its output. Compile errors appear behind the collapsible header.

Optional: set `texastra.mainFile` for a project with multiple roots, or run **TeXAstra: Show LaTeX Environment** to check your installation. TeX Live supplies packages and fonts; MiKTeX is not supported.

[Build & test](BUILDING.md) · [Release notes](https://github.com/NoFixedPoint/TeXAstra/releases) · [Security](SECURITY.md)

Original code is [MIT](LICENSE); bundled GPL/AGPL components retain their licenses. See [licensing and source availability](LICENSING.md).
