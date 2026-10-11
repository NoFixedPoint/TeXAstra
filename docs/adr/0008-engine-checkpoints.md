# The TeX interpreter owns checkpoint boundaries

Version 0.0.12 replaces the handwritten root paragraph splitter with safe points
in the bundled LuaHBTeX interpreter. The compiler can retain state inside an
included chapter while preserving TeX's actual grouping, expansion, conditionals,
and category-code behavior. This trades a small engine patch for removing a
second partial parser and the fixed 2,048-block input driver.

The outer interpreter invokes an optional hook between completed commands in
outer vertical mode, with normal scanner status, outside output routines and
recursive local control. The live runtime activates the hook at document start
and disables it at document end. It keeps at most one checkpoint per shipped
physical page. The comparison corpus continues using explicit checkpoints.

Each checkpoint records the read frontier of every observed TeX input. The
controller compares the old and new file bytes and selects the latest retained
checkpoint whose frontier has not crossed the first changed byte. Frontiers
cover complete buffered lines and macro arguments, not just emitted glyphs.
An observed EOF consumes an extra position so appended source invalidates state
that already observed the old end. Multiple reads and aliases use the furthest
frontier for a canonical path.

After fork restoration, active Lua readers reopen at their logical positions to
discard stale stdio buffers. The engine refreshes source tables for the active
input stack while preserving origin lengths for unchanged prefix tokens already
present in nodes or token lists. The controller likewise preserves source spans
for unchanged pages. Original source files are copied without paragraph splitting
and compiled through a small startup wrapper in the session cache.

Preamble changes still require a fresh session when every checkpoint has consumed
the changed bytes. A macro can scan a whole chapter before emitting its first
paragraph; edits to that argument must replay from before the scan. Large boxes
and long paragraphs may also lack nearby safe points. Raw file access by external
Lua modules is outside the tracked input contract. This decision supersedes the
paragraph scheduling portion of ADR 0005 and the scheduler limitations in ADR
0006; package ownership remains unchanged.
