Native macOS release for **Apple Silicon and Intel, macOS 15 or later**.

This regular release includes the CV fix: opening a valid UTF-8 document no
longer crashes with `wstring_convert::from_bytes` when another `.tex` file in
the project uses a legacy encoding. Original file bytes are preserved.

Download `texastra-macos-arm64.vsix` for native Apple Silicon VS Code, or
`texastra-macos-x64.vsix` for Intel VS Code. Install through **Extensions: Install
from VSIX…** and reload VS Code.

This release needs a compatible TeX Live package tree and LuaHBTeX 1.14 formats.
The included setup script creates an isolated TeX Live 2021 installation with
the matching bundled engine and formats. It leaves your system MacTeX separate.
See the [macOS installation instructions](https://github.com/NoFixedPoint/TeXAstra#macos)
or the [build guide](https://github.com/NoFixedPoint/TeXAstra/blob/master/BUILDING.md).

The release is gated on native CI for both architectures: dependency/signature
audits, extension unit checks, and extracted-VSIX rendering comparisons for text,
TikZ, figures and tables. It also checks included-file checkpoints, deep paths,
syntax-error recovery, preservation of project source, and the legacy-file
encoding regression in both extracted VSIX packages. Matching source ZIPs
contain the validation reports; SHA-256 files cover the download assets.

Binaries are ad-hoc signed, not Developer ID signed or notarized. No interactive
VS Code GUI test or broad macOS-version compatibility claim is made.
Windows and WSL packages are included in this same 0.1.2 release.

Package dependencies still come from the selected TeX installation; this release
does not add automatic package installation or bundle Scientific Word helpers.
