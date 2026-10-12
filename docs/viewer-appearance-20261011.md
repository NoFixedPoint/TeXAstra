# Preview appearance

The shared browser and VS Code preview uses a light palette with readable dark
labels, white controls, and a white page surround. Outer padding is reduced from
16 to 4 pixels, page gaps from 20 to 8 pixels, and heavy page shadows become subtle
outlines. Removing the 880-pixel page-width cap lets rendered pages fill the panel.
The header, navigation, location strip, and diagnostics use less vertical space;
a flex layout gives the remaining height to the scrollable preview.

Validation on 2026-10-11:

- `python scripts/check_viewer_latency.py`: all 19 checks passed, including page
  navigation, deferred prefetch, frame delivery, and decode-error recovery.
- The embedded test viewport now uses a 900-pixel width so neighboring pages stay
  within prefetch range. The original 1440-pixel fixture timed out because pages
  became taller after removing the width cap.
- Chromium layout inspection passed at embedded sizes 480x700, 900x1000, and
  1440x1000, and at demo size 1440x1000: white surround, 4-pixel padding, pages
  filling the available width, and no document-level vertical or horizontal
  overflow. At 1440 pixels wide, embedded pages occupy 1432 pixels.
- Visually inspected the embedded preview screenshot; `git diff --check` passed.

These checks use browser fixtures. A live compiler session and the actual VS Code
extension host were not rerun for this CSS-only appearance change.
