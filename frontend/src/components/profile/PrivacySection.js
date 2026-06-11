import { useState, useEffect } from 'react';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Shield, MessageSquare } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';

/**
 * PrivacySection — Profil-Privatsphäre-Block.
 *  - "Heute im Büro"-Widget Opt-Out (iter 247)
 *  - Iter 323: DM-Policy (wer darf mich anschreiben)
 *
 * Backend: GET/PUT /api/users/me/privacy
 */
const DM_POLICY_OPTIONS = [
  { value: 'everyone',        de: 'Alle Kolleg:innen',
    desc_de: 'Standard — jede:r mit Chat-Zugriff darf mich direkt anschreiben.' },
  { value: 'same_department', de: 'Nur meine Abteilung',
    desc_de: 'Nur Kolleg:innen aus derselben Abteilung dürfen neue DMs starten.' },
  { value: 'managers_plus',   de: 'Nur Moderatoren & Admins',
    desc_de: 'Nur Vorgesetzte mit Moderator- oder Admin-Rolle dürfen mich anschreiben.' },
  { value: 'nobody',          de: 'Niemand',
    desc_de: 'Keine neuen DMs — bestehende Gespräche laufen weiter. Admins können trotzdem schreiben.' },
];

export default function PrivacySection({ language }) {
  const [hide, setHide] = useState(false);
  const [dmPolicy, setDmPolicy] = useState('everyone');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/users/me/privacy')
      .then(({ data }) => {
        setHide(!!data.hide_from_office_widget);
        setDmPolicy(data.dm_policy || 'everyone');
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const onToggle = async (next) => {
    setSaving(true);
    setHide(next);
    try {
      await api.put('/users/me/privacy', { hide_from_office_widget: next });
      toast.success(language === 'de'
        ? (next ? 'Du wirst im "Heute im Büro"-Widget ausgeblendet' : 'Du erscheinst wieder im "Heute im Büro"-Widget')
        : (next ? 'Hidden from office widget' : 'Visible in office widget again'));
    } catch (e) {
      setHide(!next);
      toast.error(e.response?.data?.detail || 'Fehler');
    } finally {
      setSaving(false);
    }
  };

  const onDmPolicyChange = async (next) => {
    const prev = dmPolicy;
    setSaving(true);
    setDmPolicy(next);
    try {
      await api.put('/users/me/privacy', { dm_policy: next });
      toast.success('Chat-Einstellung gespeichert');
    } catch (e) {
      setDmPolicy(prev);
      toast.error(e.response?.data?.detail || 'Fehler beim Speichern');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return null;

  const dmCurrent = DM_POLICY_OPTIONS.find(o => o.value === dmPolicy) || DM_POLICY_OPTIONS[0];

  return (
    <div className="border border-[#E2E4E0] rounded-xl p-4 space-y-4" data-testid="privacy-block">
      <div className="flex items-center gap-2">
        <Shield className="w-4 h-4 text-[#4A5D4E]" />
        <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">
          {language === 'de' ? 'Privatsphäre' : 'Privacy'}
        </Label>
      </div>

      {/* Office-widget toggle */}
      <div className="flex items-center justify-between py-1">
        <div className="flex-1 pr-3">
          <p className="text-sm font-medium text-[#1C1F1D]">
            {language === 'de' ? 'Im "Heute im Büro"-Widget verbergen' : 'Hide from "In office today" widget'}
          </p>
          <p className="text-xs text-[#9CA3AF] mt-0.5">
            {language === 'de'
              ? 'Deine Desk-Buchungen werden Kolleg/innen im Dashboard nicht angezeigt.'
              : 'Your desk bookings will not be shown to colleagues on the dashboard.'}
          </p>
        </div>
        <Switch
          checked={hide}
          onCheckedChange={onToggle}
          disabled={saving}
          data-testid="hide-from-office-widget-toggle"
        />
      </div>

      {/* Iter 323 — DM Opt-In */}
      <div className="pt-3 border-t border-[#E2E4E0] space-y-2">
        <div className="flex items-start gap-2">
          <MessageSquare className="w-4 h-4 text-[#4A5D4E] mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[#1C1F1D]">
              Wer darf mich im Chat anschreiben?
            </p>
            <p className="text-xs text-[#9CA3AF] mt-0.5">
              Gilt nur für <strong>neue Direkt-Nachrichten</strong>. Bestehende Chats und
              Gruppen-Nachrichten sind nicht betroffen. Admins können dich immer erreichen.
            </p>
          </div>
        </div>
        <Select value={dmPolicy} onValueChange={onDmPolicyChange} disabled={saving}>
          <SelectTrigger className="w-full border-[#E2E4E0]" data-testid="dm-policy-select">
            <SelectValue placeholder="Bitte wählen" />
          </SelectTrigger>
          <SelectContent>
            {DM_POLICY_OPTIONS.map(o => (
              <SelectItem key={o.value} value={o.value} data-testid={`dm-policy-${o.value}`}>
                {o.de}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-[11px] text-[#6B7280] italic px-1" data-testid="dm-policy-desc">
          {dmCurrent.desc_de}
        </p>
      </div>
    </div>
  );
}
