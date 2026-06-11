import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import CommandPalette from './CommandPalette';
import { toast } from 'sonner';

/**
 * Global keyboard shortcuts + command palette mount.
 *
 * Shortcuts:
 *  - Cmd/Ctrl + K         → open command palette
 *  - g then n             → go to news
 *  - g then c             → go to chat
 *  - g then d             → go to dashboard
 *  - g then m             → go to meetings
 *  - g then u             → go to surveys
 *  - m                    → create new meeting
 *  - ?                    → show help toast
 */
export default function KeyboardShortcuts() {
  const navigate = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const leaderRef = useRef(null); // tracks "g" leader key with timeout

  useEffect(() => {
    const onKey = (e) => {
      // Ignore when user is typing in input/textarea/contenteditable
      const tag = (e.target?.tagName || '').toLowerCase();
      const editable = e.target?.isContentEditable;
      const typing = editable || tag === 'input' || tag === 'textarea' || tag === 'select';

      // Cmd/Ctrl+K always works even when typing
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setPaletteOpen(o => !o);
        return;
      }

      if (typing) return;

      // Leader key "g" starts a chord
      if (e.key === 'g' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        leaderRef.current = 'g';
        setTimeout(() => { if (leaderRef.current === 'g') leaderRef.current = null; }, 1200);
        return;
      }

      if (leaderRef.current === 'g') {
        leaderRef.current = null;
        switch (e.key) {
          case 'n': navigate('/news'); return;
          case 'c': navigate('/chat'); return;
          case 'd': navigate('/dashboard'); return;
          case 'm': navigate('/meetings'); return;
          case 'u': navigate('/surveys'); return;
          case 'k': navigate('/calendar'); return;
          default: return;
        }
      }

      // Single-key shortcuts
      if (e.key === '?' && !e.shiftKey === false) {
        toast.info('Shortcuts: Strg+K = Suche · g+n = News · g+c = Chat · g+d = Dashboard · g+m = Meetings · g+u = Umfragen', { duration: 6000 });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [navigate]);

  return <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />;
}
