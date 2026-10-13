# Licensing

The [MIT license](LICENSE) covers TeXAstra's original code, examples, and
documentation, except the files and upstream material identified below. It does
not replace third-party licenses or make the complete binary distribution MIT-only.

| Material | License |
| --- | --- |
| Optional bundled pdfTeX and linked xpdf library | GPL-2.0-or-later; matching TeX Live sources and pdfTeX notices accompany the build |
| Original extension, webview, tools, and examples | MIT |
| `native/renderer.hpp`, which adapts PyMuPDF geometry code | AGPL-3.0; Artifex Software and contributors retain their copyrights |
| Patched LuaHBTeX and upstream material in `engine/patch.py` | GPL-2.0-or-later and upstream component licenses |
| MuPDF/PyMuPDF and the combined native renderer executable | AGPL-3.0 |
| Other bundled libraries and Microsoft runtime files | Their respective licenses; see the dependency notices |

Original MIT-covered contributions remain available under MIT. When distributed
as part of the linked native application, the combined work must also satisfy its
GPL/AGPL obligations. The Windows compiler module uses the GPLv3 option of its
GPL-2.0-or-later grant when combined with AGPLv3 components. Existing copyright and
license notices must be preserved.

Each binary release is accompanied by `texastra-<version>-<target>-sources.zip`, containing the
matching project source, build recipes, pinned upstream archives, and dependency
notices. VSIX packages retain project runtime source, license texts, and dependency
notices; large build-source archives are supplied in that separate download.
The packaged `SOURCE.md` links directly to the matching archive, and `SOURCE.json`
records its SHA-256. Publish the source ZIP alongside its VSIX on the same release,
at the linked URL with equivalent access and no additional charge. Source
availability is not conditional on payment or registration.

Read [native/THIRD_PARTY.md](native/THIRD_PARTY.md),
[native/WINDOWS-NOTICES.md](native/WINDOWS-NOTICES.md), and the license texts in
`licenses/` before redistributing the runtime. Microsoft redistributables are
unmodified system runtime components and are governed by Microsoft's terms.

Upstream references: [MuPDF licensing](https://mupdf.readthedocs.io/en/latest/license.html)
and [GNU license compatibility](https://www.gnu.org/licenses/gpl-faq.html#AGPLGPL).
