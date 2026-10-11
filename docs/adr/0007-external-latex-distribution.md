# Ship the preview engine and use an existing LaTeX distribution

We ship and maintain the preview engine and its supporting runtime. The user's
existing LaTeX distribution supplies packages, document classes, fonts, and
supporting tools, and its package manager owns their installation and updates.
This keeps package maintenance with the distribution the user already uses and
avoids maintaining a second package ecosystem. The trade-off is that compatibility
and reproducibility depend on both our engine and the selected distribution.

Shipping the engine includes the backend, renderer, adapters, and required license
and source materials. It does not mean bundling a complete LaTeX distribution.
Project-local packages remain supported and travel with the project into its
isolated build directory.

The integration should discover compatible installations and let the user select
one when necessary. Package lookup, formats, fonts, and supporting tools should
resolve consistently against that selection. Compatibility must be checked rather
than inferred from the presence of a distribution; an existing format or package
set may not work with our engine version. Any format generation needed for our
engine should use our cache and leave the distribution's installation intact.

Missing-package diagnostics should identify the missing file and selected
distribution and direct the user to that distribution's maintenance workflow.
BaKoMa should not silently install or upgrade packages. Environment reports should
record engine/distribution identity and resolved dependencies to help reproduce
failures. Such reports describe the environment; they are not a new package
manager or a guarantee of a reproducible build.

Changes to external dependencies should invalidate reusable build state and
retained compiler checkpoints before those changes are used. Supporting external
bibliography and index tools remains separate build-orchestration work; their
installation and updates still belong to the distribution.

Currently the launcher selects Ubuntu-22.04 WSL on Windows, and the bundled patched
LuaHBTeX 1.14 reads its installed TeX configuration and LuaLaTeX format. Supported
project-local files are copied into the build directory. Cache reuse checks
external inputs recorded in the compiler's `.fls` file by size and modification
time. Active sessions do not watch system package updates, so users must reopen
the preview after such changes. Distribution selection, compatibility preflight,
environment reports, and active dependency invalidation are planned work, not
implemented capabilities. This decision does not establish native Windows,
macOS, or MiKTeX compatibility.
