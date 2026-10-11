# In-memory page output — prototype 0.0.3

The new default `stream` backend removes complete-PDF finalization, PDF transport,
and PDF reopening from ordinary edits with cached resources. The existing
`snapshot` backend remains selectable for comparison.

## Implementation

1. Restore a real LuaTeX checkpoint before the changed corpus input.
2. Restore the output prefix into a Linux memory-backed descriptor (`memfd`).
   LuaTeX continues its normal shipout into that descriptor.
3. Capture the completed, uncompressed page drawing stream and glyph coverage.
   Transport page buffers over a local Unix socket, then send only the visible
   page to the Windows host over the existing persistent pipe.
4. Suspend the child before document finalization. Keep the renderer document and
   font resources alive; replace only the page's command stream.
5. Rasterize with the existing lossless PNG path and preserve token navigation.

This is a direct page-command path using the PDF drawing language, not a new DVI
engine. A complete PDF supplies the initial renderer resources. Resource misses
resume the child through finalization and reseed the renderer; subsequent covered
edits return to streaming. Background convergence also produces a complete seed
and a new set of checkpoints. There is no full PDF serialization or reopening on
the ordinary `page-stream` path.

See the [architecture decision](adr/0002-retained-page-command-streams.md) and
[BaKoMa investigation](bakoma-binary-pipeline.md). No installed BaKoMa files are
modified or needed by this implementation.

## Paired measurements

The same 100-page corpus, browser harness, and machine were used sequentially:
36 text/math edits on pages 100, 50, and 1 for each backend. Both use the existing
checkpoint, source mapping, transport, and PNG implementation. Measurements run
from a browser source-input event through image decoding, text-layer installation,
and two animation frames; they do not measure physical monitor presentation.

| Measurement | Finalized PDF (`snapshot`) | Page commands (`stream`) |
|---|---:|---:|
| Median edit to display | 242 ms | 193.5 ms |
| p95 edit to display | 372 ms | 253 ms |
| Mean compiler stage | 116.1 ms | 63.3 ms |
| Mean mapping | 9.0 ms | 8.9 ms |
| Mean worker preparation | 1.8 ms | 1.9 ms |
| Mean renderer stage | 45.2 ms | 45.0 ms |
| Mean complete backend pipeline | 183.5 ms | 125.4 ms |
| Mean queue/response/browser beyond pipeline | 68.1 ms | 67.2 ms |
| Immediate adjacent page after early edits | 285 ms | 215 ms |
| Immediate jump to page 100 before convergence | 6,607 ms | 6,669 ms |

Median latency fell about 20%, p95 about 32%, and the mean compiler stage about
46%. **The 150 ms p95 target remains unmet.** Rendering and browser delivery still
contribute materially. A far jump still requires sequential work after early
checkpoints have been invalidated. This output change does not solve that cost.

Raw data: [PDF comparison](../results/page-stream-baseline-latency.json) and
[page-stream samples](../results/page-stream-latency.json). This is a small,
sequential comparison on a shared machine with other work running. Compare these
two runs with each other, not with older measurements taken under different load.
These measurements preceded the subsequent cache-navigation and stream-length
validation fixes; those changes do not alter the ordinary-edit drawing pipeline.
Engine versions, machine details, and final implementation hashes are recorded in
[page-stream-environment.json](../results/page-stream-environment.json).

## Correctness and limits

The differential harness checks all 100 initial pages against an uninstrumented
full build using the same Linux TeX engine, packages, and fonts. It then compares
exact pixels and exact source regions after text, math, rotated TikZ, new Chinese
glyphs, and paragraph reflow. It also checks syntax-error recovery, adjacent-page
reflow, unchanged seed PDFs, and absence of the finalization marker on streamed
edits. Results are in [page-stream-correctness.json](../results/page-stream-correctness.json).
All 33 assertions passed. The final [browser interaction run](../results/page-stream-browser.json)
passed 15 checks with no browser errors, including math/TikZ reverse navigation,
selection, stale-output guards, syntax recovery, convergence, and far-page
checkpoint reuse. Sustained typing displayed 18 frames over 2.894 seconds (6.22
updates/second), with a longest measured freeze of 268 ms and stable scroll/caret.
That interaction run overlapped differential checks; use the separate paired
benchmark above for ordinary-edit performance comparison.

In the diagnostic cases, a new Chinese glyph required a resource refresh (about
351 ms backend latency in that sample); the following edit streamed again (about
106 ms). Initial loading, background convergence, new resources, and reflow must
not be counted as proven ordinary-edit latency. Cold initialization still builds
the document and populates font resources and checkpoints.

The proof remains limited to the supported source-instrumentation subset and
explicit corpus input boundaries. Native Windows/macOS checkpointing and general
document rollback are not implemented. The new adapter is pinned to Linux
LuaHBTeX 1.14; on this Windows host it runs under Ubuntu-22.04 WSL. Logs, auxiliary
files, isolated source copies, and source metadata still use the filesystem.

## Run and reproduce

```powershell
python -m prototype.demo --engine stream --port 8765
# In a second terminal:
python scripts/check_browser.py http://127.0.0.1:8765
python scripts/benchmark_browser.py http://127.0.0.1:8765 --output page-stream-latency.json
python scripts/check_page_stream.py
```

Use `--engine snapshot` for the old finalized-PDF comparison or `--engine native`
for the slower native full-build fallback. In VS Code, install the 0.0.3 VSIX and
select `stream` for `bakoma.engine` if you previously set that option explicitly.
The diagnostic frame fields `outputMode`, `pageBytes`, and `resourceRefresh` expose
which path was used. Passing `--assert-target` to the browser benchmark will still
fail while p95 is at or above 150 ms.
