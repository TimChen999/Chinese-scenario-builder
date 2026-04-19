/**
 * Renders the OCR'd source text VERBATIM in plain selectable DOM.
 *
 * Composition contract with the Pinyin Tool extension (DESIGN.md
 * Section 9). This component MUST:
 *
 *   - render the text inside a `<pre>` (or `<p>` / `<span>`) so
 *     ordinary text-selection works
 *   - set `lang="zh"` so the OS picks a CJK font
 *   - set `data-scenario-content="raw"` so the extension (and any
 *     future tooling) can identify the node
 *   - use `whitespace-pre-wrap` so newlines are preserved
 *   - NOT apply `user-select: none`
 *   - NOT attach `mouseup` / `mousedown` handlers (the extension
 *     listens on `document` and a local stopPropagation would break
 *     its selection trigger)
 *   - NOT set `contenteditable` (interferes with selection events)
 *
 * The raw_content invariant from DESIGN.md Section 1 ("authenticity"):
 * we render the string as-is, character for character, no
 * normalization or reformatting.
 */

interface RawContentProps {
  /** Raw OCR text. Rendered verbatim; do NOT pre-process at the call site. */
  text: string;
}

/**
 * Render the source text. Tailwind `whitespace-pre-wrap` preserves
 * line breaks and consecutive spaces; `font-cjk` selects the OS's
 * CJK fallback set we configure in Tailwind's theme.
 */
export default function RawContent({ text }: RawContentProps) {
  return (
    <pre
      lang="zh"
      data-scenario-content="raw"
      className="scenario-raw-content font-cjk whitespace-pre-wrap break-words text-base leading-relaxed text-slate-900"
    >
      {text}
    </pre>
  );
}
