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

**Automatic setup is implemented for the next release; the published v0.1.5
downloads below still use the legacy setup.** With a package built from this checkout:

1. On **macOS 15+**, install [VS Code](https://code.visualstudio.com/).
2. In VS Code, run **Extensions: Install from VSIX…** and choose the TeXAstra package for Apple Silicon or Intel.
3. Open your trusted LaTeX project and run **TeXAstra: Open Document**. On first use, TeXAstra downloads and prepares its compatible TeX Live automatically, then opens the preview.

No Python, Terminal commands, folder selection, or settings changes are needed.
First-time setup needs internet access and can take several minutes; progress and
a Cancel button appear in VS Code. Run **Open Document** again to retry a failed
or cancelled setup. Later uses reuse the installation.

TeXAstra manages an isolated **TeX Live 2021** tree in VS Code's extension storage;
your existing MacTeX stays unchanged. An explicit `texastra.texBinDirectory`
setting takes precedence and skips automatic setup. Additional document packages
must be installed separately. See [setup details and troubleshooting](docs/macos.md).

<details>
<summary>Published v0.1.5: downloads and legacy setup</summary>

1. Install Python **3.11.8+** for the one-time setup.
2. Download **[Apple Silicon](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.5/texastra-macos-arm64.vsix)** or **[Intel](https://github.com/NoFixedPoint/TeXAstra/releases/download/v0.1.5/texastra-macos-x64.vsix)** and install it with **Extensions: Install from VSIX…**. Install one variant.
3. In Terminal, run the setup below, replacing `<extension-folder>` with the installed TeXAstra folder under `~/.vscode/extensions/`. Set `texastra.texBinDirectory` to the **absolute path printed by the script** in VS Code Settings.

   ```sh
   python3 "<extension-folder>/scripts/install_test_texlive.py" \
     --destination "$HOME/texastra-texlive-2021"
   ```

4. Reload VS Code, open your trusted LaTeX project, and run **TeXAstra: Open Document**.

The legacy setup also installs an isolated compatible tree; a newer MacTeX may
be incompatible with the bundled engine.

</details>

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
