import { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Switch } from '../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Trash2, ShieldCheck, UserPlus2 } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

import { useLanguage } from '../../contexts/LanguageContext';
export default function PoliciesPanel() {
  const { t } = useLanguage();
  const [policies, setPolicies] = useState([]);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', max_duration: 120, max_participants: 100, allow_recording: true, allow_guest: true, require_lobby: false, default_meeting_mode: 'standard', auto_transcribe: false });
  const qc = useQueryClient();

  // Iter 119: organisation-wide onboarding settings (email verification,
  // auto-promote). Live-updated via React Query; the mutation invalidates
  // the query key so the toggle reflects the server truth instantly.
  const orgQ = useQuery({
    queryKey: ['admin', 'org-settings'],
    queryFn: async () => (await api.get('/admin/org-settings')).data,
  });
  const groupsQ = useQuery({
    queryKey: ['admin', 'groups'],
    queryFn: async () => (await api.get('/admin/groups')).data,
  });
  const orgMutation = useMutation({
    mutationFn: (patch) => api.put('/admin/org-settings', patch),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin', 'org-settings'] }); toast.success('Einstellung gespeichert'); },
    onError: () => toast.error('Fehler beim Speichern'),
  });
  const orgSettings = orgQ.data || {};
  const groups = groupsQ.data || [];
  const updateOrg = (patch) => orgMutation.mutate(patch);

  const fetchPolicies = useCallback(async () => {
    try { const { data } = await api.get('/admin/policies'); setPolicies(data); } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchPolicies(); }, [fetchPolicies]);

  const handleCreate = async () => {
    try { await api.post('/admin/policies', form); setCreating(false); fetchPolicies(); toast.success('Richtlinie erstellt'); } catch { /* ignore */ }
  };

  const handleDelete = async (id) => {
    try { await api.delete(`/admin/policies/${id}`); fetchPolicies(); toast.success('Richtlinie gelöscht'); } catch { /* ignore */ }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="onboarding-policies">
        <h3 className="text-sm font-medium text-[#1C1F1D] flex items-center gap-2 mb-4">
          <ShieldCheck className="w-4 h-4 text-[#4A5D4E]" /> Onboarding & Zugang
        </h3>
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <Label className="text-sm text-[#1C1F1D]">{t('emailVerificationRequired')}</Label>
              <p className="text-xs text-[#6B7280] mt-0.5">Neue Nutzer erhalten einen Bestätigungs-Link per E-Mail. Ohne Bestätigung wird ein Hinweis-Banner angezeigt (Login bleibt möglich).</p>
            </div>
            <Switch
              checked={!!orgSettings.email_verification_required}
              onCheckedChange={(v) => updateOrg({ email_verification_required: v })}
              data-testid="toggle-email-verification"
            />
          </div>
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <Label className="text-sm text-[#1C1F1D]">{t('autoPromoteOnVerify')}</Label>
              <p className="text-xs text-[#6B7280] mt-0.5">Nach erfolgreicher E-Mail-Bestätigung wird der Nutzer von "Gast" in "Mitglied" verschoben.</p>
            </div>
            <Switch
              checked={!!orgSettings.auto_promote_on_verify}
              onCheckedChange={(v) => updateOrg({ auto_promote_on_verify: v })}
              data-testid="toggle-auto-promote"
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-[#E2E4E0]">
            <div>
              <Label className="text-xs text-[#6B7280] flex items-center gap-1.5">
                <UserPlus2 className="w-3 h-3" /> Default-Gruppe für neue Nutzer
              </Label>
              <Select
                value={orgSettings.default_guest_group || ''}
                onValueChange={(v) => updateOrg({ default_guest_group: v })}
              >
                <SelectTrigger className="mt-1.5 h-9 text-xs" data-testid="default-guest-group"><SelectValue placeholder="Keine" /></SelectTrigger>
                <SelectContent>
                  {groups.map(g => <SelectItem key={g.group_id} value={g.group_id}>{g.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-[#6B7280] flex items-center gap-1.5">
                <UserPlus2 className="w-3 h-3" /> Gruppe nach Verifizierung
              </Label>
              <Select
                value={orgSettings.default_member_group || ''}
                onValueChange={(v) => updateOrg({ default_member_group: v })}
              >
                <SelectTrigger className="mt-1.5 h-9 text-xs" data-testid="default-member-group"><SelectValue placeholder="Keine" /></SelectTrigger>
                <SelectContent>
                  {groups.map(g => <SelectItem key={g.group_id} value={g.group_id}>{g.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Iter 290 — Selbst-Registrierung-Regeln */}
          <div className="pt-2 border-t border-[#E2E4E0] space-y-3">
            <div>
              <Label className="text-sm text-[#1C1F1D]">Selbst-Registrierung: erlaubte Domains</Label>
              <p className="text-xs text-[#6B7280] mt-0.5">
                Komma-getrennte Liste (z.B. <code className="bg-[#F3F4F1] px-1 rounded">firma.de, beispiel.com</code>).
                Leer = jede Domain erlaubt. Bei gesetzter Liste wird Selbst-Registrierung nur für E-Mails mit passender Domain akzeptiert.
                SSO und vom Admin angelegte Nutzer sind nicht betroffen.
              </p>
              <Input
                value={(orgSettings.allowed_signup_domains || []).join(', ')}
                onChange={(e) => {
                  const list = e.target.value.split(',').map(d => d.trim().toLowerCase().replace(/^@/, '')).filter(Boolean);
                  updateOrg({ allowed_signup_domains: list });
                }}
                placeholder="firma.de, partner.de"
                className="mt-1.5 h-9 text-sm"
                data-testid="allowed-signup-domains-input"
              />
              {(orgSettings.allowed_signup_domains || []).length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {orgSettings.allowed_signup_domains.map(d => (
                    <span key={d} className="text-[10px] bg-emerald-50 text-emerald-800 border border-emerald-300 rounded px-1.5 py-0.5">
                      @{d}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div>
              <Label className="text-sm text-[#1C1F1D]">Auto-Sperre unverifizierter Konten (Stunden)</Label>
              <p className="text-xs text-[#6B7280] mt-0.5">
                Selbst-registrierte Nutzer, deren E-Mail nicht innerhalb dieser Zeitspanne bestätigt wurde, werden automatisch gesperrt
                (Login blockiert). 0 = deaktiviert. Standard: 24 Stunden.
              </p>
              <Input
                type="number"
                min="0"
                max="168"
                value={orgSettings.auto_lock_unverified_hours ?? 24}
                onChange={(e) => updateOrg({ auto_lock_unverified_hours: Math.max(0, Math.min(168, Number(e.target.value) || 0)) })}
                className="mt-1.5 h-9 text-sm w-32"
                data-testid="auto-lock-unverified-hours-input"
              />
            </div>
            {/* Iter 379 — Passwort-Rotation in Monaten */}
            <div className="pt-3 border-t border-[#E2E4E0]">
              <Label className="text-sm text-[#1C1F1D] flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-[#4A5D4E]" /> Passwort-Rotation (Monate)
              </Label>
              <p className="text-xs text-[#6B7280] mt-0.5">
                Wie oft Mitarbeiter ihr Passwort erneuern müssen. Beim Login wird ein Hinweis-Banner eingeblendet
                wenn das aktuelle Passwort aelter ist. 0 = deaktiviert. Empfohlen: 6 Monate.
                Wiederverwendung der letzten 3 Passwoerter wird automatisch verhindert.
              </p>
              <Input
                type="number"
                min="0"
                max="36"
                value={orgSettings.password_rotation_months ?? 6}
                onChange={(e) => updateOrg({ password_rotation_months: Math.max(0, Math.min(36, Number(e.target.value) || 0)) })}
                className="mt-1.5 h-9 text-sm w-32"
                data-testid="password-rotation-months-input"
              />
              <p className="text-[10px] text-[#9CA3AF] mt-1">
                Policy: min. 8 Zeichen, je mind. 1 Gross-/Kleinbuchstabe, Ziffer und Sonderzeichen (4-aus-4).
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white border border-[#E2E4E0] rounded-xl p-6" data-testid="policies-panel">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-sm font-medium text-[#1C1F1D]">Meeting-Richtlinien</h3>
        <Button onClick={() => setCreating(!creating)} size="sm" className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs" data-testid="create-policy-button">
          {creating ? 'Abbrechen' : '+ Neue Richtlinie'}
        </Button>
      </div>
      {creating && (
        <div className="bg-[#F3F4F1] rounded-xl p-4 mb-4 space-y-3">
          <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Name der Richtlinie" className="border-[#E2E4E0] rounded-xl" data-testid="policy-name-input" />
          <div className="grid grid-cols-2 gap-3">
            <div><Label className="text-[10px] text-[#6B7280]">Max. Dauer (Min.)</Label>
              <Input type="number" value={form.max_duration} onChange={e => setForm({ ...form, max_duration: +e.target.value })} className="border-[#E2E4E0] rounded-lg h-8 text-xs" /></div>
            <div><Label className="text-[10px] text-[#6B7280]">{t('maxParticipants')}</Label>
              <Input type="number" value={form.max_participants} onChange={e => setForm({ ...form, max_participants: +e.target.value })} className="border-[#E2E4E0] rounded-lg h-8 text-xs" /></div>
          </div>
          {[['allow_recording', 'Aufnahme erlauben'], ['allow_guest', 'Gastzugang erlauben'], ['require_lobby', 'Warteraum erforderlich'], ['auto_transcribe', 'Auto-Transkript']].map(([k, l]) => (
            <div key={k} className="flex justify-between items-center"><span className="text-xs text-[#4B5563]">{l}</span>
              <Switch checked={form[k]} onCheckedChange={v => setForm({ ...form, [k]: v })} /></div>
          ))}
          <Button onClick={handleCreate} size="sm" className="bg-[#4A5D4E] text-white rounded-full w-full" data-testid="save-policy-button">{t('savePolicy')}</Button>
        </div>
      )}
      <div className="space-y-3">
        {policies.map(p => (
          <div key={p.policy_id} className="border border-[#E2E4E0] rounded-xl p-4" data-testid={`policy-${p.policy_id}`}>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium text-[#1C1F1D]">{p.name}</span>
              <div className="flex gap-1">
                <Badge className={p.is_active ? 'bg-[#6B8E23]/10 text-[#6B8E23] text-[9px]' : 'bg-[#9CA3AF]/10 text-[#9CA3AF] text-[9px]'}>{p.is_active ? 'Aktiv' : 'Inaktiv'}</Badge>
                <button onClick={() => handleDelete(p.policy_id)} className="p-1 text-[#C87967] hover:bg-[#C87967]/10 rounded" data-testid={`delete-policy-${p.policy_id}`}><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[10px] text-[#6B7280]">
              <span>Max. Dauer: {p.max_duration} Min.</span><span>Max. Teilnehmer: {p.max_participants}</span>
              <span>Aufnahme: {p.allow_recording ? 'Ja' : 'Nein'}</span><span>Gast: {p.allow_guest ? 'Ja' : 'Nein'}</span>
              <span>Warteraum: {p.require_lobby ? 'Erforderlich' : 'Optional'}</span><span>Modus: {p.default_meeting_mode}</span>
            </div>
          </div>
        ))}
        {policies.length === 0 && !creating && <p className="text-xs text-[#9CA3AF] text-center py-6">{t('noPoliciesConfigured')}</p>}
      </div>
      </div>
    </div>
  );
}
