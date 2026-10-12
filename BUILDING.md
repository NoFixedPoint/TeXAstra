# Build and validate

The release bundles the typesetting engine and renderer. An installed TeX Live
distribution supplies packages, fonts, classes, and auxiliary tools at runtime.
Use a trusted checkout: TeX compilation can execute Lua and shell commands.

## Linux / WSL

The reference build uses Ubuntu 22.04 x86-64, Python 3.10+, Node.js 22, GCC/G++,
and the following packages:

```sh
sudo apt-get update
sudo apt-get install build-essential pkg-config texlive-full \
  libharfbuzz-dev libzzip-dev libpng-dev zlib1g-dev libgraphite2-dev \
  libgmp-dev libmpfr-dev libdeflate-dev
python3 scripts/build_engine.py
python3 scripts/build_cpp.py
```

On Windows, run the same scripts with `python`; they use Ubuntu-22.04 in WSL.
They cache pinned source downloads under `.work/` and the user's cache directory.

## macOS (Apple Silicon and Intel)

See [the macOS build and release guide](docs/macos.md). The macOS distribution
uses native builds for `darwin-arm64` and `darwin-x64`, with macOS 15 as its
initial minimum. It requires a compatible TeX Live 2021 installation.

## Native Windows x64

Install TeX Live, Visual Studio Build Tools with C++ x64 tools and a Windows SDK,
and Ubuntu-22.04 WSL for the compiler cross-build. WSL is needed to build the
compiler, not to run the native Windows release.

```powershell
python scripts/build_windows_engine.py
python scripts/build_windows_cpp.py
python scripts/bundle_windows.py
python scripts/windows_sources.py
```

## Validate and package

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
compilation check uses the Linux runtime. `release_sources.py` prepares the source
and license materials for both packages. Run it after both platform builds.

For a local browser session:

```powershell
node native/demo.js --project examples/demo --main main.tex --runtime-mode wsl
```

Use `--runtime-mode native --runtime native/windows-bundle` for the Windows bundle.
Open <http://127.0.0.1:8765>. Browser-session edits stay in memory. The GitHub GIF
is recorded from this shared viewer using `python scripts/record_demo.py` and
FFmpeg; edit/compile timing is not accelerated. It shows source edits, not direct
editing of rendered text.

Release binaries are unsigned and are not claimed to be bit-for-bit reproducible.
The build pins runtime source archives and library wheels with SHA-256 checks;
compiler toolchain versions and platform differences can change output bytes.

The release collector uses tracked project files. Run it from the public release
checkout with both source kits prepared; it produces the two named VSIX assets,
`texastra-sources.zip`, and `SHA256SUMS` in `artifacts/`.
