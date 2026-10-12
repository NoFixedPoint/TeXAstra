# Release validation

## 0.1.2 ? Windows, WSL, and macOS

This is the first consolidated release. All four packages use extension version
0.1.2 and include the fix for an unrelated legacy-encoded TeX file preventing a
valid UTF-8 project from opening.

### Packaged-runtime checks

Each VSIX is extracted into a path containing spaces. Its actual bundled runtime
is checked for:

- Successful compilation and source mappings with an unrelated non-UTF-8 draft.
- Text, TikZ, figure, and table edits that match a fresh compilation exactly.
- Preservation of every original project file.

[Windows/WSL package results](results/release-packages.json),
[Apple Silicon results](results/release-packages-darwin-arm64.json), and
[Intel macOS results](results/release-packages-darwin-x64.json) record the package
hashes and individual checks. Windows/WSL packages are validated locally on
Windows x64 and Ubuntu 22.04 WSL. Both macOS jobs passed on **macOS 15.7.9**,
with a macOS 15.0 deployment target, in
[the native CI run](https://github.com/NoFixedPoint/TeXAstra/actions/runs/38226791788).

The macOS checks also cover architecture, ad-hoc signatures, library dependencies,
long paths, included-file checkpoints, syntax-error recovery, and source
preservation. The macOS package bytes are unchanged from that successful run.
The native build commit is `675f0075f2bba4e0f24ad54c600147b6ebb53745`.

[Published asset identities](results/release-0.1.2.json) record the consolidated
release's checksums and package versions. The supplied source archives contain
the corresponding project and dependency sources. `SHA256SUMS` covers all four
VSIX packages and all three source archives; architecture-specific macOS
checksum files are retained as well.

### Other validation

Extension unit tests, Python syntax checks, source-index tests, and the WSL
compile/edit encoding regression passed during release preparation. Earlier
platform acceptance also covered Windows bibliography/index tools, project
assets, concurrent sessions, crash recovery, and Chromium document interaction.
Those broader acceptance checks were not rerun for this consolidation.

### Limits

There is no clean-machine or broad OS compatibility matrix. Interactive VS Code
GUI validation was not performed for the 0.1.2 packages. Windows binaries are
unsigned; macOS binaries are ad-hoc signed, not Developer ID signed or notarized.
macOS 15.0 itself was not tested. macOS still requires the compatible isolated
TeX Live 2021 setup; newer MacTeX formats are not assumed compatible.

The selected TeX installation supplies packages and fonts. Automatic dependency
installation and MiKTeX integration are not supported. Private CV/lecture sources
and rendered documents are excluded from release materials.
