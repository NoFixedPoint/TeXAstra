# Live LaTeX Preview

The language of a LaTeX editing experience with a live rendered document and two-way navigation between source and output.

## Language

**Live preview**:
A rendered view of the LaTeX document that updates as its source is edited.
_Avoid_: Export, static preview

**Forward synchronization**:
Navigation from a location in the LaTeX source to its corresponding location in the rendered document.
_Avoid_: Reverse synchronization

**Reverse synchronization**:
Navigation from a location in the rendered document to the source responsible for that content.
_Avoid_: Forward synchronization

**Preview caret**:
A visible text position within the rendered document used for selection and navigation. Source edits take place in the source editor.

**Token-level synchronization**:
Correspondence between rendered content and the specific source token responsible for it, including ordinary text, math, and TikZ text. A source line alone is not a sufficiently precise destination.
_Avoid_: Line-level synchronization, exact character mapping

**Macro-origin fallback**:
The source argument or macro invocation used as the navigation destination for generated content that has no unique source character.

**Edit-to-preview latency**:
The elapsed time between a source edit and the appearance of the corresponding updated content in the live preview.
_Avoid_: Compilation time

**Stale preview**:
A last successfully rendered view that no longer corresponds to the current source. Its navigation targets are usable only when their correspondence to the current source has been validated.

**Acceptance corpus**:
The agreed collection of document content and edit scenarios used to judge preview speed, rendering compatibility, and synchronization precision.

**Visible-page update**:
An updated rendering of the page currently being viewed that reflects the current source edit. Other pages or cross-references may still await convergence.

**Provisional preview**:
A preview whose current visible content has been updated but whose dependent layout or references may still change as the document converges.
_Avoid_: Stale preview

**Document convergence**:
The point at which the document's layout and references have stabilized for a given source revision under the selected typesetting configuration.

**Continuous-typing smoothness**:
The preview's ability to make visible progress throughout a sustained burst of source edits while keeping the caret and scroll position stable.
_Avoid_: Isolated-edit latency

**Glyph origin**:
The source token or source range responsible for a rendered glyph, including an argument or macro invocation when expansion produces the content.
_Avoid_: Nearby source line
