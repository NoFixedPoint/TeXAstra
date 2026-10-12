# Forward synchronization to unloaded pages — 0.0.20

Selecting a source token in VS Code now resolves and loads its preview page even
when that page has never been viewed. This covers late positions in the main
document and included chapter files. Loaded pages still use their local mapping.

## Cause

The extension sends `{type: 'forward', file, line, column}` to the shared viewer.
The viewer used `{type: 'sync-forward', ...location, ...}` for a backend lookup.
Spreading the original selection message overwrote the new request type with
`forward`. The extension only forwards `sync-forward` queries, so it silently
dropped this message. The bug was hidden whenever a loaded page supplied the
mapping locally. The old scrolling check called `forward` without the message's
`type` field and navigated to a previously loaded page, missing this boundary.

The viewer now copies only `file`, `line`, and `column` into the backend request.
No compiler or source-index changes were needed.

## Validation

`python scripts/check_forward_sync.py` failed twice before the fix with
`VS Code selection requests backend lookup for never-loaded page False`.
The recorded outgoing request had `type: "forward"`. After the fix:

- `python scripts/check_forward_sync.py`: 8 checks pass in Chromium with a
  simulated VS Code transport, including never-loaded pages, page fetch,
  scrolling, highlight visibility, loaded-page lookup and deferred selection.
- `python scripts/check_forward_sync_live.py`: 8 checks pass with the actual
  WSL compiler and browser adapter. A 30-page document starts at page 1, then
  selections using the VS Code envelope load and highlight page 20 in the main
  file and page 30 in an included chapter. Source revision stays unchanged.
- `node scripts/check_extension_live.js`: 25 checks pass, covering the actual
  extension's selection message and query/response forwarding, plus WSL default.
- `python scripts/check_viewer_latency.py`: 10 checks pass.
- `node scripts/check_launcher.js`: 23 checks pass, including WSL and native
  environment checks. `node scripts/check_project.js`: 24 checks pass.
- `node --check webview/viewer.js`: passes.
- Running the viewer regression against the actual 0.0.18 VSIX reproduces the
  same failure. All 8 checks pass against the packaged 0.0.20 viewer.

Reports are in `results/forward-sync*.json`, `results/extension-live.json`,
`results/viewer-latency.json`, and `results/package-0.0.20.json`.
These checks exercise real Chromium and WSL, with a mocked VS Code API for the
extension boundary. A real VS Code host installation was not automated. The
native Windows compiler's full document acceptance suite was not rerun; the
fix is in the shared JavaScript viewer.

## WSL installer

The default VSIX is `artifacts/bakoma-revived-prototype-0.0.20.vsix`, built with
`python scripts/package_extension.py`. It bundles the Linux runtime, defaults
`bakoma.runtimeMode` to `wsl`, and omits the Linux-only marketplace platform
restriction so Windows VS Code can install it. The native Windows package recipe
continues to select `native` in its own manifest. An explicit user/workspace
setting still overrides either package's default.

```powershell
code --install-extension artifacts/bakoma-revived-prototype-0.0.20.vsix --force
```

Reload VS Code and reopen **BaKoMa: Open Experimental Preview**. WSL with TeX Live
is required. Package verification compares the staged files byte for byte,
checks the WSL default, embedded Linux compiler, absence of Windows binaries,
and lack of a platform restriction. The packaged viewer is also checked with
`python scripts/check_forward_sync.py --vsix artifacts/bakoma-revived-prototype-0.0.20.vsix`.
