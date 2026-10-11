# Native Windows x64 preview — 0.0.19

The native Windows compiler, renderer, preview protocol, and VS Code launcher
are implemented. Body edits restore retained compiler state in the same process;
they do not start a full compilation on each edit. The Windows VSIX contains one
native executable. Native TeX Live supplies packages, fonts, classes and tools.
The installed distribution's formats and project sources are left unchanged.

## Run and build

Install `artifacts/bakoma-revived-prototype-0.0.19-win32-x64.vsix` in VS Code,
then run **BaKoMa: Open Experimental Preview** from a trusted project. Windows
defaults to the native x64 runtime. `bakoma.texBinDirectory` optionally selects
a directory such as `C:\texlive\2025\bin\windows`. **BaKoMa: Show LaTeX
Environment** reports the selected installation and compatibility preflight.

The bundled standalone executable also accepts the existing JSON-lines protocol:

```powershell
.\native\windows-bundle\bakoma-backend.exe --environment
.\native\windows-bundle\bakoma-backend.exe --project C:\papers\example --sync
```

It includes its Lua helpers, so standalone invocation needs no separate assets
directory. The extension passes its own matching packaged helpers explicitly.

To reproduce the build, install MSVC x64 C++ tools and a Windows SDK, Python,
and Ubuntu-22.04 WSL with normal TeX Live build prerequisites. MinGW cross tools
are extracted into a user cache; no system package installation is performed.
WSL is used only to build the compiler, not to run the resulting executable.

```powershell
python scripts/build_windows_engine.py
python scripts/build_windows_cpp.py
python scripts/bundle_windows.py
python scripts/windows_sources.py
python scripts/package_extension.py --target win32-x64 --runtime native/windows-bundle
node native/demo.js
```

The source build emits compiler/controller DLLs under `native/runtime/windows-x64`.
The release bundler combines these into `native/windows-bundle/bakoma-backend.exe`.
The installed EXE verifies its payload and each extracted file with SHA-256 and
uses a locked, versioned cache at `%LOCALAPPDATA%/bakoma-revived/runtime`.
DLL extraction is required by the Windows loader; this is a single distributed
binary, not a promise of a single file on disk after launch. Bootstrap job objects
terminate the controller and compiler tree when the supervisor exits.
See [component notices and source kit](../native/WINDOWS-NOTICES.md).

## Retained state and file I/O

`engine/windows_bridge.c` intercepts compiler allocation, string/path allocation,
and file I/O. The controller owns a fixed-address 2 GiB allocator arena whose
allocation metadata is part of the checkpoint. `MEM_WRITE_WATCH` records changed
pages; immutable page versions share unchanged history. Only the allocation
high-water prefix is protected and tracked. A narrowly scoped vectored exception
handler materializes selected page versions on first access after restoration.
It does not allocate, acquire locks, or swallow unrelated faults. Buffers are
materialized before passing them to CRT/kernel reads and writes.

The engine is a separate PE module. Its writable sections, owning thread's stack,
and `CONTEXT` are captured at existing engine safe points. Restoration runs below
the saved stack range before `RtlRestoreContext` resumes the original call.
Controller state and snapshot histories stay outside that rollback domain.
Restoring an earlier checkpoint invalidates its successors.

The worker tracks retained CRT streams, logical positions, and writable output
prefixes. Restoration clears read-ahead and rewinds/truncates output. Lua input
readers reopen at recorded byte positions; CRLF is normalized only when delivering
the logical line to TeX, preserving byte offsets. This is needed for Windows Biber
output as well as project files. Disposable native checkpoints isolate font-only
resource export. The renderer retains an immutable startup PDF and accepts live
page commands and small new-font bundles over inherited pipes.

`native/windows/platform.hpp` supplies Unicode process launch, explicit handle
inheritance, environment blocks, cache locks, atomic replacement, bounded/cancellable
pipe reads, and process-tree cancellation. Native TeX Live discovery generates a
compatible format in the user's cache with the bundled LuaHBTeX 1.14 compiler.
It never loads an incompatible installed format or requires TeX Live's engine
version to match the bundled engine.

