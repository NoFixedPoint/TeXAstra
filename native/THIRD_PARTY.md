# Native backend dependencies

- LuaHBTeX 1.14, the LuaTeX team, GPL-2.0-or-later. The renamed
  `runtime/texastra-luahbtex` is built from the pinned Ubuntu TeX Live source and
  security patches listed in `scripts/build_engine.py`, with the metadata patch
  in `engine/patch.py`, `engine/origins.c`, and `engine/resources.c`. Both complete source archives and
  `LuaHBTeX-COPYING` accompany the runtime. This is a modified engine. Its source
  includes the licenses/notices for Lua, FontForge, MPLib and bundled libraries.
  System HarfBuzz, Graphite2, zziplib, libpng and zlib remain dynamically linked.

- MuPDF 1.26.12, Artifex Software: https://github.com/ArtifexSoftware/mupdf/tree/1.26.12.
  The build pins its headers and obtains the matching Linux x86-64 library from
  the PyMuPDF 1.26.7 wheel. Its AGPL license is copied to
  `runtime/MuPDF-COPYING`. MuPDF's upstream third-party notices apply to its
  bundled dependencies.
- The text-trace rectangle and selection-quad conventions in `renderer.hpp`
  follow PyMuPDF 1.26.7 `src/extra.i`, copyright Artifex Software and contributors,
  licensed under AGPL-3.0: https://github.com/pymupdf/PyMuPDF/blob/1.26.7/src/extra.i.
  They preserve the previous renderer's geometry without Python objects.
- JSON for Modern C++ 3.12.0, Niels Lohmann and contributors, MIT license:
  https://github.com/nlohmann/json/tree/v3.12.0. The downloaded `json.hpp` carries
  its license and is verified against the release's SHA-256.
- System libdeflate and zlib provide lossless PNG compression and CRCs. They are
  dynamically linked, not copied into the package. Their upstream projects are
  https://github.com/ebiggers/libdeflate and https://github.com/madler/zlib.

The build script pins dependency versions and download digests. C++ source, build
instructions, and reference tests accompany TeXAstra.
`scripts/release_sources.py` adds the full MuPDF and PyMuPDF source archives and
license texts to each release. Large source archives ship in a companion ZIP;
the VSIX retains notices and a `SOURCE.md` link to the matching download.
See [the distribution licensing](../LICENSING.md).

## macOS

The macOS build uses the same engine and MuPDF versions. It restores the omitted
TeX dependency sources from upstream revision r59705 (SHA-256 pinned) and links
the engine libraries statically. The complete upstream archive and Ubuntu
security patches accompany the package. The macOS MuPDF library comes from the
architecture-matched PyMuPDF 1.26.7 wheel, with its source archive and wheel digest.
libdeflate 1.19 (MIT) is linked statically; its source and license are included.
Apple system libraries are linked from the OS and are not redistributed.
The build audits dependencies to reject references to a developer's Homebrew tree.
See `scripts/build_macos.py`, `scripts/build_engine.py`, and `docs/macos.md`.
