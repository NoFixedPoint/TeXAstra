# Typing frame delivery — version 0.0.24

Continuous typing could send arbitrarily many full PNG/JSON frames through
`webview.postMessage` before the viewer finished one. Concurrent image decodes
could repeatedly supersede one another, leaving the preview unchanged throughout
a burst. The extension regression reproduced 21 forwarded frames with no viewer
acknowledgement; the same test now forwards one, then the newest pending frame.
This reproduces missing backpressure, not the exact latency of a real VS Code host.

## Delivery behavior

The extension retains one in-flight frame and one replaceable pending frame.
The webview acknowledges completion after decoding, installing the image and text
layer, and the existing two animation-frame callbacks. `postMessage` acceptance
alone is not a paint acknowledgement. The shared browser viewer independently
bounds work to one active frame and one replaceable pending frame, including when
used by the HTTP demo without the extension adapter.

Active work finishes even if more source edits arrive. Intermediate revisions
can therefore appear during sustained typing; their navigation remains disabled
and their `visibleMs` remains null when stale. Pending frames coalesce only when
a replacement rendering exists, never merely because a newer input exists. All
source edits still reach the backend and retain versioned delta validation.

Status and forward-navigation messages bypass frame backpressure. Dropped page
requests receive `discard` so pending-page bookkeeping can retry them. Pending
mutation frames take precedence over same-generation page queries; older
generations cannot replace newer pending work. Existing neighbor-prefetch quiet
intervals and backend edit coalescing/convergence scheduling remain in place.

Decode errors and rejected deliveries release the queue. Old/duplicate
acknowledgements cannot release a different frame. Hidden webviews keep a bounded
pending payload while animation callbacks are suspended; there is intentionally
no timeout that would keep sending full frames into a hidden document. A new
`ready` after webview reload resets delivery state without reusing delivery IDs.
Disposal drops retained work and ignores callbacks from the old panel.

PNG format, resolution, selectable text and source-mapping semantics are unchanged.
This bounds extension-to-webview delivery and browser work; it does not eliminate
backend rendering or serialization for frames replaced in the extension.

## Diagnostics

Output → BaKoMa prototype logs correlated records without document/image contents:

| Record / field | Meaning |
| --- | --- |
| `frame-transport.serializeMs`, `writeMs` | Backend JSON serialization and stdout write/flush, measured locally with a monotonic clock. Sent after the frame because write time is not known beforehand. |
| `frame-transport` identity | Client ID, revision, generation, purpose and phase correlate the record with a frame. These backend timings are not added to the payload after serialization. |
| `paint.payloadBytes` | UTF-8 JSON payload bytes, excluding the line terminator. |
| `paint.imageEncodedBytes`, `nonImageBytes` | Base64 image data-URL bytes and the remaining payload bytes. The latter includes mapping rows and all other metadata, not just mapping data. |
| `paint.hostStagesMs.parse`, `.queue` | Extension JSON parsing and time held pending before dispatch; local monotonic durations. |
| `paint.hostReceivedAt`, `hostDispatchAt` | Host wall-clock timestamps at complete-line receipt and dispatch. |
| `paint.webviewDeliveryMs` | Webview receipt minus host dispatch, using wall clocks. An estimate for colocated clocks; do not interpret it as an accurate one-way duration for remote extension hosts or clock adjustments. |
| `paint.viewerQueueMs` | Local monotonic wait before browser frame processing. |
| `paint.browserStagesMs` | Existing preparation, decode, text/image installation and two-animation-frame wait durations. |
| `paint.frameAgeMs`, `revisionLag`, `updateIntervalMs` | Age of the displayed frame, revisions behind the newest observed backend status, and interval between non-page presentation proxies. Frame age remains available for stale intermediate updates; convergence has no edit age. |
| `paint.replacedFrames` | Cumulative pending replacements in this webview delivery session, including page requests. |
| `frame-delivery.hostRoundTripMs`, `outcome` | Host-monotonic dispatch-to-acknowledgement time, including both transport directions and viewer processing. Also records failed delivery outcomes. |

