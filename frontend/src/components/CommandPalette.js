import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Search, Newspaper, Video, MessageCircle, Users, Command } from 'lucide-react';
import api from '../lib/api';
import { useLanguage } from '../contexts/LanguageContext';

export default function CommandPalette({ open, onOpenChange }) {
  const { t } = useLanguage();
  const SECTIONS = [
    { key: 'news', icon: Newspaper, label: t('news') || 'News', color: '#4A5D4E', route: (it) => `/news` },
    { key: 'meetings', icon: Video, label: t('meetings'), color: '#D4A373', route: (it) => `/meetings` },
    { key: 'chats', icon: MessageCircle, label: t('chat'), color: '#6B8E23', route: (it) => `/chat?conv=${it.conversation_id}` },
    { key: 'users', icon: Users, label: t('users'), color: '#C87967', route: (it) => `/chat?userId=${it.user_id}` },
  ];
  const [q, setQ] = useState('');
  const [results, setResults] = useState({ news: [], meetings: [], chats: [], users: [] });
  const [loading, setLoading] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
    else { setQ(''); setResults({ news: [], meetings: [], chats: [], users: [] }); setActiveIdx(0); }
  }, [open]);

  useEffect(() => {
    if (!open || !q || q.length < 2) {
      setResults({ news: [], meetings: [], chats: [], users: [] });
      return;
    }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const { data } = await api.get(`/search/global?q=${encodeURIComponent(q)}&limit=5`);
        if (!cancelled) setResults(data);
      } catch { if (!cancelled) setResults({ news: [], meetings: [], chats: [], users: [] }); }
      finally { if (!cancelled) setLoading(false); }
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q, open]);

  const flatItems = SECTIONS.flatMap(sec => (results[sec.key] || []).map(it => ({ ...it, _section: sec })));

  const navigateTo = useCallback((item) => {
    if (!item) return;
    onOpenChange(false);
    const route = item._section.route(item);
    if (item._section.key === 'meetings') navigate(`/meetings/${item.meeting_id}/lobby`);
    else if (item._section.key === 'news') navigate('/news');
    else navigate(route);
  }, [navigate, onOpenChange]);

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, flatItems.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(i => Math.max(0, i - 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); navigateTo(flatItems[activeIdx]); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px] p-0 overflow-hidden">
        <DialogHeader className="sr-only">
          <DialogTitle>{t('globalSearch')}</DialogTitle>
          <DialogDescription>{t('searchDescription')}</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2 border-b border-[#E2E4E0] px-4 py-3">
          <Search className="w-4 h-4 text-[#9CA3AF]" />
          <input
            ref={inputRef}
            value={q}
            onChange={e => { setQ(e.target.value); setActiveIdx(0); }}
            onKeyDown={onKeyDown}
            placeholder={t('searchPlaceholder')}
            className="flex-1 outline-none text-sm text-[#1C1F1D] bg-transparent"
            data-testid="command-palette-input"
          />
          <kbd className="hidden sm:flex items-center gap-0.5 text-[10px] text-[#9CA3AF] border border-[#E2E4E0] px-1.5 py-0.5 rounded">ESC</kbd>
        </div>
        <div className="max-h-[400px] overflow-y-auto">
          {loading && <div className="p-6 text-center text-xs text-[#9CA3AF]">{t('searching')}</div>}
          {!loading && q.length >= 2 && flatItems.length === 0 && (
            <div className="p-6 text-center text-xs text-[#9CA3AF]">{t('noResultsFor')} "{q}"</div>
          )}
          {!loading && q.length < 2 && (
            <div className="p-6 text-center text-xs text-[#9CA3AF]">
              <Command className="w-6 h-6 mx-auto mb-2 opacity-50" />
              {t('typeAtLeast2')}
              <p className="mt-2 text-[10px]">{t('searchShortcutHint')}</p>
            </div>
          )}
          {SECTIONS.map(sec => {
            const items = results[sec.key] || [];
            if (items.length === 0) return null;
            const Icon = sec.icon;
            return (
              <div key={sec.key} className="py-1" data-testid={`palette-section-${sec.key}`}>
                <div className="px-4 py-1 text-[10px] font-bold uppercase tracking-wider text-[#9CA3AF]">{sec.label}</div>
                {items.map((it, idx) => {
                  const flatI = flatItems.findIndex(x => x === flatItems.find(f => f._section.key === sec.key && (f.post_id || f.meeting_id || f.message_id || f.user_id) === (it.post_id || it.meeting_id || it.message_id || it.user_id)));
                  const isActive = flatI === activeIdx;
                  return (
                    <button key={idx} onClick={() => navigateTo({ ...it, _section: sec })}
                      className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm ${isActive ? 'bg-[#4A5D4E]/10' : 'hover:bg-[#F3F4F1]'}`}
                      data-testid={`palette-result-${sec.key}-${idx}`}>
                      <Icon className="w-4 h-4 flex-shrink-0" style={{ color: sec.color }} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-[#1C1F1D] truncate">
                          {it.title || it.name || it.content || it.meeting_code}
                        </p>
                        {(it.excerpt || it.email || it.sender_name) && (
                          <p className="text-[10px] text-[#9CA3AF] truncate">{it.excerpt || it.email || `${t('fromBy')} ${it.sender_name}`}</p>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
        <div className="flex items-center justify-between px-4 py-2 border-t border-[#E2E4E0] text-[10px] text-[#9CA3AF]">
          <span>{t('paletteHintNav')}</span>
          <span>Cmd/Strg + K</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
