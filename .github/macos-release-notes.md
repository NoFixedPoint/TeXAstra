Native macOS preview for **Apple Silicon and Intel, macOS 15 or later**.

Download `texastra-macos-arm64.vsix` for native Apple Silicon VS Code, or
`texastra-macos-x64.vsix` for Intel VS Code. Install through **Extensions: Install
from VSIX…** and reload VS Code.

This preview needs a compatible TeX Live package tree and LuaHBTeX 1.14 formats.
The included setup script creates an isolated TeX Live 2021 installation with
the matching bundled engine and formats. It leaves your system MacTeX separate.
See the [macOS installation and build guide](https://github.com/NoFixedPoint/TeXAstra/blob/macos-distribution/docs/macos.md).

The release is gated on native CI for both architectures: dependency/signature
audits, extension unit checks, and extracted-VSIX rendering comparisons for text,
TikZ, figures and tables. It also checks included-file checkpoints, deep paths,
syntax-error recovery and preservation of project source. Matching source ZIPs
contain the validation reports; SHA-256 files cover the download assets.

Binaries are ad-hoc signed, not Developer ID signed or notarized. No interactive
VS Code GUI test or broad macOS-version compatibility claim is made. This preview
does not replace the Windows/WSL 0.1.0 release.
