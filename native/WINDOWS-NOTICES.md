# Windows runtime contents

The Windows VSIX ships one native executable, `texastra-backend.exe`. It embeds
the controller, patched compiler, renderer, required Microsoft runtime DLLs,
and Lua helpers. At startup it verifies SHA-256 hashes and extracts them into
`%LOCALAPPDATA%/texastra/runtime/<payload hash>`. The extracted compiler
module imports its allocator and checkpoint services from the controller.
No WSL, Python, Node native addon, or installed Visual C++ redistributable is
needed by the runtime. VS Code supplies Node for the extension itself.

Components and source locations:

- LuaHBTeX 1.14 / TeX Live SVN r59705, GPL-2.0-or-later and its component
  licenses. The source kit includes the pinned Ubuntu source archive, security
  patches, and bundled library sources omitted from Ubuntu's repack. Our
  changes and build recipe are in `engine/` and `scripts/build_windows_engine.py`.
- MuPDF 1.26.12, distributed in the pinned PyMuPDF 1.26.7 Windows wheel, GNU
  Affero GPL version 3. The source kit contains the full upstream release
  including third-party sources, and `MuPDF-COPYING`. Upstream:
  <https://mupdf.com/releases> and <https://github.com/pymupdf/PyMuPDF/tree/1.26.7>.
- libdeflate 1.19, MIT; source and license included in the source kit.
- nlohmann/json 3.12.0, MIT; the full single-header source includes its license.
- MinGW-w64 and GCC runtime libraries, their component licenses and GCC Runtime
  Library Exception. Copyright notices are included in the source kit.
- Microsoft Visual C++ runtime (`msvcp140.dll`, `vcruntime140.dll`,
  `vcruntime140_1.dll`), unmodified redistributable files supplied by the installed
  Visual Studio toolchain. Microsoft license terms apply to these components.
  [Runtime license terms](https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/)
  and [distributable code list](https://aka.ms/vs/17/redist.txt).

`scripts/windows_sources.py` followed by `scripts/release_sources.py` assembles
the complete source kit beside the bundle;
`scripts/package_extension.py --target win32-x64` includes it in the VSIX.
The engine build recovers its library sources from pinned upstream commit
`7652969578ab227a3ae1774f0530f175e4a5abe2`. To reconstruct that source tree offline,
extract the Ubuntu archive, apply its declared `CVE-*` Debian patches, unpack
`windows-engine-libraries.tar.xz` into the tree, and run `engine/patch.py`.
The build scripts record exact versions and download hashes. The Windows
controller, bootstrap, and platform implementation are under `native/windows/`.

The external TeX Live installation supplies packages, fonts, classes, and
bibliography/index tools. It is not embedded in the executable or maintained by
this extension.
