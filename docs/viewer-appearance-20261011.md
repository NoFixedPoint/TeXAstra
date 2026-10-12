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

## Version 0.0.26: compile errors

The permanent limitations footer is replaced by a hidden error panel. Compilation
failures open it automatically with the compiler's error text; users can collapse
it. Errors remain during retries and stale frame delivery, then clear after a
current successful compile. Nonfatal warnings do not show the error panel.
Preview rendering and connection failures use the same panel with distinct
headings. Expanded errors occupy at most 35% of the window height and scroll
without covering the preview controls.

Validation: `python scripts/check_viewer_latency.py` passed all 25 checks,
including initial hiding, literal error text, expansion/collapse, retaining errors
during retry/stale output, successful recovery with warnings, and failures with
no details. `node --check webview/viewer.js` and `git diff --check` passed. These
checks use synthetic compiler messages in Chromium; live compiler and VS Code
host interactions were not rerun.

## Version 0.0.27: user-controlled error details

The compile-error header is always visible and starts collapsed. It is neutral
when there are no errors and red while an error is present. Error updates and
successful compilation never change the user's expanded/collapsed choice.
Successful compilation clears the error text and restores the neutral header.

Validation: all 27 checks in `python scripts/check_viewer_latency.py` passed,
including computed header colors, manual expansion/collapse, preserving that
choice across errors and recovery, and fallback error text. JavaScript syntax
validation and `git diff --check` passed. Browser fixtures were used; live
compiler and VS Code host interaction were not rerun.
