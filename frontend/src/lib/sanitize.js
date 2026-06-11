/**
 * Iter 270 — Zentraler HTML-Sanitizer für alle dangerouslySetInnerHTML-Aufrufe.
 *
 * Verwendet DOMPurify mit einer strikten Allow-List geeignet für:
 *  - Chat-Markdown (renderMarkdown) — Bold/Italic/Code/Link/Quote/Br
 *  - News-Posts (server-rendered post.content_html)
 *  - Meeting-Summaries (AI-generierter Markdown → HTML)
 *  - Newsletter-Previews (Backend-generiertes HTML mit Inline-Styles)
 *  - Aufgaben-Kommentare
 *
 * Per Default werden gefährliche Tags/Attribute (script, iframe, on*, javascript:)
 * gestrippt. Inline-Styles werden bei der `richContent` Variante erlaubt, da
 * Newsletter-HTML diese braucht.
 */
import DOMPurify from 'dompurify';

const SAFE_TAGS = [
  'a', 'p', 'br', 'strong', 'em', 'b', 'i', 'u', 'del', 's',
  'code', 'pre', 'kbd', 'mark',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'blockquote', 'hr',
  'span', 'div',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'img',
];
const SAFE_ATTRS = ['href', 'target', 'rel', 'src', 'alt', 'title', 'class', 'lang'];

/**
 * Sanitisiert User-generierten / serverseitig zusammengesetzten HTML für
 * dangerouslySetInnerHTML.
 */
export function sanitizeHTML(input) {
  if (input == null) return '';
  // Force all links to open in new tab with no-opener (XSS mitigation).
  const out = DOMPurify.sanitize(String(input), {
    ALLOWED_TAGS: SAFE_TAGS,
    ALLOWED_ATTR: SAFE_ATTRS,
    FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['onerror', 'onclick', 'onload', 'onmouseover', 'style'],
    ALLOW_DATA_ATTR: false,
  });
  return out;
}

/**
 * Erweiterte Variante: erlaubt zusätzlich inline `style`-Attribute (für
 * Newsletter-HTML-Previews mit Tabellen-Layout und Inline-CSS).
 */
export function sanitizeRichHTML(input) {
  if (input == null) return '';
  return DOMPurify.sanitize(String(input), {
    ALLOWED_TAGS: [...SAFE_TAGS, 'style'],
    ALLOWED_ATTR: [...SAFE_ATTRS, 'style', 'width', 'height', 'border', 'cellpadding', 'cellspacing', 'colspan', 'rowspan', 'align', 'valign', 'bgcolor'],
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form'],
    FORBID_ATTR: ['onerror', 'onclick', 'onload', 'onmouseover'],
    ALLOW_DATA_ATTR: false,
  });
}

// Add target="_blank" + rel="noopener" to ALL outbound <a> elements automatically.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

export default sanitizeHTML;
