# Shared project assets — 0.0.17

The project root and main document directory are now separate. The VS Code
extension uses the workspace folder containing the selected main file, falling
back to the main-file directory without a workspace. `bakoma.projectRoot` can
select a common ancestor explicitly; relative values resolve against the
workspace, or against the main-file directory without a workspace. The main
document must remain inside that root. Reopen the preview after changing these
settings.

For this layout, select `paper/main.tex` as the main file and the containing
project folder as the root:

```text
project/
  paper/main.tex
  figures/chart.pdf
  shared/chapter.tex
  shared/references.bib
  shared/local.sty
```

Relative inputs such as `\input{../shared/chapter}`, graphics paths pointing to
`../figures/`, local styles, and bibliography databases retain their normal TeX
meaning. The backend mirrors the supported project files into an isolated cache
tree and runs TeX and auxiliary tools from the mirrored main-file directory.
The JSON protocol and source navigation use paths relative to the project root.
The command-line equivalent is `--project <project> --main paper/main.tex`.

## Dependencies and source mapping

Copied input contents, including sibling assets and unsaved overlays, participate
in the startup-cache fingerprint. The recorder still tracks distribution inputs
separately. This is conservative: changing an unused supported project file can
also invalidate the build. The runtime and cache schema invalidate old sessions.
On reload, stale copied files are removed when a dependency was deleted or an
unsaved file is no longer supplied as an overlay. Generated outputs remain in the
cache tree.

The source manifest registers mirrored absolute paths. LuaHBTeX canonicalizes
both registered paths and names opened by TeX, so `../shared/chapter.tex` and
`../shared/../shared/./chapter.tex` retain the same token identity. User-facing
locations remain `shared/chapter.tex`. The checkpoint input journal resolves
these paths against the actual compiler working directory. Body edits in sibling
chapters can therefore resume existing checkpoints.

Backend sockets resolve through a retained directory descriptor under
`/proc/self/fd`, avoiding Unix socket pathname limits for deeply nested main
files. Child compiler processes still use their local socket names.

## Saved changes and unsaved buffers

A VS Code filesystem watcher observes supported files throughout the chosen
project root. Create/change/delete events are coalesced for 200 ms, then send a
`reload` mutation with the complete set of currently dirty editor buffers. The
backend discards obsolete overlays, copies current disk inputs, applies dirty
buffers, and creates fresh compiler checkpoints. Reload participates in revision
tracking, stale-frame rejection, and background-build cancellation just like
ordinary edits. It preserves the requested visible page where possible.

Ordinary text-change events continue to use checkpoint edits when safe. New
editor files and package/bibliography edits rebuild. The watcher is disposed and
pending reloads are cancelled when the preview closes. Generated cache files are
outside the watched source tree. Neither the watcher nor the backend saves editor
buffers or creates build artifacts in the source project.

## Validation

The patched LuaHBTeX engine and C++ backend rebuilt successfully. The C++ build
reported no warnings. Functional validation covers:

| Suite | Checks | Coverage |
| --- | ---: | --- |
| `check_project_assets.py` | 27 | Nested main files, sibling graphics/styles/BibTeX data, exact pixels and selection versus full builds, canonical source paths, checkpoint edits, cache reuse/invalidation, reloads, dirty buffers, missing/recreated inputs, deep socket paths, source preservation and root containment |
| `check_project.js` | 24 | Main-file discovery, project-root overrides, containment and watcher filtering |
| `check_extension_live.js` | 19 | Mock VS Code host: nested launch, sibling overlays, watcher debounce, create/change/delete handling, overlay removal and watcher disposal |
| `check_cpp.py` | 346 | Existing 100-page differential rendering and edit regressions |
| `check_token_origins.py` | 80 | Engine token origins and macro/source spans |
| `check_source_mapping.py` | 167 | Mapping, math rules, imported content and localized failures |
| `check_included_edits.py` | 189 | Retained edits, dependency invalidation and background adoption |
| `check_engine_checkpoints.py` | 67 | Safe engine checkpoints and long included chapters |
| `check_build_tools.py` | 77 | Real BibTeX/Biber/MakeIndex, tool reuse, failures, cancellation and bounded convergence |
| `check_external_project.py` | 25 | LuaLaTeX/XeLaTeX/pdfLaTeX full builds, overlays, recovery and source preservation |

Total: **1,021 checks**. The new reports are
[project-assets.json](../results/project-assets.json) and
[external-projects-assets.json](../results/external-projects-assets.json); other
suites retain their existing reports under `results/`. The project-asset report
records the tested backend hash.

The v0.0.17 VSIX is packaged and byte-verified by
`scripts/package_extension.py`, with runtime/compiler hashes recorded in
[package-0.0.17.json](../results/package-0.0.17.json). It is not installed
automatically. Extension event handling uses a mocked host; actual VS Code/WSL
filesystem-event delivery and latency were not measured in this run.

## Limits

- Choose a root containing all relative project inputs. Directory symlinks are
  not traversed. Paths outside that root, external symlink targets, and absolute
  project filenames are not remapped into
  the cache; unsaved overlays for such paths are unsupported. Distribution paths
  continue to be resolved by the installed TeX distribution.
- Supported copied formats remain TeX/package files, bibliography/style files,
  PNG/JPEG/PDF/EPS/PS graphics, common font files, and CSV/DAT/TXT/Lua data. Extension
  matching is case-insensitive. Hidden paths and `node_modules` are excluded.
- TeX's ordinary output-path restrictions still apply, including workflows that
  try to write `\include` auxiliary files through `../`. Shared `\input` files
  and read-only graphics/bibliography dependencies are covered here.
- Automatic saved-file refresh is provided by the VS Code extension and depends
  on VS Code delivering filesystem events. Direct protocol clients can send
  `reload`; the browser demo has no filesystem watcher. Distribution updates
  outside the project root still require reopening the preview.
- A large workspace is copied conservatively. Set a narrower project root when
  unrelated supported files would exceed the existing source-file limits.
- No new latency measurements or real VS Code extension-host measurements are
  claimed. Distribution discovery and compatibility preflight remain future work.
