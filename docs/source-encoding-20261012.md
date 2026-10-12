# Unrelated legacy-encoded TeX files no longer block preview

Opening a valid UTF-8 CV failed with `wstring_convert::from_bytes` because
project preparation indexed every `.tex` file, including an unrelated older
document with non-UTF-8 bytes. A minimal project containing a valid `main.tex`
and an unused `old.tex` containing byte `0xff` reproduced the same failure.

Source indexing now preserves non-UTF-8 input bytes and omits their token
mappings. If a previously indexed file becomes undecodable, its old spans are
discarded and its slot remains reserved. Returning to UTF-8 restores mapping
without colliding with another file's IDs. The compiler still receives the
original source; this change does not transcode legacy files or add support
for compiling arbitrary encodings.

Validation on Windows and Ubuntu 22.04 WSL:

- `python scripts/check_source_edits.py`: reproduced the conversion exception
  before the fix; passed afterward, including stale-span removal, manifest
  omission, and stable IDs after recovery.
- `python scripts/build_cpp.py` and `python scripts/build_windows_cpp.py`: passed.
- `python scripts/check_source_encoding.py --project <read-only CV directory>
  --main <CV filename>`: passed on both runtimes (`BAKO_CHECKPOINT_MODE=windows`
  selects native Windows). The synthetic fixture compiles and edits with source
  mappings. All five CV pages render and map; hashes of every file in the
  original project match before and after each run.
- `python scripts/check_live_mode.py` against an isolated CV/class copy:
  all five pages match plain LuaLaTeX pixel-for-pixel, source spans and forward
  navigation pass, three edits match fresh output and use retained checkpoints,
  and reopening reuses the cache. Source files remain unchanged.
- `node scripts/check_unit.js` and targeted `git diff --check`: passed.
- `python scripts/package_extension.py`: built the WSL VSIX and verified all
  154 packaged files against the staging tree.
- Installed the local 0.1.1 VSIX with the VS Code CLI, then repeated the
  encoding/project regression using that installed runtime: all checks passed.
  The running editor needs a window reload to activate the updated extension.

Only aggregate results are retained; private CV source and output are excluded
from Git. The fix was not exercised in an interactive VS Code window or on
macOS. Non-UTF-8 files intentionally have no token mappings; compilation of an
actually included legacy file remains subject to the engine's encoding support.
