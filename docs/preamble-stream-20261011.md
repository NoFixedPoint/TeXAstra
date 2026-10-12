# Editing documents that initialize PDF output in the preamble — 0.0.21

Valid edits in documents using `hyperref` could produce **Compile error · previous
preview is stale**. The compiler log reported `No drawing stream in page buffer`.
Initial compilation succeeded because it used the complete PDF rather than the
incremental page parser.

The failure was reproduced on the user's 85-page document, then reduced to an
article using `hyperref` with an ordinary text edit on its second page. Removing
`hyperref` made that edit work. Capturing the synthetic page buffer revealed a
`/Filter /FlateDecode` stream. LuaTeX initializes its PDF compression state when
the first PDF object is written, which Hyperref can trigger during the preamble.
The preview disabled compression at document start, after this initialization.
Its page parser consequently rejected the compressed drawing stream.

`inputs.lua` is loaded by the general-project driver before the document and
its packages. It now disables stream and object compression at that point when
the page-stream runtime is active. The existing document-start setup remains
for the explicit-checkpoint comparison corpus. No compiler binaries changed.

## Reproduction and validation

Before the fix, `python scripts/check_preamble_stream.py --case hyperref` failed:

```text
hyperref initial pixels match full build True
hyperref edit 1 compiles: No drawing stream in page buffer False
```

After the fix:

- `python scripts/check_preamble_stream.py`: 54 checks cover Hyperref, a PDF
  object written explicitly in the preamble, and an ordinary document. Repeated
  main-file and included-file edits stream without full export and match fresh
  full builds in pixels and text selection. Real TeX errors are rejected and
  corrected source recovers.
- `python scripts/check_forward_sync_live.py`: 14 checks run the real WSL
  compiler and Chromium viewer with Hyperref, never-loaded page navigation,
  main-file and included-file edits, stale error display, and recovery.
- The user's document was tested read-only with three in-memory edits on page
  66. All compiled, reused checkpoints, and retained source mapping. That page
  contains external graphics and still uses the existing complete-resource
  refresh, so this fix does not remove that latency cost. Its source hash stayed
  unchanged. The report stores no document content.
- `python scripts/check_live_syntax.py` checks existing syntax and mapping cases.

Results are in `results/preamble-stream.json`, `preamble-stream-external.json`,
`preamble-stream-package.json`, `forward-sync-live.json`, and `live-syntax.json`.
Package validation records byte comparisons and hashes in
`results/package-0.0.21.json`. The packaged runtime and Lua helpers are exercised
with the Hyperref regression using the test client's explicit assets directory.

The browser tests use the shared viewer and browser transport. An actual VS Code
extension-host UI session and the native Windows acceptance suite were not
automated for this fix. Projects that explicitly change PDF compression after
the preview bootstrap are outside this regression's coverage.

## Update

Install `artifacts/bakoma-revived-prototype-0.0.21.vsix`, reload VS Code, and reopen
the preview. WSL remains the default. Existing compiler sessions must be reopened
because their PDF state was initialized before the fix.