## Validation

```powershell
python scripts/check_windows_checkpoint.py
python scripts/check_windows_engine.py
python scripts/check_windows_backend.py
python scripts/check_windows_projects.py
python scripts/check_windows_browser.py
python scripts/check_windows_bundle.py
node scripts/check_launcher.js
node scripts/check_extension_live.js
```

- Arena validation includes 655 assertions, randomized branching against an
  independent full-memory reference, prepared kernel I/O, and three fault-isolation
  child processes. A real continuation test restores a returned stack frame,
  allocator reuse and allocations above the original high-water mark.
- The 100-page native differential test compares checkpoint output with fresh
  complete compilations: exact RGB pixels, selection text/geometry, and source
  spans for late text, middle math, rotated TikZ, new glyphs and first-page reflow.
  It verifies the same compiler PID and restoration near the edited page, plus
  invalid-input recovery and forward navigation. Unicode project paths are used.
- Project tests exercise real Windows BibTeX, Biber and MakeIndex, idle convergence
  with tool reuse, nested PDF assets, concurrent cache isolation, abrupt compiler
  exit/restart, cancellation, and unchanged source trees.
- Chromium tests exercise the bundled single EXE with a separate 100-page
  Chinese/math/TikZ corpus, forward/reverse navigation, page 1/50/100 edits,
  stale-error display, recovery and full idle convergence. These are browser
  adapter checks, not an automated installation test in the real VS Code host.
- Shared launcher and extension protocol checks pass. The Linux backend still
  builds; the same Linux comparison remains available explicitly.

Raw reports are in `results/windows-checkpoint.json`, `windows-backend.json`,
`windows-projects.json`, `windows-browser.json`, and `windows-latency.json`.
The single-file executable test also verifies embedded Lua helpers, Unicode
executable paths, cache repair after a deliberately corrupted extracted module,
and operation with only TeX Live and Windows system directories on PATH. Its
PE imports are only `KERNEL32.dll` and `bcrypt.dll`.
Package validation records hashes and confirms exactly one native binary in the
Windows VSIX. Timing measurements are local observations, not cross-machine
guarantees. The 150 ms end-to-end target is not met for every workload; large
reflow, new fonts and the dense 100-page corpus remain slower than ordinary edits.

The matching 13-page browser workload was also run against Linux/WSL on this
machine (six samples per case, different installed TeX Live distributions):

| Input-to-visible p95 | Native Windows | Linux/WSL |
| --- | ---: | ---: |
| Root body edit | 142 ms | 90 ms |
| Late included chapter | 158 ms | 92 ms |
| Final edit in typing burst | 236 ms | 160 ms |
| New font | 288 ms | 141 ms |

This preserves incremental compilation, but **exact latency parity with the
Linux implementation has not been achieved**. The dense 100-page Chinese corpus
measured 271 ms median and 618 ms p95 in the native browser test, including queued
viewport work. These measurements are retained rather than hidden behind a
full-recompile fallback. See `results/windows-wsl-comparison.json` for the Linux
comparison and the per-stage fields in both native browser reports.

## Supported scope and limits

Validated on Windows 10 x64 build 19045, MSVC 14.36, Windows SDK 10.0.22000,
and installed TeX Live 2025 packages. Other TeX Live installations must pass
preflight. Windows ARM64, macOS, and MiKTeX are not supported. Native Windows does
not transparently launch projects in WSL; choose the explicit WSL comparison
runtime for those paths.

The checkpoint domain covers the statically linked engine and tracked standard
file I/O. Arbitrary native Lua modules, external threads, sockets and side effects
outside that domain are not rollback-safe. The arena cannot grow beyond 2 GiB;
checkpoint histories have no memory-budget eviction. Signed distribution,
clean Windows VM testing without developer tools, and a real VS Code host
installation test are not established by this local validation.

Preamble/package/asset changes and edits without usable dependency history rebuild
the session, as on Linux. Complete startup/idle builds and unsupported resource
changes still finalize a PDF. Body edits use retained checkpoints and preserve
the incremental path.
