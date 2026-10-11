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

As of 0.0.18, the launcher discovers WSL instances and the backend discovers TeX
Live binary directories. Settings can select both explicitly. The selected
kpathsea supplies configuration and the format path; the bundled LuaHBTeX 1.14
performs a compatibility compile before project work. Bibliography/index tools
come from that same binary directory. Preflight and project environment reports
record identities and resolved dependencies. See the
[implementation and validation](../distribution-20261011.md).

Project-local files are copied into the build directory. Cache reuse checks
distribution identity, lookup configuration and recorded external dependencies.
Active sessions still do not watch system package updates: reopen the preview
after maintenance. Automatic generation of engine-specific formats is not
implemented; incompatible formats fail explicitly without changing the selected
installation. This decision does not establish native Windows, macOS, MiKTeX,
or compatibility with every TeX Live release.
