/**
 * Copy text to clipboard with three-tier fallback:
 *
 *   1. modern `navigator.clipboard.writeText` — works on HTTPS top-level docs.
 *   2. legacy hidden-textarea + `document.execCommand('copy')` — works in
 *      iframes when Permissions-Policy blocks the Clipboard API but the
 *      legacy command is still allowed.
 *   3. select an existing visible input element (`fallbackInput` arg) so the
 *      user can press Ctrl+C/⌘+C themselves. Used by the Profile page when
 *      the preview environment is sandboxed in a Permissions-Policy iframe.
 *
 * Returns:
 *   { ok: true,  method: 'clipboard' | 'execCommand' }
 *   { ok: false, method: 'manual', selected: <bool> }
 *
 * Callers may rely on `ok` for the toast wording.
 */
export async function copyToClipboard(text, fallbackInput = null) {
  // 1. modern API
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return { ok: true, method: 'clipboard' };
    }
  } catch { /* fall through */ }

  // 2. legacy execCommand via hidden textarea
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none;';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    let success = false;
    try { success = document.execCommand('copy'); } catch { success = false; }
    document.body.removeChild(textarea);
    if (success) return { ok: true, method: 'execCommand' };
  } catch { /* fall through */ }

  // 3. last-resort: select the visible input so the user can copy manually
  if (fallbackInput && typeof fallbackInput.select === 'function') {
    try {
      fallbackInput.focus();
      fallbackInput.select();
      return { ok: false, method: 'manual', selected: true };
    } catch { /* ignore */ }
  }
  return { ok: false, method: 'manual', selected: false };
}
