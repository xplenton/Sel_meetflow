// Simple chat markdown renderer (bold, italic, strikethrough, code, quotes, links, line breaks).
// Iter 270 — output is sanitised via lib/sanitize.js downstream, but we also
// pre-escape inside URLs to prevent href-breakout XSS (e.g. `https://x" onerror=`).
import { sanitizeHTML } from './sanitize';

export function renderMarkdown(text) {
  if (!text) return '';
  const html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```([\s\S]*?)```/g, '<pre class="bg-black/10 rounded px-2 py-1 text-xs font-mono my-1 overflow-x-auto">$1</pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-black/10 rounded px-1 py-0.5 text-xs font-mono">$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/~~(.+?)~~/g, '<del>$1</del>')
    .replace(/^&gt; (.+)$/gm, '<blockquote class="border-l-2 border-current/30 pl-2 opacity-80">$1</blockquote>')
    // Iter 270 — escape `"` inside URL captures so attacker cannot break out of href
    .replace(/(https?:\/\/[^\s<"]+)/g, (m) => `<a href="${m.replace(/"/g, '&quot;')}" target="_blank" rel="noopener" class="underline opacity-80">${m}</a>`)
    .replace(/\n/g, '<br/>');
  // Final defense: pass through DOMPurify
  return sanitizeHTML(html);
}
