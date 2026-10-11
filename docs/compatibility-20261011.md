# Compatibility repairs — version 0.0.9

Compilation uses the existing LuaHBTeX 1.14 engine and installed LaTeX packages
under Ubuntu-22.04 WSL. MuPDF interprets and rasterizes page output. Our code
implements source instrumentation, compiler snapshots, incremental scheduling,
page transport and preview navigation; it does not implement TeX's typesetter.
The current source rewriting is experimental and can break otherwise valid TeX.

A reported project failed with `Incomplete \iffalse; all text was ignored`.
A minimal document compiled successfully with ordinary LuaLaTeX and failed in
live mode. A generated block ended inside a false conditional. TeX's skipping
scanner did not expand the Lua command that would load the later closing `\fi`.
The block splitter now keeps literal primitive conditionals together, including
nested branches. It ignores grouping/environment syntax inside that region,
since skipped TeX can contain unmatched braces. Conditional blocks are preserved
verbatim with a macro-origin range; inserting setters into numeric operands could
otherwise change branch selection. This is bounded lexical handling, not a
general implementation of expandable conditional aliases or altered catcodes.

The same project exposed unbraced math-field failures: `\d\bar\Theta`,
`x^\frac{1}{2}`, and `\frac{\d}{\d\theta}` with a redefined `\d`.
The scanner now keeps supported nested accent/fraction fields intact and does
not consume a closing delimiter or script as an accent argument. Originally
unbraced accent chains retain their original grouping, since adding braces can
change accent placement. These expressions use a combined source-origin range
where inserting internal markers would change TeX's grammar. Unbraced `\pmb`
arguments are also recognized. For dollar-delimited macro arguments, a dollar
inside a nested brace group is not treated as the closing delimiter; this
preserves embedded math such as `\text{value $x_i$}` inside a custom equation.
Unknown starred commands keep the star and following arguments adjacent to the
command, including natbib's `\citealp*{...}`.
The dollar-delimited fallback applies outside math: an unknown math symbol
followed by a closing `$` must not consume a later equation macro as its argument.

The manuscript also exposed a separate provenance mismatch in Palatino virtual
fonts. One TeX glyph node can draw multiple physical glyphs, while a missing
character draws none. Sidecar recording now counts the standard virtual-font
`font`/`char`/`slot` packets recursively and caches counts by font and character.
It repeats the source identifier for each physical component. Navigation still
requires exact agreement with the renderer trace; arbitrary Lua or node output
inside virtual-font packets is outside this counting model. This uses LuaTeX's
existing font descriptions; it does not implement font shaping.

Backend error messages now also appear in **Output → BaKoMa prototype**, so an
error visible in the preview is not lost from the diagnostic log.

`python scripts/check_live_syntax.py` compares the public regression cases with
plain LuaLaTeX, including rendered pixels, surrounding token mapping and live
edits. Results are recorded in `results/live-syntax.json`. The broader live
fixture and extension command checks remain in their existing scripts.

The reported manuscript now passes 216 checks: all 101 pages match plain
LuaLaTeX pixels, all pages have source regions, and three edits on physical page
51 resume a retained checkpoint and match complete recompilations. Reopening
reuses the cache. All 156 original project files have unchanged hashes. Aggregate
results are in [conditional-project.json](../results/conditional-project.json);
private source and rendered pages are not included. The public syntax suite
passes 75 checks across 15 cases, including glyph-coordinate checks after
virtual-font expansions and missing characters.

These repairs do not establish compatibility with arbitrary documents or
XeLaTeX-only features. Preventing this class of failure more generally requires
moving provenance tracking closer to TeX's actual token consumption and macro
expansion, rather than continually expanding a separate source scanner. That
engine-level work is not implemented in this version.
