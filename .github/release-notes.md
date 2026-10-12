TeXAstra brings live LaTeX typesetting and precise source ↔ document navigation to VS Code.

**0.1.2 is the first consolidated release for Windows, WSL, and macOS.**

- Edit text, math, TikZ, figures, and tables while viewing the rendered document.
- Navigate between source and output and inspect compile errors in the collapsible header.
- Includes the CV fix: a valid UTF-8 document no longer crashes with `wstring_convert::from_bytes` when another TeX file in its folder uses a legacy encoding. Source bytes are preserved.

### Install

Install VS Code and TeX Live in your chosen environment. Download **one** package:

| Asset | Use |
| --- | --- |
| `texastra-windows-x64.vsix` | Native Windows x64; no WSL or Python needed |
| `texastra-wsl.vsix` | Windows VS Code with TeX Live inside Ubuntu 22.04 WSL |
| `texastra-macos-arm64.vsix` | Native Apple Silicon VS Code; macOS 15+ |
| `texastra-macos-x64.vsix` | Intel VS Code; macOS 15+ |

Run **Extensions: Install from VSIX…**, reload VS Code, open a trusted LaTeX project, and run **TeXAstra: Open Document**.

For macOS, use the bundled setup script to prepare the compatible isolated TeX Live 2021 tree and matching LuaHBTeX 1.14 formats; existing system MacTeX can remain separate. See the [macOS installation instructions](https://github.com/NoFixedPoint/TeXAstra#macos). Source builds for all platforms are covered in the [build guide](https://github.com/NoFixedPoint/TeXAstra/blob/master/BUILDING.md).

Packages and external helper files come from the selected TeX installation. Automatic dependency installation and MiKTeX integration are not supported.

### Validation and scope

All four extracted VSIX runtimes pass the CV encoding regression, retain source mappings, preserve project files, and render text, TikZ, figure, and table edits identically to fresh builds. The two native macOS jobs also pass architecture/signature/dependency audits, long-path and included-file checkpoint checks, and syntax-error recovery on macOS 15.7.9. See [validation](https://github.com/NoFixedPoint/TeXAstra/blob/master/VALIDATION.md).

Windows/WSL testing is on one Windows machine with Ubuntu 22.04 WSL. This is not a clean-machine or broad OS compatibility matrix. Interactive VS Code GUI validation was not performed for these 0.1.2 packages. Windows binaries are unsigned; macOS binaries are ad-hoc signed, not Developer ID signed or notarized. Editing takes place in the source editor; the rendered page provides navigation and selection.

### Licenses and integrity

Original project code is MIT except identified upstream-derived material. The bundled compiler and renderer carry GPL/AGPL obligations; this is not an MIT-only binary distribution. Notices and matching dependency sources are included in each VSIX and the corresponding source archives:

- `texastra-sources.zip`: Windows and WSL sources.
- `texastra-darwin-arm64-sources.zip`: Apple Silicon sources and native validation.
- `texastra-darwin-x64-sources.zip`: Intel macOS sources and native validation.

`SHA256SUMS` covers all four VSIX files and all three source archives. The architecture-specific macOS checksum files are also retained. The automatic GitHub source ZIP lacks upstream source kits; use the supplied source archives for complete corresponding sources.