`visibleMs` retains its old endpoint and stale-frame exclusions. `deliveryMs`
remains a residual: total minus backend request-to-payload time, browser work and
the separately measured viewer queue. Host parse/queue and transport are nested
inside that residual; do not add all fields together. Backend write time ends
when the pipe accepts the bytes, not when VS Code receives them. Existing
edit-to-display and frame-age fallbacks use wall clocks across processes, so
clock jumps can affect them. Browser-local intervals use `performance.now()`.
The viewer retains at most 256 paint-history records.

## Measurements and limits

`benchmark_figure_note.py` now supports `--burst-edits`, `--interval-ms` and an
optional `--decode-delay-ms` for controlled slow-viewer experiments. It records
updates during typing, frame age, update gaps, final-input latency and the new
diagnostics. Original source files stay unchanged. The test runs the real
extension and WSL compiler with mocked editor APIs and an HTTP webview bridge;
it does **not** measure an actual VS Code window or physical monitor latency.

Three 40-edit bursts, spaced approximately 35 ms apart, on the isolated 85-page
figure-note project produced these final-input display latencies:

| Version | Final input in each burst | Updates during each burst |
| --- | --- | --- |
| 0.0.23 | 188 / 224 / 147 ms | 13 / 13 / 12 |
| 0.0.24 | 192 / 236 / 258 ms | 13 / 13 / 11 |

These small sequential samples show **no general latency improvement**. No
extension frames were replaced in the ordinary run: its viewer kept pace with
the backend. The new run's median backend serialization was 1.29 ms, stdout
write was 0.49 ms, and payload size was about 526 KB. The image accounted for
about 251 KB, with about 275 KB of other data. This does not support attributing
hundreds of milliseconds to PNG sending in this harness.

A separate controlled experiment added 180 ms to image decoding. The old viewer
made zero updates during the burst and failed the progress assertion. The new
viewer made five updates during typing (eight including completion), and passed.
Final-input display time was 424 ms before and 575 ms after. Completing active
work preserves continuity but can add one active frame's remaining work to the
final input's delay. This tradeoff is explicit; the 150 ms target is not achieved.

Reports: [ordinary before](../results/typing-delivery-before.json),
[ordinary after](../results/typing-delivery-after.json),
[slow viewer before](../results/typing-slow-viewer-before.json),
[slow viewer after](../results/typing-slow-viewer-after.json).
The measured snapshots precede the final webview-reload guard; each report
includes hashes of the measured extension, viewer and backend.

## Validation and package

Passed: 14 frame-delivery checks, 37 extension adapter checks, 18 save checks,
24 project checks, 19 real-Chromium timing/queue checks, 32 mapping/click checks,
and 13 real-backend scrolling, navigation, convergence and error-recovery checks.
The controlled slow-viewer baseline failure is intentional. The browser queue
test holds decoding while 20 frames arrive: only the first and last decode,
with a maximum of one concurrent decode. Intermediate stale paints remain
excluded from current-edit latency. A decode rejection and obsolete generation
both acknowledge completion and allow later frames through.

```powershell
node scripts/check_frame_delivery.js
node scripts/check_extension_live.js
node scripts/check_extension_save.js
node scripts/check_project.js
python scripts/check_viewer_latency.py
python scripts/check_mapping_browser.py
python scripts/build_cpp.py
python scripts/benchmark_figure_note.py --project .work/mexico-note --main paper.tex --token 'Panel (a) plots the fraction' --replacement 'Panel (a) shows the fraction' --repeats 3 --burst-edits 40 --output typing-delivery-after.json --assert-stream
python scripts/package_extension.py
```

The WSL VSIX is `artifacts/bakoma-revived-prototype-0.0.24.vsix`; archive validation
is recorded in `results/package-0.0.24.json`. Install it and reload VS Code to
replace the running extension. The separately packaged native Windows runtime
was not rebuilt or benchmarked for this update. Actual VS Code transport remains
the next measurement needed to identify the user's remaining latency.
