import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Checkbox } from './ui/checkbox';
import { Upload, CheckCircle2, XCircle, SkipForward, Loader2 } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

/**
 * Admin bulk-invite dialog (iter 119).
 *
 * Paste many emails (comma-, semicolon- or newline-separated), pick a
 * role + target group, optionally disable the email dispatch (useful for
 * pre-seeding accounts for a training workshop), fire the request, and
 * render a per-row success/skip/fail report the admin can screenshot.
 */
export default function BulkInviteDialog({ open, onClose }) {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [emailsText, setEmailsText] = useState('');
  const [role, setRole] = useState('member');
  const [groupId, setGroupId] = useState('');
  const [sendEmail, setSendEmail] = useState(true);
  const [result, setResult] = useState(null);

  const groupsQ = useQuery({
    queryKey: ['admin', 'groups'],
    queryFn: async () => (await api.get('/admin/groups')).data,
    enabled: open,
  });
  const groups = groupsQ.data || [];

  const bulkMutation = useMutation({
    mutationFn: async ({ emails, role, group_id, send_email }) =>
      (await api.post('/admin/users/bulk-invite', { emails, role, group_id, send_email })).data,
    onSuccess: (data) => {
      setResult(data);
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
      qc.invalidateQueries({ queryKey: ['admin', 'stats'] });
      qc.invalidateQueries({ queryKey: ['admin', 'groups'] });
      const s = data.summary || {};
      if (s.created === 0 && s.invalid > 0) toast.error(`Keine gültigen E-Mails (${s.invalid} ungültig)`);
      else if (s.failed > 0) toast.error(`${s.created} erstellt, aber ${s.failed} Mails konnten nicht gesendet werden`);
      else toast.success(`${s.created} Benutzer angelegt, ${s.sent} Mails gesendet`);
    },
    onError: (err) => toast.error(err.response?.data?.detail || 'Fehler beim Bulk-Invite'),
  });

  const parseEmails = () => emailsText
    .split(/[\s,;]+/)
    .map(s => s.trim())
    .filter(Boolean);

  const previewMutation = useMutation({
    mutationFn: async (emails) => (await api.post('/admin/users/bulk-invite/preview', { emails })).data,
  });
  const [preview, setPreview] = useState(null);

  const handlePreview = () => {
    const emails = parseEmails();
    if (emails.length === 0) { toast.error('Mindestens eine E-Mail erforderlich'); return; }
    previewMutation.mutate(emails, { onSuccess: (d) => setPreview(d), onError: () => toast.error('Preview fehlgeschlagen') });
  };

  const handleSubmit = () => {
    const emails = parseEmails();
    if (emails.length === 0) { toast.error('Mindestens eine E-Mail erforderlich'); return; }
    if (emails.length > 500) { toast.error('Maximal 500 E-Mails auf einmal'); return; }
    setResult(null);
    bulkMutation.mutate({ emails, role, group_id: groupId || undefined, send_email: sendEmail });
  };

  const handleClose = () => {
    if (bulkMutation.isPending) return; // don't close during request
    setEmailsText('');
    setResult(null);
    setPreview(null);
    setGroupId('');
    onClose();
  };

  const previewCount = parseEmails().length;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl" data-testid="bulk-invite-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="w-5 h-5 text-[#6B8E23]" />
            {t('inviteMultipleUsers')}
          </DialogTitle>
        </DialogHeader>

        {!result && (
          <div className="space-y-4">
            <div>
              <Label htmlFor="bulk-emails" className="text-xs font-medium text-[#4B5563] mb-2 block">
                {t('emailAddressesDelimited')}
              </Label>
              <Textarea
                id="bulk-emails"
                data-testid="bulk-invite-emails"
                value={emailsText}
                onChange={(e) => setEmailsText(e.target.value)}
                placeholder="anna@klinik.de&#10;boris@klinik.de&#10;carla@klinik.de, dennis@klinik.de"
                rows={8}
                className="font-mono text-sm"
              />
              <p className="text-xs text-[#6B7280] mt-1.5" data-testid="bulk-invite-preview-count">
                {previewCount} E-Mail{previewCount !== 1 ? 's' : ''} erkannt (max. 500)
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-xs font-medium text-[#4B5563] mb-2 block">Rolle</Label>
                <Select value={role} onValueChange={setRole}>
                  <SelectTrigger data-testid="bulk-invite-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="member">{t('member')}</SelectItem>
                    <SelectItem value="moderator">{t('moderator')}</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs font-medium text-[#4B5563] mb-2 block">Gruppe zuweisen (optional)</Label>
                <Select value={groupId || 'none'} onValueChange={(v) => setGroupId(v === 'none' ? '' : v)}>
                  <SelectTrigger data-testid="bulk-invite-group-select"><SelectValue placeholder="Keine Gruppe" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">— Keine Gruppe —</SelectItem>
                    {groups.map(g => (
                      <SelectItem key={g.group_id} value={g.group_id}>
                        {g.name} {g.is_system ? '(System)' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <Checkbox checked={sendEmail} onCheckedChange={(v) => setSendEmail(!!v)} data-testid="bulk-invite-send-email-toggle" />
              <span className="text-sm text-[#1C1F1D]">{t('sendEmailInvitesWithTempPassword')}</span>
            </label>

            <div className="flex gap-2 justify-end pt-2">
              <Button variant="outline" onClick={handleClose} disabled={bulkMutation.isPending}>Abbrechen</Button>
              <Button
                variant="outline"
                onClick={handlePreview}
                disabled={previewMutation.isPending || bulkMutation.isPending || previewCount === 0}
                data-testid="bulk-invite-preview"
              >
                {previewMutation.isPending ? 'Prüfe...' : 'Vorschau'}
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={bulkMutation.isPending || previewCount === 0}
                className="bg-[#6B8E23] hover:bg-[#5a7a1f] text-white"
                data-testid="bulk-invite-submit"
              >
                {bulkMutation.isPending ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Erstelle & sende...</> : `${previewCount} einladen`}
              </Button>
            </div>

            {preview && (
              <div className="rounded-lg bg-[#F9F9F6] border border-[#E2E4E0] p-3 text-xs space-y-1.5" data-testid="bulk-invite-preview-result">
                <div className="flex items-center gap-4">
                  <span className="text-[#6B8E23] font-medium">{preview.will_create} neu</span>
                  {preview.already_existing.length > 0 && <span className="text-[#D4A373]">{preview.already_existing.length} bereits vorhanden</span>}
                  {preview.duplicates.length > 0 && <span className="text-[#9CA3AF]">{preview.duplicates.length} Duplikate</span>}
                  {preview.invalid.length > 0 && <span className="text-[#C87967]">{preview.invalid.length} ungültig</span>}
                </div>
                {preview.already_existing.length > 0 && (
                  <details className="text-[#6B7280]">
                    <summary className="cursor-pointer">{t('showExisting')}</summary>
                    <div className="pl-3 pt-1 font-mono">{preview.already_existing.slice(0, 10).join(', ')}{preview.already_existing.length > 10 ? `... (+${preview.already_existing.length - 10})` : ''}</div>
                  </details>
                )}
                {preview.invalid.length > 0 && (
                  <details className="text-[#6B7280]">
                    <summary className="cursor-pointer">{t('showInvalid')}</summary>
                    <div className="pl-3 pt-1 font-mono">{preview.invalid.slice(0, 10).join(', ')}</div>
                  </details>
                )}
              </div>
            )}
          </div>
        )}

        {result && (
          <div className="space-y-4" data-testid="bulk-invite-result">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
              <StatTile value={result.summary?.created ?? 0} label="Erstellt" color="#6B8E23" />
              <StatTile value={result.summary?.sent ?? 0} label="E-Mails gesendet" color="#4A5D4E" />
              <StatTile value={result.summary?.skipped_existing ?? 0} label={t('alreadyExists')} color="#D4A373" />
              <StatTile value={result.summary?.failed ?? 0 + (result.summary?.invalid ?? 0)} label="Fehlgeschlagen" color="#C87967" />
            </div>
            <div className="max-h-80 overflow-y-auto border border-[#E2E4E0] rounded-lg">
              <table className="w-full text-xs">
                <thead className="bg-[#F3F4F1] sticky top-0">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium text-[#4B5563]">E-Mail</th>
                    <th className="text-left px-3 py-2 font-medium text-[#4B5563]">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(result.results || []).map((r, i) => (
                    <tr key={i} className="border-t border-[#E2E4E0]" data-testid={`bulk-row-${i}`}>
                      <td className="px-3 py-2 font-mono">{r.email}</td>
                      <td className="px-3 py-2 flex items-center gap-1.5">
                        {r.status === 'sent' && <><CheckCircle2 className="w-3.5 h-3.5 text-[#6B8E23]" /> Gesendet</>}
                        {r.status === 'created_no_email' && <><CheckCircle2 className="w-3.5 h-3.5 text-[#6B8E23]" /> Erstellt</>}
                        {r.status === 'skipped_existing' && <><SkipForward className="w-3.5 h-3.5 text-[#D4A373]" /> Bereits vorhanden</>}
                        {r.status === 'failed' && <><XCircle className="w-3.5 h-3.5 text-[#C87967]" /> Fehler{r.error ? `: ${r.error}` : ''}</>}
                        {r.status === 'invalid' && <><XCircle className="w-3.5 h-3.5 text-[#C87967]" /> {t('invalid')}</>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => { setResult(null); setEmailsText(''); }}>{t('inviteMore')}</Button>
              <Button onClick={handleClose} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white" data-testid="bulk-invite-close">Fertig</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function StatTile({ value, label, color }) {
  return (
    <div className="rounded-lg bg-[#F9F9F6] border border-[#E2E4E0] py-3">
      <div className="text-2xl font-medium" style={{ color }}>{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-[#6B7280] mt-0.5">{label}</div>
    </div>
  );
}
