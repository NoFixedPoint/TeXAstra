# macOS distribution

The macOS port builds native VS Code extensions for Apple Silicon (`darwin-arm64`)
and Intel (`darwin-x64`). The initial deployment target is **macOS 15 or later**.
The release workflow compiles and validates on both architectures. Until it passes,
these are development build instructions, not a claim of a tested binary release.

## Build on your Mac

Install Xcode Command Line Tools (`xcode-select --install`), native Python 3.11+
(3.11 is used by CI), Node.js 22+, and CMake. With Homebrew already installed:

```sh
brew install python@3.11 node@22 cmake
git clone https://github.com/NoFixedPoint/TeXAstra.git
cd TeXAstra
git checkout macos-distribution
python3 scripts/build_macos.py
python3 scripts/check_macos.py
```

The build downloads pinned engine, MuPDF and libdeflate dependencies, applies the
engine patches, compiles the controller and Lua checkpoint bridge, and prepares
the dependency source kit. It uses Apple's compiler and SDK. There is no Python
dependency at extension runtime. The first build can take several minutes.

Run native Python: `python3 -c 'import platform; print(platform.machine())'` should
print `arm64` on Apple Silicon or `x86_64` on Intel. The build targets the Python
process's architecture; do not run an Intel Python under Rosetta for an ARM build.

## TeX Live compatibility

This project still bundles LuaHBTeX 1.14. A current MacTeX installation can have
incompatible LuaLaTeX formats and packages. Use a separate **TeX Live 2021** tree
for this release; you can keep your current MacTeX installation unchanged.
The explicit installer below downloads historical packages to a new user
directory, installs the bundled LuaHBTeX 1.14 in that isolated tree, and generates
matching formats. (The original 2021 Mac binaries are LuaHBTeX 1.13.2.) It does
not change the system TeX installation. Build the runtime or install the VSIX
first; `--engine /path/to/texastra-luahbtex` can select its engine explicitly:

```sh
python3 scripts/install_test_texlive.py --destination "$HOME/texastra-texlive-2021"
export PATH="$HOME/texastra-texlive-2021/bin/universal-darwin:$PATH"
```

In VS Code, set `texastra.texBinDirectory` to the **absolute** path printed by the
installer (replace `$HOME` with your actual home directory in JSON settings).
The runtime also discovers `/Library/TeX/texbin` and standard TeX Live directories.
Run **TeXAstra: Show LaTeX Environment** to check the selected installation.

## Validate, package, and install

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install pymupdf==1.26.7
npm test
# Apple Silicon; on Intel replace darwin-arm64 with darwin-x64 below.
python3 scripts/package_extension.py --target darwin-arm64
python3 scripts/check_release_packages.py --target darwin-arm64
python3 scripts/release_macos.py
```

`artifacts/darwin-arm64/` (or `artifacts/darwin-x64/`) contains the VSIX, matching
source ZIP, and SHA-256 checksums. Install the VSIX using VS Code's
**Extensions: Install from VSIX…**, reload VS Code, open a trusted LaTeX project,
and run **TeXAstra: Open Document**. For local browser testing:

```sh
node native/demo.js --project examples/demo --main main.tex
```

The package check extracts the actual VSIX into a directory containing spaces,
compiles the example, edits text/TikZ/figure/table content, and compares each
rendered result against a fresh compilation. It also exercises long nested paths,
included-file checkpoints, syntax-error recovery and source preservation. `check_macos.py` checks architecture,
ad-hoc signatures and dynamic dependencies; non-system libraries must be bundled.
The source ZIP includes these validation reports.

## Architecture, OS versions, and cross-compilation

- Apple Silicon Macs (M1 and newer) use ARM64; Intel Macs use x86-64. We ship two
  VSIX packages, matching VS Code's `darwin-arm64` and `darwin-x64` targets.
- You do **not** need a binary for every macOS release. A deployment target sets
  the oldest supported OS, provided all dependencies support it. This initial
  distribution selects macOS 15. Lowering that floor requires rebuilding and
  testing the entire runtime and its libraries against the older target.
- Apple supports compiling both architectures on a Mac, and combining slices
  into a universal binary. This repository currently builds each architecture
  natively because the engine's configure probes and dependency libraries also
  need the right architecture. Intel Macs cannot run ARM64 tests.
- Cross-compiling from Windows/Linux is technically possible with a suitable
  toolchain and Apple SDK, but is not implemented here. It would still need Mac
  testing. The supplied GitHub Actions matrix uses `macos-15` (ARM64) and
  `macos-15-intel` (Intel), so one Mac is enough for local work and CI can produce
  the other package. The minimum OS applies to every bundled Mach-O component.

The binaries are ad-hoc signed for local execution, not Developer ID signed or
notarized. VSIX is the distribution format; this is not a standalone `.app`/DMG.
macOS uses file-backed PDF checkpoints instead of Linux `memfd`; equivalent
rendering is tested, but identical latency is not promised.

References: [Apple universal binary builds](https://developer.apple.com/documentation/apple-silicon/building-a-universal-macos-binary),
[VS Code platform-specific extensions](https://code.visualstudio.com/api/working-with-extensions/publishing-extension#platformspecific-extensions),
[GitHub runner labels](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job).
