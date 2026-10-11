# Distribution discovery and compatibility — 0.0.18

BaKoMa continues to ship its patched engine and preview runtime. Packages,
classes, fonts, formats and bibliography/index executables come from an existing
LaTeX distribution. No package installation, update or format generation is
performed by this integration.

## Selection

On Windows, the launcher lists installed WSL distributions. An explicit
`bakoma.wslDistribution` wins; otherwise a WSL UNC source/runtime path selects its
owner, then Ubuntu-22.04 is preferred when installed, then the first listed
instance is used. Conflicting UNC owners, unavailable selections and missing WSL
produce actionable errors. Drive paths are translated to their `/mnt/<drive>`
equivalent; WSL paths must belong to the selected instance. Native Linux uses the
same backend directly. The packaged executable remains Linux x86-64.

The backend discovers `kpsewhich` along PATH, then under
`/usr/local/texlive/*/bin/x86_64-linux`, then `/usr/bin`. The first discovered
installation is selected unless `bakoma.texBinDirectory` specifies an absolute
Linux binary directory. Candidates appear in the environment report. A failing
selection is reported rather than silently switching installations.

For example, workspace settings can explicitly select the validated environment:

```json
{
  "bakoma.wslDistribution": "Ubuntu-22.04",
  "bakoma.texBinDirectory": "/usr/bin"
}
```

Settings are read for the selected main document. Reopen the preview after a
selection change. The standalone demo accepts `--wsl-distribution` and `--tex-bin`;
the Linux backend accepts `--tex-bin` directly.

Selected `kpsewhich` supplies `TEXMFCNF` instead of hard-coded Debian paths. Its
resolved LuaLaTeX format is passed explicitly to the bundled engine. The selected
binary directory is prepended to PATH, and orchestrated BibTeX/Biber/MakeIndex
executables are resolved strictly within it. Missing optional tools do not block
ordinary documents, but a document requiring one receives an error naming the
selected distribution. Tools do not fall back to another installation on PATH.
Inherited TeX lookup overrides remain effective and are listed in the report;
they can intentionally extend or override the selected installation's resources.

## Compatibility and caching

Before processing project requests, the backend compiles a small article with
text and math using the bundled engine and selected format. The probe runs with
shell escape disabled in a unique cache directory and requires a produced PDF.
It does not load project source. Missing formats and incompatible dumps/packages
fail before the project build, with an explanation and selection/maintenance
remedy. Full-build comparison mode probes the selected full compiler instead and
does not require a LuaLaTeX format when using pdfLaTeX or XeLaTeX.

Each discovery subprocess has a ten-second bound; the compatibility compile has
a thirty-second bound. A timeout kills and reaps the subprocess group. Temporary
probe directories are removed. Normal distribution-managed font caches may be
populated by TeX as on an ordinary compile.

Successful probe results are published atomically under
`$XDG_CACHE_HOME/bakoma-revived/environment-v1`, or `~/.cache/...`. Reuse checks the
engine hash, selected binary paths/stamps, lookup overrides, configuration files,
TeX filename databases, format path/stamp and all recorded probe inputs. The
configuration and filename databases are enumerated afresh because they may be
read before the recorder starts. Changing a selected installation or its tracked
inputs invalidates both compatibility reuse and project startup-cache identity.
No probing or hashing is added to checkpoint edits.

## Reports and errors

**BaKoMa: Show LaTeX Environment** opens a new JSON document that can be saved or
copied by the user. It includes host/WSL selection, discovered candidates,
selected executables and stamps, engine/distribution versions, the bundled-engine
hash, configuration, format, inherited lookup overrides, compatibility status,
and resolved probe dependencies. It does not transmit the report anywhere.

The backend's `--environment` command prints the same core JSON without needing
a project and exits nonzero on preflight failure. Async previews emit an
`environment` message at startup; the extension records it in its output channel.
Every complete project build writes `bako-environment.json` in its isolated
session, augmented with the actual external inputs from its `.fls` file. Frames
provide that report path, also logged by the extension. These reports contain
machine paths and metadata, not project source text.

Missing LaTeX file errors name the input and selected installation, distinguishing
package/class maintenance from checking project-local paths. Runtime launch
errors include the loader's stderr so a missing shared library is visible.

## Validation

The C++ backend rebuilt without warnings. **735 functional checks passed**:

| Suite | Checks | Coverage |
| --- | ---: | --- |
| `check_distribution.py` | 31 | Real discovery/probe, explicit and PATH selection, configuration/format invalidation, invalid selections, missing/incompatible formats, optional tool isolation, actual selected BibTeX execution, missing-package remedies, project cache invalidation, reports, timeout and source preservation |
| `check_launcher.js` | 18 | WSL list decoding, selection and UNC conflicts, path translation, actual Node-to-WSL environment reporting and failure reporting |
| `check_extension_live.js` | 22 | Mock VS Code host, distribution settings, JSON report command, environment logging and existing edit/watcher behavior |
| `check_cpp.py` | 346 | Existing 100-page differential rendering and edit regressions |
| `check_project_assets.py` | 27 | Nested projects, shared dependencies, checkpoint edits, reloads and source preservation |
| `check_included_edits.py` | 189 | Included-file edits, cache invalidation and background convergence/adoption |
| `check_build_tools.py` | 77 | Real BibTeX/Biber/MakeIndex, selection-aware missing-tool/cancellation fixtures, reuse, failures and bounded convergence |
| `check_external_project.py` | 25 | LuaLaTeX/XeLaTeX/pdfLaTeX full builds, overlays, error recovery and source preservation |

New reports are [distribution.json](../results/distribution.json),
[launcher.json](../results/launcher.json), and
[external-projects-distribution.json](../results/external-projects-distribution.json).
Other suites retain their existing report filenames under `results/`. The
distribution and shared-asset reports record the tested backend hash.

The v0.0.18 VSIX is packaged and byte-verified, with its artifact and runtime
hashes in [package-0.0.18.json](../results/package-0.0.18.json). It is not installed
automatically. No latency benchmark or actual VS Code extension-host run was
performed for this release.

## Limits

- Actual integration is validated against the installed TeX Live in Ubuntu-22.04
  WSL. Selection of other WSL names is tested with fixtures; no additional WSL
  installation or different TeX Live release was installed for these checks.
- Preflight establishes basic format/package compatibility, not compatibility
  with every package a document might load. Project compilation remains the
  check for project-specific requirements.
- The bundled engine is still LuaHBTeX 1.14. Incompatible newer formats require a
  compatible installation or future engine/format work; formats are not rebuilt
  automatically. Native Windows/macOS checkpoint engines and MiKTeX integration
  are not implemented.
- Reopen the preview after external package maintenance. Active sessions do not
  watch system trees, and a running backend retains its selected preflight state.
  Library dependencies of external tools are not individually fingerprinted.
- Discovery covers PATH, explicit directories and conventional Linux x86-64 TeX
  Live paths. WSL drive translation assumes the standard `/mnt` mount layout.
- Preflight runs before the request reader starts. Closing a preview during a
  probe can wait for that bounded probe to finish. The cache has no eviction
  policy. No new edit-latency or real VS Code-host measurements are claimed.
