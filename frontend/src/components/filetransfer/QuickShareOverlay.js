import { useEffect, useState, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import api from '../../lib/api';
import { toast } from 'sonner';
import { Send, Upload, X } from 'lucide-react';

/**
 * Global Drag-and-Drop overlay (iter 386d).
 *
 * Mount once near the app root. Listens to window-level drag events; when
 * the user drags one or more files anywhere over the app, a full-screen
 * teal overlay appears. Dropping the files there creates a new Filetransfer
 * in one shot:
 *
 *  • On the chat page (`/chat?conv=…` or `/chat/conv_…`), the active
 *    conversation's first OTHER member is added as the recipient and a
 *    small "Filetransfer gesendet" message with the permalink is appended
 *    to the chat.
 *  • Anywhere else, the transfer is created without a recipient and the
 *    user is navigated to /filetransfer/{tid} to finish it.
 *
 * The component opts out for guests + unauthenticated routes via the
 * `data-no-global-drop` attribute on either the document or any ancestor.
 */
export default function QuickShareOverlay() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);
  const dragDepth = useRef(0);

  useEffect(() => {
    // Disable on auth-less routes
    if (!user) return undefined;
    if (location.pathname.startsWith('/filetransfer/public/')) return undefined;
    if (location.pathname.startsWith('/login') || location.pathname.startsWith('/signup')) return undefined;
    if (document.body.hasAttribute('data-no-global-drop')) return undefined;

    const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes('Files');
    const onEnter = (e) => {
      if (!hasFiles(e)) return;
      dragDepth.current++;
      setDrag(true);
    };
    const onOver = (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
    };
    const onLeave = () => {
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDrag(false);
    };
    const onDrop = async (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth.current = 0;
      setDrag(false);
      const files = Array.from(e.dataTransfer?.files || []);
      if (!files.length) return;
      await sendQuickTransfer(files);
    };

    window.addEventListener('dragenter', onEnter);
    window.addEventListener('dragover', onOver);
    window.addEventListener('dragleave', onLeave);
    window.addEventListener('drop', onDrop);
    return () => {
      window.removeEventListener('dragenter', onEnter);
      window.removeEventListener('dragover', onOver);
      window.removeEventListener('dragleave', onLeave);
      window.removeEventListener('drop', onDrop);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, location.pathname]);

  async function sendQuickTransfer(files) {
    setUploading(true);
    try {
      // Figure out chat recipient if we're on a chat URL
      let recipientId = null;
      let convId = null;
      const m = location.pathname.match(/^\/chat\/?$/) ? null : null;
      const sp = new URLSearchParams(location.search);
      convId = sp.get('conv') || (location.pathname.match(/^\/chat\/(conv_[\w-]+)/) || [])[1] || null;
      if (convId) {
        try {
          const { data: conv } = await api.get(`/chat/conversations/${convId}`);
          const others = (conv.members || []).filter(m => m.user_id !== user.user_id);
          if (conv.type === 'direct' && others.length === 1) recipientId = others[0].user_id;
        } catch { /* ignore */ }
      }
      const { data: t } = await api.post('/filetransfer/transfers', {
        message: convId ? `Geteilt aus Chat` : '',
        recipient_user_ids: recipientId ? [recipientId] : [],
        expiry_days: 14,
      });
      void m;
      for (const f of files) {
        const fd = new FormData();
        fd.append('file', f);
        try {
          await api.post(`/filetransfer/transfers/${t.transfer_id}/files`, fd, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
        } catch (err) {
          toast.error(`${f.name}: ${err?.response?.data?.detail || 'Upload fehlgeschlagen'}`);
        }
      }
      const url = `${window.location.origin}/filetransfer/${t.transfer_id}`;
      if (convId) {
        try {
          await api.post(`/chat/conversations/${convId}/messages`, {
            content: `📦 ${files.length} Datei(en) per Filetransfer: ${url}`,
          });
          toast.success(`${files.length} Datei(en) im Chat geteilt`);
        } catch {
          toast.success(`Transfer erstellt — Link in Zwischenablage`);
          try { await navigator.clipboard.writeText(url); } catch { /* ignore */ }
        }
      } else {
        toast.success(`Transfer mit ${files.length} Datei(en) erstellt`);
        navigate(`/filetransfer/${t.transfer_id}`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Filetransfer fehlgeschlagen');
    } finally { setUploading(false); }
  }

  if (!drag && !uploading) return null;
  return (
    <div
      data-testid="global-ft-dropzone"
      className="fixed inset-0 z-[9998] bg-[#4A5D4E]/85 backdrop-blur-sm flex items-center justify-center pointer-events-none"
    >
      <div className="bg-white rounded-2xl px-6 py-5 sm:px-10 sm:py-8 max-w-md mx-3 text-center shadow-2xl pointer-events-auto">
        {uploading ? (
          <>
            <Send className="w-8 h-8 sm:w-10 sm:h-10 mx-auto text-[#4A5D4E] animate-pulse mb-2" />
            <p className="text-base sm:text-lg font-semibold text-[#1C1F1D]">Transfer wird erstellt…</p>
            <p className="text-xs text-[#6B7280] mt-1">Die Dateien werden hochgeladen.</p>
          </>
        ) : (
          <>
            <Upload className="w-8 h-8 sm:w-10 sm:h-10 mx-auto text-[#4A5D4E] mb-2" />
            <p className="text-base sm:text-lg font-semibold text-[#1C1F1D]">Hier ablegen, um zu teilen</p>
            <p className="text-xs text-[#6B7280] mt-1">
              {location.pathname.startsWith('/chat') ? 'Wird im aktuellen Chat geteilt' : 'Wird als neuer Filetransfer erstellt'}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
