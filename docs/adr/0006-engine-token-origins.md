# Source origins belong to the TeX engine

Version 0.0.10 replaces production source instrumentation with a small patch to
LuaHBTeX 1.14. TeX reads the original body and included-file text. Its scanner
determines token boundaries using the current category codes; a parallel token
table carries source IDs through argument collection, expansion and token-list
copies. Deferred tokens on the group save stack, after assignments, and during
`\futurelet` lookahead retain their origins too. No source-ID assignments are
inserted between TeX tokens.

Ordinary tokens retain their own source span. Macro replacement text inherits
the calling control-sequence token as its origin; substituted arguments retain
their individual origins. The command-token fallback intentionally excludes
arguments when those arguments did not produce the generated glyph. Node
creation and math-field scanning attach these origins as attributes, which the
existing shaping/layout and shipout path carry to the renderer.

`engine/patch.py` applies checked edits to a pinned upstream source archive.
`engine/origins.c` owns the metadata; `native/source.hpp` only indexes source
text and translates engine-reported spans into editor positions. It contains no
macro-name lists or argument parser. Project `.tex` files are registered before
compilation, so computed input filenames can be tracked too. A resumed session
reloads its source registry when an edit creates additional paragraph blocks.

The engine's token values and serialized format layout are unchanged. Metadata
is process memory retained by the existing fork checkpoints. Internal undo
snapshots have been removed, superseding ADR 0004; there is one checkpoint
implementation to maintain.

Builds pin Ubuntu's TeX Live 2021 source (LuaHBTeX 1.14) and apply the security
patches from its 1ubuntu0.3 source package before our patch. The extension ships
the renamed executable, upstream source archive, distro patch archive, license,
and our patch/build recipe. It uses the installed WSL distribution's LaTeX
packages and fonts. Updating the engine requires rebasing the checked patch and
rerunning pixel, provenance, and checkpoint tests.

This does not replace the separate paragraph splitter used to choose checkpoint
boundaries. That scheduler still requires explicit document boundaries and can
have compatibility limits for unusual input structure or category-code changes
across blocks. Generated Lua nodes, rewritten input buffers, imported PDF text,
and arbitrary token manipulation by external modules are not established as
precise source origins. Non-glyph rules are not selectable source tokens.

The differential corpus continues checking exact pixels and glyph geometry.
Its old rewriter remains a test-only oracle for established token destinations;
generated-content fallback comparisons normalize both implementations to the
originating command token. Independent tests exercise reordered/delimited
arguments, nested expansion, active characters, changed letter catcodes,
verbatim, unbraced math, token registers, and computed file inputs.

The legacy oracle also incorrectly assigns a body token to a generated footer
page number when a paragraph reflows. The new regression explicitly requires
that footer to remain unmapped, then compares every body region as before.
