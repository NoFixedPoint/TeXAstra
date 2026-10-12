# TeXAstra

Interactive LaTeX editing for VS Code. TeXAstra typesets your document as you write and connects rendered text, mathematics, and supported TikZ content to their source.

## Install and open a document

The default Windows package uses WSL with TeX Live installed in that distribution.

```powershell
code --install-extension artifacts/texastra-0.0.28.vsix --force
```

Reload VS Code, open your LaTeX project, and run **TeXAstra: Open Document** from the Command Palette. TeXAstra discovers the main file from the active document, its `% !TEX root` comment, or `main.tex`. You can also select a file when prompted.

Edit in the VS Code source editor. The document updates beside it. Click rendered content to select the corresponding source, or move the source cursor to locate its output. Drag across a page to select rendered text, and scroll to move between pages.

The **Compile errors** header stays visible. It turns red when an error occurs; click it to read the details. Its expansion state stays under your control. The last successful rendering stays visible while you correct the source.

## Settings

| Setting | Purpose |
| --- | --- |
| `texastra.mainFile` | Main `.tex` file, relative to the workspace or absolute. |
| `texastra.projectRoot` | Directory containing the document and shared assets. Defaults to the containing workspace. |
| `texastra.runtimeMode` | `wsl` for the default Windows package; `native` for the separate Windows runtime. |
| `texastra.wslDistribution` | WSL distribution containing TeX Live. Empty selects an available distribution. |
| `texastra.texBinDirectory` | TeX Live binary directory. Empty discovers the installation. |

For example:

```json
{
  "texastra.mainFile": "paper/main.tex",
  "texastra.runtimeMode": "wsl",
  "texastra.wslDistribution": "Ubuntu-22.04"
}
```

Run **TeXAstra: Show LaTeX Environment** to inspect the selected installation and tools. Reopen the document after changing runtime settings. Existing settings from the previous extension name remain readable; explicit `texastra.*` settings take precedence.

## Runtime and compatibility

TeXAstra bundles its LuaHBTeX typesetting engine and renderer. Your TeX Live installation supplies document classes, packages, fonts, BibTeX, Biber, and MakeIndex. Install or update those through TeX Live's package manager.

Generated files stay in the TeXAstra user cache. Linux and WSL use `$XDG_CACHE_HOME/texastra` or `~/.cache/texastra`; native Windows uses `%LOCALAPPDATA%/texastra`. Unsaved editor buffers participate in compilation. Saving those buffers preserves the live session, while external source and asset changes trigger updates.

Supported runtime platforms are Linux x86-64 and Windows x64. The default Windows package requires WSL; a separate native Windows build is available. macOS, Windows ARM64, and MiKTeX runtimes are not supported. Startup checks the selected TeX Live installation for compatibility. The extension requires a trusted workspace.

Rendering latency depends on document complexity, fonts, and graphics. Content without verified source mappings remains readable but cannot navigate to a source token.

## Build and validate

Build the Linux runtime, including through WSL on Windows:

```powershell
python scripts/build_engine.py
python scripts/build_cpp.py
python scripts/package_extension.py
```

Build the native Windows runtime with MSVC C++ tools, a Windows SDK, and the WSL compiler cross-build toolchain:

```powershell
python scripts/build_windows_engine.py
python scripts/build_windows_cpp.py
python scripts/bundle_windows.py
npm run package:windows
```

Run the browser interface with `node native/demo.js --runtime-mode wsl` on Windows or `node native/demo.js` on Linux, then open <http://127.0.0.1:8765>. Browser-session edits stay in memory. For VS Code source debugging, select **Run TeXAstra** and press F5.

Relevant validation commands:

```powershell
node scripts/check_configuration.js
node scripts/check_extension_live.js
node scripts/check_extension_save.js
node scripts/check_frame_delivery.js
python scripts/check_viewer_latency.py
python scripts/check_preamble_stream.py
```

Dependency licenses and source distribution details are in [THIRD_PARTY.md](native/THIRD_PARTY.md) and [WINDOWS-NOTICES.md](native/WINDOWS-NOTICES.md). Version 0.0.28 introduces the TeXAstra name, commands, settings, and package identity.
