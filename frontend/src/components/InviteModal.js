/**
 * iter 210 — In-Meeting "Einladen"-Modal.
 *
 * Lets a host (or any participant) invite others to the active meeting in
 * three ways at once:
 *   1. Copy the join URL (always available, instant).
 *   2. Pick existing platform users from a searchable list — invitation is
 *      delivered as in-app notification + email (handled by /meetings/{id}/invite).
 *   3. Type external email addresses (one per line / comma separated) for
 *      guests that don't have an account yet.
 *
 * Mirrors the look-and-feel of TaskDetailDialog so it sits naturally next to
 * other in-meeting overlays. Uses useAuth() to surface "you" and excludes
 * the current host from the user picker.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import { Loader2, Copy, Check, Send, Search, Mail, Link as LinkIcon, X } from 'lucide-react';
import { toast } from 'sonner';
import api from '../lib/api';

export default function InviteModal({ open, onClose, meetingId, meetingTitle }) {
  const [users, setUsers] = useState([]);
  const [query, setQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [externalEmails, setExternalEmails] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [copied, setCopied] = useState(false);

  // Build the absolute join link from the current origin so it works in dev,
  // preview AND production without baking in any environment variable.
  const joinLink = useMemo(
    () => `${window.location.origin}/meetings/${meetingId}/join`,
    [meetingId]
  );

  useEffect(() => {
    if (!open) return;
    api.get('/chat/users').then(({ data }) => setUsers(data || [])).catch(() => {});
    setSelectedIds(new Set());
    setExternalEmails('');
    setMessage('');
    setCopied(false);
    setQuery('');
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return users.slice(0, 30);
    return users.filter(u =>
      (u.name || '').toLowerCase().includes(q) ||
      (u.email || '').toLowerCase().includes(q)
    ).slice(0, 30);
  }, [users, query]);

  const toggleUser = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(joinLink);
      setCopied(true);
      toast.success('Link kopiert');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Konnte Link nicht kopieren');
    }
  };

  // Parse one-per-line or comma-separated emails, dedupe + lowercase.
  const parseExternalEmails = () => {
    const raw = externalEmails.split(/[\s,;]+/).map(s => s.trim()).filter(Boolean);
    const seen = new Set();
    const valid = [];
    for (const e of raw) {
      const lower = e.toLowerCase();
      if (seen.has(lower)) continue;
      seen.add(lower);
      // Permissive regex — server validates further.
      if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(lower)) valid.push(lower);
    }
    return valid;
  };

  const handleSend = async () => {
    // Resolve selected users → their emails
    const userEmails = users
      .filter(u => selectedIds.has(u.user_id))
      .map(u => (u.email || '').toLowerCase())
      .filter(Boolean);
    const externals = parseExternalEmails();
    const emails = Array.from(new Set([...userEmails, ...externals]));
    if (!emails.length) {
      toast.error('Bitte wähle Personen oder gib eine E-Mail ein');
      return;
    }
    setSending(true);
    try {
      const { data } = await api.post(`/meetings/${meetingId}/invite`, {
        emails,
        message: message.trim() || `Du bist eingeladen zu "${meetingTitle || 'Meeting'}"`,
      });
      toast.success(`${data.count || emails.length} Einladung(en) gesendet`);
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Einladungen konnten nicht gesendet werden');
    } finally {
      setSending(false);
    }
  };

  const totalSelected = selectedIds.size + parseExternalEmails().length;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg p-0 overflow-hidden bg-white" data-testid="invite-modal">
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-[#E2E4E0]">
          <DialogTitle className="text-base font-semibold text-[#1A1D1B] flex items-center gap-2">
            <Send className="w-4 h-4 text-[#4A5D4E]" />Personen einladen
          </DialogTitle>
        </DialogHeader>

        <div className="px-5 py-4 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* Section 1: Copy meeting link */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-[#6B7280] uppercase tracking-wider flex items-center gap-1.5">
              <LinkIcon className="w-3 h-3" />Meeting-Link
            </label>
            <div className="flex items-stretch gap-2">
              <div className="flex-1 px-3 py-2 bg-[#F5F4F0] rounded-md text-xs text-[#1A1D1B] truncate font-mono" data-testid="invite-join-link">
                {joinLink}
              </div>
              <Button onClick={copyLink} size="sm"
                className={`h-9 px-3 text-xs ${copied ? 'bg-[#4A5D4E]' : 'bg-[#1A1D1B]'} text-white hover:opacity-90`}
                data-testid="invite-copy-link">
                {copied ? <><Check className="w-3.5 h-3.5 mr-1" />Kopiert</> : <><Copy className="w-3.5 h-3.5 mr-1" />Kopieren</>}
              </Button>
            </div>
          </div>

          {/* Section 2: Pick platform users */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-[#6B7280] uppercase tracking-wider">
              Aus Personen-Liste
              {selectedIds.size > 0 && (
                <span className="ml-1.5 text-[#4A5D4E] normal-case font-normal">({selectedIds.size} ausgewählt)</span>
              )}
            </label>
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9CA3AF]" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Suchen nach Name oder E-Mail..."
                className="h-8 text-xs pl-8 border-[#E2E4E0]"
                data-testid="invite-user-search" />
            </div>
            <div className="max-h-44 overflow-y-auto border border-[#E2E4E0] rounded-md divide-y divide-[#E2E4E0]">
              {filtered.length === 0 ? (
                <div className="px-3 py-4 text-xs text-[#9CA3AF] text-center">Keine Treffer</div>
              ) : (
                filtered.map(u => {
                  const sel = selectedIds.has(u.user_id);
                  return (
                    <button key={u.user_id}
                      type="button"
                      onClick={() => toggleUser(u.user_id)}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[#F5F4F0] transition ${sel ? 'bg-[#4A5D4E]/5' : ''}`}
                      data-testid={`invite-user-${u.user_id}`}>
                      <div className={`w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center ${sel ? 'bg-[#4A5D4E] border-[#4A5D4E]' : 'border-[#D1D5DB]'}`}>
                        {sel && <Check className="w-3 h-3 text-white" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-[#1A1D1B] truncate">{u.name || u.email}</div>
                        <div className="text-[10px] text-[#6B7280] truncate">{u.email}</div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Section 3: External emails */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-[#6B7280] uppercase tracking-wider flex items-center gap-1.5">
              <Mail className="w-3 h-3" />Externe E-Mail-Adressen (optional)
            </label>
            <Textarea value={externalEmails} onChange={(e) => setExternalEmails(e.target.value)}
              placeholder="alice@example.com, bob@example.com&#10;eine pro Zeile oder Komma-getrennt"
              className="text-xs border-[#E2E4E0] min-h-[60px]"
              data-testid="invite-external-emails" />
            {parseExternalEmails().length > 0 && (
              <div className="flex flex-wrap gap-1">
                {parseExternalEmails().map(e => (
                  <Badge key={e} variant="outline" className="text-[10px] border-[#4A5D4E]/30 text-[#4A5D4E]">{e}</Badge>
                ))}
              </div>
            )}
          </div>

          {/* Section 4: Optional message */}
          <div className="space-y-1.5">
            <label className="text-[11px] font-semibold text-[#6B7280] uppercase tracking-wider">
              Persönliche Nachricht (optional)
            </label>
            <Textarea value={message} onChange={(e) => setMessage(e.target.value)}
              placeholder="z.B. Wir starten in 5 Minuten..."
              className="text-xs border-[#E2E4E0] min-h-[50px]"
              data-testid="invite-message" />
          </div>
        </div>

        <div className="px-5 py-3 border-t border-[#E2E4E0] flex items-center justify-between gap-2 bg-[#FAFAF9]">
          <span className="text-[11px] text-[#6B7280]">
            {totalSelected > 0 ? `${totalSelected} Empfänger${totalSelected === 1 ? '' : ''} bereit` : 'Keine Empfänger ausgewählt'}
          </span>
          <div className="flex items-center gap-2">
            <Button onClick={onClose} variant="outline" size="sm" className="h-8 text-xs" data-testid="invite-cancel">
              <X className="w-3.5 h-3.5 mr-1" />Schließen
            </Button>
            <Button onClick={handleSend} size="sm"
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white h-8 text-xs"
              disabled={sending || totalSelected === 0}
              data-testid="invite-send">
              {sending ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Send className="w-3.5 h-3.5 mr-1" />}
              {sending ? 'Sende...' : 'Einladungen senden'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
