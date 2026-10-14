# macOS setup

**TeXAstra: Open Document** prepares
TeX Live 2021 automatically on first use in a trusted workspace. **Show LaTeX
Environment** also prepares it when necessary.

- [Install the prebuilt macOS package](../README.md#macos).
- [Build, validate, and package on macOS](../BUILDING.md#macos-apple-silicon-and-intel).

Setup runs in VS Code's JavaScript runtime using macOS's system curl, tar, and
Perl. It requires internet access, but no Python, administrator access, or user
settings changes. Downloads use the historical TeX Live repository; the installer
archive is verified against a pinned SHA-256 before extraction or execution.
The basic scheme includes TikZ, booktabs, geometry, luaotfload, and SyncTeX.

The managed tree lives under the extension's `globalStorageUri` (normally
`~/Library/Application Support/Code/User/globalStorage/texastra.texastra`). Setup
copies the bundled LuaHBTeX 1.14 and pdfTeX 1.40.22 engines into this tree and
generates matching formats. It changes neither the system PATH nor MacTeX.
The selected path is passed directly to the backend, so it is never written to
workspace settings or synced to another computer.

Completed installations survive extension reloads and updates. A change to the
bundled engines creates a separate compatible tree. Concurrent requests in one
window share setup; separate windows can create independent trees safely. Each
attempt has its own final path because TeX configuration embeds absolute paths.
Failed or cancelled attempts are removed; an abruptly terminated host can leave
an incomplete directory, which future setup ignores.

An explicit `texastra.texBinDirectory` (including a legacy `bakoma` setting)
skips managed setup. Users with an existing working isolated TeX tree can keep
that setting. Clear it to switch to automatic setup.

If setup fails, check **Output → TeXAstra**, restore network access if necessary,
and run **Open Document** again. Cancel stops the installer and its subprocesses.
**Show LaTeX Environment** reports the selected binary directory; use that tree's
`tlmgr` to add packages required by a document.

Automatic setup, format generation, LuaLaTeX/PDFLaTeX compilation, and reuse
passed on both Apple Silicon and Intel in [native CI](https://github.com/NoFixedPoint/TeXAstra/actions/runs/38503902074).
The same jobs passed architecture/signature audits, extension tests, compiler
checks, and extracted-VSIX rendering/navigation checks. The first Intel package
check failed during a retained TikZ edit; rerunning the unchanged commit passed.
Interactive VS Code GUI testing remains outside this validation.
