# Build and validate

For prebuilt packages, follow [installation in the README](README.md#install).
This page covers building from source on macOS, Linux/WSL, and native Windows.
The release bundles the typesetting engine and renderer; TeX Live supplies
packages, fonts, classes, and auxiliary tools at runtime.

Start from a trusted checkout. TeX compilation can execute Lua and shell commands.
Run the commands below from its root:

```sh
git clone https://github.com/NoFixedPoint/TeXAstra.git
cd TeXAstra
git checkout v0.1.5
```

Source downloads are pinned with SHA-256 checks and cached under `.work/` and
the user's cache directory. Use separate checkouts for macOS and Windows/WSL
builds so their runtime files do not mix.

## macOS (Apple Silicon and Intel)

### Prerequisites and build

Use **macOS 15+**, Xcode Command Line Tools (`xcode-select --install`), native
Python **3.11.8+**, Node.js 22+, and CMake. With Homebrew already installed:

```sh
brew install python@3.11 node@22 cmake
export PATH="$(brew --prefix python@3.11)/libexec/bin:$(brew --prefix node@22)/bin:$PATH"
python3 scripts/build_macos.py
python3 scripts/check_macos.py
```

The build compiles LuaHBTeX and pdfTeX, the controller, renderer dependencies, and checkpoint
bridge, prepares the matching source kit, and ad-hoc signs the native binaries.
`check_macos.py` audits architecture, signatures, and dynamic-library dependencies.

Build with native Python: `python3 -c 'import platform; print(platform.machine())'`
should print `arm64` on Apple Silicon or `x86_64` on Intel. The build targets that
architecture; use an ARM Python on Apple Silicon rather than Intel Python under
Rosetta. Cross-compiling macOS binaries from Windows/Linux is not implemented.

### Compatible TeX tree

End users of packages built from this checkout get automatic setup inside VS
Code; the following manual procedure is for builds and validation. To exercise
the automatic installer, including fresh LuaLaTeX and PDFLaTeX compilation, run
`node scripts/check_macos_setup.js --native` on macOS after building the runtime.
Both macOS CI architectures run this check.

The bundled LuaHBTeX 1.14 and pdfTeX 1.40.22 need compatible packages and formats. Prepare an
isolated TeX Live 2021 tree in a **new destination directory**:

```sh
python3 scripts/install_test_texlive.py --destination "$HOME/texastra-texlive-2021"
export PATH="$HOME/texastra-texlive-2021/bin/universal-darwin:$PATH"
```

The setup downloads historical packages, installs both bundled engines in that
tree, and generates matching formats. It leaves system MacTeX unchanged. Use
`--engine /absolute/path/to/texastra-luahbtex` to select another built engine,
and `--pdftex-engine /absolute/path/to/pdftex` for a matching pdfTeX. Native CI
uses the unmodified `native/runtime/pdftex-baseline` as its rendering reference;
the final historical Mac TeX tree otherwise supplies incompatible pdfTeX 1.40.23.
For VS Code, set `texastra.texBinDirectory` to the absolute path printed by the
script. The setup installs a small package selection; add other document
dependencies to the selected TeX installation as needed.

### Validate and package

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install pymupdf==1.26.7
npm test
python3 scripts/check_pdftex.py
python3 scripts/check_pdftex_state.py
# Apple Silicon; on Intel replace darwin-arm64 with darwin-x64.
python3 scripts/package_extension.py --target darwin-arm64
python3 scripts/check_release_packages.py --target darwin-arm64
python3 scripts/release_macos.py
```

The package check runs the runtime extracted from the VSIX. It covers text,
TikZ, figure and table edits against fresh compilation, the legacy-encoding
regression, long paths, included-file checkpoints, error recovery, and unchanged
source files. `artifacts/darwin-arm64/` (or `artifacts/darwin-x64/`) contains the
VSIX, matching source ZIP, a `validation/` directory of reports, and SHA-256 checksums.

PDFLaTeX checks cover character navigation, retained edits, rollback and reference
convergence against stock PDFLaTeX pixels. The extracted-package check also
exercises PDFLaTeX navigation and retained included-file edits under long paths.
The bundled pdfTeX 1.40.22 is enabled only when the selected distribution's
pdfTeX version matches; other versions use the existing full-build SyncTeX path.

The GitHub Actions matrix builds natively on `macos-15` (ARM64) and
`macos-15-intel` (Intel), with release preparation gated on both jobs passing. The minimum
deployment target is macOS 15.0 for every bundled Mach-O component. Lowering it
requires rebuilding and validating the entire runtime. Binaries are ad-hoc
signed, not Developer ID signed or notarized. macOS uses file-backed checkpoints;
matching rendering does not imply identical latency across platforms.

## Linux / WSL

### Prerequisites and build

The reference build uses Ubuntu 22.04 x86-64, Python 3.10+, Node.js 22, and
GCC/G++. In Ubuntu, install the dependencies and build:

```sh
sudo apt-get update
sudo apt-get install build-essential pkg-config texlive-full \
  libharfbuzz-dev libzzip-dev libpng-dev zlib1g-dev libgraphite2-dev \
  libgmp-dev libmpfr-dev libdeflate-dev
python3 scripts/build_engine.py
python3 scripts/build_cpp.py
```

For matching PDFLaTeX character provenance on Linux/WSL, also run
`python3 scripts/build_pdftex.py`. See [the pdfTeX engine notes](docs/pdftex-engine.md)
for compatibility and validation. This is a separate build from LuaHBTeX.

From Windows, run the same two scripts with `python` in PowerShell; they invoke
the toolchain in the `Ubuntu-22.04` WSL distribution. TeX Live must be installed
inside that distribution. The backend and engine are written to `native/runtime/`.

## Native Windows x64

### Prerequisites and build

Install Python 3.11+, Node.js 22, TeX Live, Visual Studio Build Tools with C++ x64
tools and a Windows SDK, and Ubuntu-22.04 WSL for the compiler cross-build.
WSL is needed to build the compiler, not to run the native Windows package.
In PowerShell:

```powershell
python scripts/build_windows_engine.py
python scripts/build_windows_cpp.py
python scripts/bundle_windows.py
python scripts/windows_sources.py
```

The controller and compiler are built under `native/runtime/windows-x64/`.
The relocatable Windows bundle and corresponding sources are prepared under
`native/windows-bundle/`.

## Validate and package Windows and WSL

Run this sequence in PowerShell after completing **both** platform builds above:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
node scripts/check_unit.js
python scripts/check_viewer_latency.py
python scripts/check_preamble_stream.py
python scripts/check_windows_backend.py
python scripts/check_windows_bundle.py
python scripts/release_sources.py
python scripts/package_extension.py
python scripts/package_extension.py --target win32-x64 --runtime native/windows-bundle
python scripts/check_release_packages.py
python scripts/release_artifacts.py
```

The native Windows checks require Windows and its built runtime. The WSL
compilation checks use the Linux runtime. `release_sources.py` prepares source
and license materials for both packages; run it after both platform builds and
`windows_sources.py`.

The package checks extract both VSIX files and exercise the legacy-encoding
regression, mapped text/TikZ/figure/table edits, and source preservation.
`release_artifacts.py` produces `texastra-windows-x64.vsix`, `texastra-wsl.vsix`,
the matching `texastra-<version>-wsl-sources.zip` and
`texastra-<version>-win32-x64-sources.zip`, and their `SHA256SUMS` under `artifacts/`. When combining
them with macOS downloads, extend the release checksum manifest to cover those
assets too. Windows binaries are unsigned.

Packaging creates each source ZIP at the same time as its VSIX. Large upstream
archives (including duplicate TeX Live archives) are omitted from the VSIX;
runtime binaries, project source, setup scripts, licenses, and notices remain.
The installed `SOURCE.md` links to the versioned source asset and `SOURCE.json`
pins its checksum. Publish both files together using the generated source filename.
Release collectors verify and reuse this exact source ZIP; they do not regenerate
it from a potentially changed checkout. No source download is needed to run the
extension. Package JSON reports include both download sizes and checksums.

To replace 0.1.5 downloads while preserving its existing asset names and release
text, collect the four validated packages into a separate directory:

```sh
python scripts/collect_compatible_release.py \
  --wsl artifacts/texastra-0.1.5.vsix \
  --win32-x64 artifacts/texastra-0.1.5-win32-x64.vsix \
  --darwin-arm64 artifacts/darwin-arm64/texastra-macos-arm64.vsix \
  --darwin-x64 artifacts/darwin-x64/texastra-macos-x64.vsix \
  --output .work/release-downloads
```

Keep the companion source ZIP beside each input VSIX. The collector retains the
three existing source filenames: `texastra-sources.zip` contains separate `wsl/`
and `win32-x64/` source trees, and each Mac has its own source ZIP. It updates only
the packaged source references, verifies every other file and its permissions
against the tested VSIX, and regenerates all three checksum manifests. The
`collection.json` report connects the final download hashes to the tested inputs.
Publish the seven VSIX/source assets and three checksum manifests; keep the
collection report as validation evidence.

For packaging-only changes, `repackage-macos.yml` can restore the original
full-source macOS VSIX using explicit SHA-256 inputs instead of recompiling it.
It still runs native architecture/signature audits and all extracted-package
checks on both Macs. Use it only when runtime and engine sources are unchanged;
the full build workflow remains the path for binary changes.

## Browser demo and release materials

For Linux or macOS:

```sh
node native/demo.js --project examples/demo --main main.tex
```

On Windows, add `--runtime-mode wsl` for WSL, or
`--runtime-mode native --runtime native/windows-bundle` for the native bundle.
Open <http://127.0.0.1:8765>. Browser-session edits stay in memory. The GitHub GIF
is recorded using `python scripts/record_demo.py` and FFmpeg at real edit/compile
speed; editing happens in the source editor.

Packaging snapshots the staged project files and prepared source kits. Run it
from the public release checkout; collectors reuse the matching source ZIPs.
Binaries are not claimed
to be bit-for-bit reproducible: toolchain versions and platform differences can
change output bytes. See [validation](VALIDATION.md) and [licensing](LICENSING.md).
