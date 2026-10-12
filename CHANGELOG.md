# Release notes

## 0.1.2 — First release

- Live LaTeX typesetting and precise source ↔ document navigation in VS Code.
- Native Windows x64, Ubuntu 22.04 WSL, Apple Silicon macOS, and Intel macOS
  packages in one release. macOS requires version 15 or later.
- Incremental text, math, TikZ, figure and table updates; a white document canvas
  and a persistent, collapsible compile-error header.
- Fix `wstring_convert::from_bytes` when a valid UTF-8 document shares its folder
  with an unrelated legacy-encoded TeX file. Original source bytes are preserved.
- Matching source archives, licenses, checksums, and extracted-VSIX checks for
  rendering, edits, source preservation, and the CV encoding regression.
- Native macOS architecture/dependency audits and ad-hoc signing; a compatible
  isolated TeX Live 2021 setup with matching LuaHBTeX formats.

Install one VSIX for your platform from [0.1.2](https://github.com/NoFixedPoint/TeXAstra/releases/tag/v0.1.2).
TeX Live supplies packages, fonts, bibliography tools, and indexes. Windows
native runs without WSL or Python. See the [macOS setup guide](docs/macos.md)
for its compatible TeX tree. Automatic dependency installation and MiKTeX
integration are not supported.

Editing happens in the source editor; the rendered page supports navigation
and selection. See [validation](VALIDATION.md) and [licensing](LICENSING.md).
The earlier platform-specific release entries have been consolidated here.
