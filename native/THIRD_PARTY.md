# Native backend dependencies

- LuaHBTeX 1.14, the LuaTeX team, GPL-2.0-or-later. The renamed
  `runtime/bakoma-luahbtex` is built from the pinned Ubuntu TeX Live source and
  security patches listed in `scripts/build_engine.py`, with the metadata patch
  in `engine/patch.py` and `engine/origins.c`. Both complete source archives and
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
instructions, and reference tests accompany the local prototype. No BaKoMa binary
or source is linked or distributed.
