import { useState, useRef, useEffect, useCallback } from 'react';
import api from '../lib/api';

/**
 * Input with @mention autocomplete.
 * Detects "@" then letters, queries /search/global for users, and shows a popup.
 * On select, replaces the active @token with "@Name ".
 */
export default function MentionInput({
  value,
  onChange,
  onSubmit,
  placeholder,
  disabled,
  testId = 'comment-input',
  className = '',
}) {
  const inputRef = useRef(null);
  const popupRef = useRef(null);
  const [mentionQuery, setMentionQuery] = useState(null); // null = inactive
  const [mentionStart, setMentionStart] = useState(-1);
  const [suggestions, setSuggestions] = useState([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [loading, setLoading] = useState(false);

  // Fetch suggestions when query changes
  useEffect(() => {
    if (mentionQuery === null) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    const q = mentionQuery.trim();
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get(`/search/mentions?q=${encodeURIComponent(q)}&limit=6`);
        if (!cancelled) {
          setSuggestions((data.users || []).slice(0, 6));
          setActiveIdx(0);
        }
      } catch {
        if (!cancelled) setSuggestions([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 150);
    return () => { cancelled = true; clearTimeout(t); };
  }, [mentionQuery]);

  // Parse the text around caret to detect an active @token
  const detectMention = useCallback((text, caret) => {
    // Walk backwards from caret
    let i = caret - 1;
    let token = '';
    while (i >= 0) {
      const ch = text[i];
      if (ch === '@') {
        // Must be at start or preceded by whitespace
        if (i === 0 || /\s/.test(text[i - 1])) {
          return { start: i, query: token };
        }
        return null;
      }
      if (/\s/.test(ch)) return null;
      token = ch + token;
      i--;
    }
    return null;
  }, []);

  const handleChange = (e) => {
    const newVal = e.target.value;
    onChange(newVal);
    const caret = e.target.selectionStart ?? newVal.length;
    const m = detectMention(newVal, caret);
    if (m) {
      setMentionStart(m.start);
      setMentionQuery(m.query);
    } else {
      setMentionStart(-1);
      setMentionQuery(null);
    }
  };

  const insertMention = useCallback((user) => {
    if (mentionStart < 0 || !user) return;
    const before = value.slice(0, mentionStart);
    const caret = inputRef.current?.selectionStart ?? value.length;
    const after = value.slice(caret);
    const name = (user.name || user.email || '').trim();
    const inserted = `@${name} `;
    const next = before + inserted + after;
    onChange(next);
    setMentionStart(-1);
    setMentionQuery(null);
    setSuggestions([]);
    // Move caret after insertion
    setTimeout(() => {
      try {
        const pos = (before + inserted).length;
        inputRef.current?.setSelectionRange(pos, pos);
        inputRef.current?.focus();
      } catch { /* ignore */ }
    }, 0);
  }, [mentionStart, value, onChange]);

  const handleKeyDown = (e) => {
    const popupOpen = mentionQuery !== null && suggestions.length > 0;
    if (popupOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIdx(i => Math.min(i + 1, suggestions.length - 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIdx(i => Math.max(0, i - 1));
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        insertMention(suggestions[activeIdx]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setMentionQuery(null);
        setMentionStart(-1);
        return;
      }
    }
    if (e.key === 'Enter' && !popupOpen && onSubmit) {
      e.preventDefault();
      onSubmit();
    }
  };

  // Close popup on outside click
  useEffect(() => {
    if (mentionQuery === null) return;
    const onClick = (e) => {
      if (popupRef.current && popupRef.current.contains(e.target)) return;
      if (inputRef.current && inputRef.current.contains(e.target)) return;
      setMentionQuery(null);
      setMentionStart(-1);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [mentionQuery]);

  const popupOpen = mentionQuery !== null && (loading || suggestions.length > 0);

  return (
    <div className="relative flex-1">
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        data-testid={testId}
        className={`flex h-10 w-full rounded-xl border border-[#E2E4E0] bg-transparent px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[#4A5D4E]/20 ${className}`}
      />
      {popupOpen && (
        <div
          ref={popupRef}
          data-testid="mention-suggestions"
          className="absolute bottom-full left-0 mb-1 w-[280px] bg-white border border-[#E2E4E0] rounded-xl shadow-lg overflow-hidden z-50"
        >
          {loading && suggestions.length === 0 && (
            <div className="px-3 py-2 text-xs text-[#9CA3AF]">Suche...</div>
          )}
          {suggestions.map((u, idx) => (
            <button
              key={u.user_id}
              type="button"
              data-testid={`mention-suggestion-${idx}`}
              onClick={() => insertMention(u)}
              onMouseEnter={() => setActiveIdx(idx)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm ${idx === activeIdx ? 'bg-[#4A5D4E]/10' : 'hover:bg-[#F3F4F1]'}`}
            >
              <div className="w-7 h-7 rounded-full bg-[#4A5D4E]/20 flex items-center justify-center text-[10px] font-bold text-[#4A5D4E] flex-shrink-0">
                {(u.name || u.email || '?').slice(0, 2).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-[#1C1F1D] truncate">{u.name || u.email}</p>
                {u.email && u.name && (
                  <p className="text-[10px] text-[#9CA3AF] truncate">{u.email}</p>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
