# Figure-note latency — version 0.0.22

Editing the figure note on page 15 of the supplied `Mexico-wedge4.tex`
reproduced a roughly four-second **to display** delay. Its 358,948-byte source
produces 85 pages. The renderer rejected every page containing an external
graphics operator, even when the images were unchanged. That forced the compiler
to finish the remaining document and replace the complete PDF resource seed.
The initial probe spent 3,469 ms in that fallback alone.

## Changes

The compiler now identifies ordinary file-backed PNG/JPEG resources at shipout.
Resource names are matched against the retained page together with the file path,
content digest, image properties and PDF image settings. The renderer reuses a
resource only when these identities agree. Changing the figure, reassigning an
image name to another file, or using unsupported graphics retains the complete
resource-refresh path. PDF figures, forms, custom image dictionaries, shading,
external color spaces and graphics-state resources remain conservative fallbacks.
Older engines without image metadata also fall back safely.

Source indexing now stores compact line/Unicode indexes and materializes rich
source spans only when output references them. Engine command spans in unchanged
prefixes survive edits. This removes the per-character string/object rebuild for
large buffers while preserving source coordinates and UTF-16 editor columns.

After the first complete buffer update, VS Code sends its actual content changes
with source/base versions and the previous UTF-16 length. The backend applies all
queued changes in order before coalescing rendering. Full-buffer clients still
work. Reopened buffers, skipped versions, backend errors and project reloads reset
the extension's edit base. Invalid bases/ranges are rejected atomically.

Neighbor prefetch now waits for a quiet interval after a fresh edit paint. A slow
compile used to consume the input-time delay, allowing speculative page replay
to compete immediately with the next keystroke. Explicit navigation still runs
immediately. The displayed latency is still measured through image decoding,
text installation and two animation frames; its measurement was not shortened.

## Measurements

`scripts/benchmark_figure_note.py` runs the actual extension, WSL backend and
shared Chromium viewer. VS Code editor/window APIs and the webview transport are
replaced by a small local test host. It edits only in-memory buffers. The supplied
document and its figure/table assets were copied into the ignored `.work` folder;
the original project was not modified or committed. Reports include source and
runtime hashes, timings and checks, without document contents.

The comparison edits the first multi-panel figure note, alternating one word.
Both versions ran sequentially on the same copy, with one first edit recorded
separately followed by six measured edits:

| Extension | Median to display | Maximum | First edit |
| --- | ---: | ---: | ---: |
| Installed 0.0.21 | 3,977 ms | 4,027 ms | 3,961 ms |
| 0.0.22 | 143.5 ms | 145 ms | 216 ms |

The repeated-edit messages shrink from approximately 374 KB to 225 bytes.
Every updated note was verified in the currently displayed revision, and all
optimized frames used `page-stream`. See [before](../results/figure-note-before.json)
and [after](../results/figure-note-after.json). The first edit still transfers the
whole buffer to establish a base. These small local samples are not a guarantee
of sub-150-ms performance, and **sub-100-ms display latency is not achieved**.
Actual VS Code host/monitor latency and the native Windows package were not
measured. The shipped update uses the existing default WSL runtime.

Reproduce against a read-only project copy:

```powershell
python scripts/benchmark_figure_note.py --project .work/mexico-note --main paper.tex --token 'Panel (a) plots the fraction' --replacement 'Panel (a) shows the fraction' --repeats 6 --assert-stream
```

Use `--extension` to select an older installed extension and `--output` to keep a
separate report. `--assert-stream` failed on 0.0.21 and passes on 0.0.22. The test
host supplies editor events with UTF-16 offsets, including real document versions.

A separate 757 KB, 100-page synthetic fixture isolated the source-size costs.
Median request-to-frame time fell from 258 ms to 47 ms. Source-update time dropped
from approximately 107 ms to 7 ms; full-buffer transport accounts for much of the
remaining difference. This is backend delivery, not a display measurement:
[before](../results/large-edits-before.json),
[mapping profile](../results/large-edits-profile-before.json),
[after](../results/large-edits-after.json).

## Validation and packaging

- 45 figure-resource and queued-edit checks: exact pixels, selection text and
  source spans; retained PNG/JPEG note edits; resizing; font changes; changed
  images with reused resource names; PDF fallback; coalesced Unicode multi-cursor
  edits through the production asynchronous queue.
- Exact pixels and selection text against a full compile of the supplied note
  edit: [result](../results/figure-note-differential.json).
- 167 source-mapping, 83 font-resource, and 67 checkpoint differential checks.
- 33 extension adapter checks; 11 Chromium timing/scheduling checks, including
  delayed neighbor prefetch after slow paints and exclusion of stale paints.
- Standalone source-index/edit tests cover supplementary Unicode, CRLF, shortened
  and empty buffers, retained command spans, and invalid delta rejection.

Commands: `python scripts/check_figure_resources.py`,
`python scripts/check_source_edits.py`, `python scripts/check_source_mapping.py`,
`python scripts/check_font_resources.py`, `python scripts/check_engine_checkpoints.py`,
`node scripts/check_extension_live.js`, and `python scripts/check_viewer_latency.py`.

Build with `python scripts/build_engine.py`, `python scripts/build_cpp.py`, then
`python scripts/package_extension.py`. The package verifier checks archive bytes
and records runtime hashes in `results/package-0.0.22.json`. Install
`artifacts/bakoma-revived-prototype-0.0.22.vsix` and reload the VS Code window.
