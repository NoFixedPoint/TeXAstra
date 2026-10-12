# Save latency — version 0.0.23

Saving text already submitted to the live preview caused a second, complete
build. The filesystem watcher treated every supported change/create/delete event
as a project reload, dropping compiler checkpoints, the editor delta base, and
the current frame. Another LaTeX extension's generated document PDF could trigger
the same reload. Small source changes therefore suffered full startup cost on Save.

The extension now tracks submitted editor versions and fingerprints saved text.
After the existing 200 ms watcher debounce, it asynchronously compares the changed
disk content with the known saved or submitted buffer. Matching notifications do
not send a backend request or mark the preview stale. The saved fingerprint also
handles typing that continues before delayed watcher notifications arrive.
Content comparison handles duplicate events, atomic saves and watcher-before-save
ordering. UTF-8 BOMs are tolerated; unrecognized encodings fall back to reloading.

Notifications remain grouped by path: a matching source save cannot swallow an
unrelated figure update in the same batch. Different external source contents,
new inputs, actual deletions and asset changes still reload with current dirty
buffers preserved. Backend errors invalidate the known snapshots. Closing or
replacing a preview cancels pending reloads, including asynchronous checks.

The main document's sibling output PDF and `main.pdf` are ignored, matching the
backend's existing exclusion of these files from its input mirror. Figure PDFs
remain watched. Idle background convergence is unchanged and is independent of Save.

## Reproduction and validation

`node scripts/check_extension_save.js` first failed with
`saving an already submitted edit sends no rebuild false`. It now passes 18
checks covering ordinary/repeated saves, unchanged initial source, continued
typing, retained delta bases, delayed notifications, atomic replacement, generated
PDFs, closed buffers, external edits, mixed figure events, deletions, new files,
error recovery, bibliography saves and preview disposal. The existing extension
adapter's 33 checks and project discovery/filtering's 24 checks also pass.

The real extension, WSL backend and Chromium viewer were exercised on the isolated
85-page copy of `Mexico-wedge4.tex` used for the previous figure-note benchmark.
Each edit was displayed, then saved to that copy. The test host supplies the VS Code
save/watcher callbacks; it does not run inside an actual VS Code window. Original
project files were not edited, and the saved fixture is restored after the run.

| Version | Saves tested | Reloads caused by Save | Save to rebuilt paint |
| --- | ---: | ---: | --- |
| Installed 0.0.22 | 3 | 3 | 7,389 / 7,492 / 7,458 ms |
| 0.0.23 | 3 | 0 | No rebuild; the existing preview remains available |

The optimized test checks for reload requests 350 ms after each save, beyond the
watcher debounce. Subsequent edits retain the small delta protocol and streamed
page rendering. No zero-latency sample is claimed for an absent rebuild.
The baseline fails `--assert-no-save-rebuild`; the new version passes it.
Reports: [before](../results/save-before.json), [after](../results/save-after.json),
[save regressions](../results/extension-save.json).

```powershell
node scripts/check_extension_save.js
node scripts/check_extension_live.js
node scripts/check_project.js
python scripts/benchmark_figure_note.py --project .work/mexico-note --main paper.tex --token 'Panel (a) plots the fraction' --replacement 'Panel (a) shows the fraction' --repeats 2 --output save-after.json --save-after-edit --assert-no-save-rebuild --assert-stream
```

This update changes the extension adapter only; it reuses the validated 0.0.22
compiler/renderer runtime. The VSIX archive verifier records its file count and
hashes in `results/package-0.0.23.json`. Install the 0.0.23 VSIX and reload the VS
Code window to replace the running extension. Real VS Code save-event scheduling
and native Windows runtime performance were not measured by this harness.
