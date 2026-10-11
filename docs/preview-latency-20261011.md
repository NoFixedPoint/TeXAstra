# Preview latency — version 0.0.13

The preview now reports where time goes between an edit and the updated page.
`scripts/benchmark_preview.py` creates an isolated 13-page project, starts a
loopback demo backed by the production C++ service, drives real Chromium input
events, and closes its server afterward. Original project files stay unchanged.

Run `python scripts/build_cpp.py`, then
`python scripts/benchmark_preview.py --repeats 20`. Playwright and its Chromium
installation are required. The report is written to
[preview-latency.json](../results/preview-latency.json). `--output` selects another
report under `results/`; `--assert-target` exits unsuccessfully unless **every**
scenario has p95 below 150 ms. Latency thresholds are separate from correctness
checks and are not asserted by default on machines with different performance.

The four scenarios are root-body edits, edits late in a long included chapter,
eight-input typing bursts spaced 35 ms apart, and insertion of a previously unused
font. Root and chapter edits exclude one warmup. Every resource sample resets the
compiler with the original sources, ensuring that the font is new to its resource
seed. Startup time is excluded. The harness verifies the matching edit revision,
rendered text, nearby checkpoint reuse, resource-refresh path, absence of browser
errors, and unchanged original sources. It records superseded inputs and complete
burst duration separately from the latency of the final input; coalesced inputs
are never reported as zero-latency samples.

## Measurement boundaries

Browser input timing uses a monotonic clock from input-handler entry. A sample
ends after image decoding, installation of selectable text, and two animation
frame callbacks. This is a browser presentation proxy, not physical monitor
latency. The VS Code adapter starts its timestamp at the document-change callback
before reading the buffer, and logs the same stage fields through its output
channel. The automated benchmark exercises the browser adapter, not the VS Code
Extension Development Host; VS Code end-to-end latency remains unmeasured.

The backend reports queue wait and request-to-payload time, alongside compiler,
checkpoint preparation, renderer sub-stages, and resource refresh. Browser stages
separate preparation, decode, text installation, and animation-frame wait.
`deliveryMs` is the residual after subtracting backend request-to-payload time and
browser work from total time. It includes both directions of transport, JSON
serialization/parsing and adapter scheduling; it is not a pure network metric.
Pipeline and nested stage timings overlap and must not all be added together.
Resource refresh measures document completion and resource seeding after a
streamed page detects missing resources, excluding its final rendering.

Frames superseded while awaiting paint carry `stale: true` and no valid latency.
Idle convergence has no input timestamp and is excluded. Per-case percentiles
use nearest rank; with six pilot samples, p95 is the maximum. Reports include
Chromium/platform information and source/runtime hashes.

## Measured improvement

The initial six-sample pilot found median backend queue waits of 95 ms for root
edits and 56 ms for late chapter edits. Automatic requests for neighboring pages
can replay TeX and were running immediately after each displayed edit, delaying
the next input. The viewer now waits for a 200 ms quiet interval after an edit
status before requesting neighboring pages. Current-page loading and explicit
navigation remain immediate. The timer resumes neighbor loading after typing
stops; it does not debounce compilation of edits.

The same six-sample pilot after this change reduced root median display latency
from 218 to 102 ms and late-chapter median from 171 to 101 ms. Median queue wait
fell below 1 ms in both cases. These are local observations, not cross-machine
guarantees. The pilot reports are
[before](../results/preview-latency-before.json) and
[after](../results/preview-latency-after-pilot.json).

The larger run then exposed a second delay in the browser adapter: its event
loop awaited each frame's decode and paint before delivering the next event.
During typing bursts, median delivery residual reached 168 ms. The demo now
dispatches incoming events immediately, matching VS Code's message delivery.
Existing generation and per-page sequence checks guard asynchronous rendering;
newer status events can mark an older frame stale before its paint completes.
In the subsequent run, median burst delivery residual was 42 ms, and median
final-input latency fell from 259 to 192 ms. The intermediate report is
[preview-latency-queue-only.json](../results/preview-latency-queue-only.json).

The final run used 20 samples per scenario, sequentially on Windows with the
engine in Ubuntu-22.04 WSL and headless Chromium. No other project tests or builds
were launched during measurement. Results:

| Scenario | Median | p95 |
| --- | ---: | ---: |
| Root body | 103 ms | 144 ms |
| Late chapter | 112 ms | 154 ms |
| Typing burst, final input | 192 ms | 256 ms |
| Previously unused font | 237 ms | 315 ms |

The typing run delivered 20 current final-input paints from 160 input events;
140 inputs were superseded before a current paint. The report preserves burst
durations and intermediate stale paints. New-font samples spent a median 80 ms
completing and seeding resources after the first streamed page. The separate
pilot and final runs differ in sample size and system scheduling, so they should
not be treated as a controlled speedup for every scenario.

New-font edits still complete the remaining document to export resources. The
150 ms target remains unmet. Resource refresh and remaining tail latency need
further work; this version does not replace the resource protocol.

## Validation

`scripts/check_viewer_latency.py` checks edit-priority scheduling, immediate
navigation, resumed neighbor loading, stage accounting, stale paint exclusion,
and convergence exclusion in real Chromium. The extension test checks that
buffer retrieval is included in the timestamp. Real-backend scrolling and
engine-checkpoint differential checks cover the shared preview path.

Validation passed 67 engine-checkpoint differential checks, 13 real-backend
scrolling/navigation checks, 10 viewer scheduling/timing checks, and seven mocked
extension checks. The benchmark completed 80 measured edits/bursts plus 160
individual typing inputs across its 20 bursts. Results are in
[engine-checkpoints.json](../results/engine-checkpoints.json),
[scrolling.json](../results/scrolling.json),
[viewer-latency.json](../results/viewer-latency.json), and
[extension-live.json](../results/extension-live.json).

The v0.0.13 VSIX contains the tested runtime and shared viewer; packaging verifies
archive bytes against staged files and records hashes in
[package-0.0.13.json](../results/package-0.0.13.json). It was built locally, not
installed into a running editor. Native Windows/macOS checkpointing and real
VS Code host performance remain unvalidated. The benchmark's `passes150ms`
result is false; this is a reported performance limitation, not a correctness
test failure.
