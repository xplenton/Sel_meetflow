import { useEffect, useMemo, useState } from 'react';
import api from '../../lib/api';
import { copyToClipboard } from '../../lib/clipboard';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { CheckCircle, UserPlus, X, ChevronDown, ChevronUp } from 'lucide-react';
import { toast } from 'sonner';
import { useLanguage } from '../../contexts/LanguageContext';

/**
 * InviteUserDialog (iter 374) — gesamte User-Stammdaten in einem Schritt
 * einsetzbar. Pflichtfelder per User-Entscheidung:
 *   E-Mail, Vorname, Nachname, Abteilung, Position, Personalnummer
 * Optional: Anzeigename, Telefon, Standort, Beruf, Org-Einheit, Sprache,
 *           Rolle, Gruppen, Direct-Grants/Denies, must_change_password.
 *
 * Drei Abschnitte mit collapsible Header — Stammdaten zuerst offen,
 * Berechtigungen + Profil-Extras eingeklappt.
 */
const REQUIRED_KEYS = ['email', 'first_name', 'last_name', 'department', 'position', 'personnel_number'];
const REQUIRED_LABELS = {
  email: 'E-Mail',
  first_name: 'Vorname',
  last_name: 'Nachname',
  department: 'Abteilung',
  position: 'Position',
  personnel_number: 'Personalnummer',
  initial_password: 'Initial-Passwort',
};

// Iter 379 — Wenn der User KEINE E-Mail hat (Pflegekraft etc.), wird Email
// optional und Initial-Passwort + Personalnummer werden Pflicht.
const REQUIRED_KEYS_NO_EMAIL = ['first_name', 'last_name', 'department', 'position', 'personnel_number', 'initial_password'];

// Inline-Policy-Check (gleich wie /backend/services/password_policy.py)
const SPECIAL = /[!@#$%^&*()_+\-=[\]{};:'",.<>/?\\|`~]/;
function pwOk(pw) {
  return (pw || '').length >= 8 &&
    /[A-Z]/.test(pw || '') &&
    /[a-z]/.test(pw || '') &&
    /\d/.test(pw || '') &&
    SPECIAL.test(pw || '');
}

function Section({ title, defaultOpen = false, children, testId }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-[#E2E4E0] rounded-xl overflow-hidden" data-testid={testId}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full px-3 py-2 bg-[#FAFAF9] flex items-center justify-between text-xs font-semibold text-[#1A1D1B] hover:bg-[#F5F4F0]"
      >
        <span>{title}</span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && <div className="p-3 space-y-3">{children}</div>}
    </div>
  );
}

export default function InviteUserDialog({
  open, onOpenChange,
  form, onFormChange,
  result, onInvite,
}) {
  const { t } = useLanguage();
  const [groups, setGroups] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [capabilities, setCapabilities] = useState([]);

  useEffect(() => {
    if (!open) return;
    api.get('/admin/groups').then(r => setGroups(Array.isArray(r.data) ? r.data : (r.data?.groups || []))).catch(() => setGroups([]));
    api.get('/admin/users/filters').then(r => setDepartments(r.data?.departments || [])).catch(() => setDepartments([]));
    api.get('/admin/capabilities').then(r => setCapabilities(r.data?.capabilities || [])).catch(() => setCapabilities([]));
  }, [open]);

  const selectedGroupIds = Array.isArray(form.group_ids) ? form.group_ids : [];
  const selectedGrants = Array.isArray(form.cap_grants) ? form.cap_grants : [];
  const selectedDenies = Array.isArray(form.cap_denies) ? form.cap_denies : [];

  const addGroup = (gid) => {
    if (!gid || selectedGroupIds.includes(gid)) return;
    onFormChange({ ...form, group_ids: [...selectedGroupIds, gid] });
  };
  const removeGroup = (gid) =>
    onFormChange({ ...form, group_ids: selectedGroupIds.filter(g => g !== gid) });
  const remainingGroups = groups.filter(g => !selectedGroupIds.includes(g.group_id));

  const addGrant = (cap) => {
    if (!cap || selectedGrants.includes(cap)) return;
    onFormChange({ ...form, cap_grants: [...selectedGrants, cap], cap_denies: selectedDenies.filter(c => c !== cap) });
  };
  const removeGrant = (cap) => onFormChange({ ...form, cap_grants: selectedGrants.filter(c => c !== cap) });
  const addDeny = (cap) => {
    if (!cap || selectedDenies.includes(cap)) return;
    onFormChange({ ...form, cap_denies: [...selectedDenies, cap], cap_grants: selectedGrants.filter(c => c !== cap) });
  };
  const removeDeny = (cap) => onFormChange({ ...form, cap_denies: selectedDenies.filter(c => c !== cap) });

  const capsByKey = useMemo(() => Object.fromEntries(capabilities.map(c => [c.key, c])), [capabilities]);

  // Pflichtfeld-Status für UI-Hinweis und Button-Disable.
  // Iter 379 — Wenn `no_email` an ist, ist E-Mail OPTIONAL und Initial-PW Pflicht.
  const isNoEmail = !!form.no_email;
  const requiredKeys = isNoEmail ? REQUIRED_KEYS_NO_EMAIL : REQUIRED_KEYS;
  const missingFields = requiredKeys.filter(k => !(form[k] || '').toString().trim());
  // Zusaetzlich Initial-PW gegen Policy prüfen, wenn gesetzt.
  const pwSet = !!(form.initial_password || '').trim();
  const pwInvalid = pwSet && !pwOk(form.initial_password);
  const missingLabels = missingFields.map(k => REQUIRED_LABELS[k] || k);
  if (pwInvalid) missingLabels.push('gültiges Initial-Passwort (Policy)');
  const canSubmit = missingFields.length === 0 && !pwInvalid;

  const handleSubmit = () => {
    if (!canSubmit) {
      toast.error(`Pflichtfelder ausfüllen: ${missingLabels.join(', ')}`);
      return;
    }
    onInvite();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px] max-h-[92vh] overflow-y-auto">
        <DialogHeader><DialogTitle>{t('inviteUser')}</DialogTitle></DialogHeader>
        {result ? (
          <div className="space-y-4 pt-2">
            <div className="text-center">
              <div className="w-12 h-12 rounded-full bg-[#6B8E23]/10 flex items-center justify-center mx-auto mb-3">
                <CheckCircle className="w-6 h-6 text-[#6B8E23]" />
              </div>
              <p className="text-sm font-medium text-[#1C1F1D] mb-1">{t('inviteUserSuccess')}</p>
              {result.email_sent ? (
                <p className="text-xs text-[#6B8E23]">{t('inviteUserEmailSent')}</p>
              ) : result.email_simulated ? (
                <div className="mt-2 p-2.5 bg-[#D4A373]/10 border border-[#D4A373]/30 rounded-lg text-left">
                  <p className="text-[11px] font-semibold text-[#1C1F1D] mb-0.5">E-Mail nur simuliert (kein Provider aktiv)</p>
                  <p className="text-[10px] text-[#6B7280] leading-relaxed">
                    Kein Resend/SendGrid/SMTP-Provider konfiguriert. Bitte in{' '}
                    <strong>Verwaltung → Integrationen → E-Mail</strong> einen Provider hinterlegen und <u>speichern</u>.
                    Die Zugangsdaten findest du unten — kopiere sie oder gib sie dem Nutzer manuell.
                  </p>
                </div>
              ) : (
                <div className="mt-2 p-2.5 bg-[#C87967]/10 border border-[#C87967]/30 rounded-lg text-left">
                  <p className="text-[11px] font-semibold text-[#1C1F1D] mb-0.5">{t('inviteUserEmailFailed')}</p>
                  {result.email_error && (
                    <p className="text-[10px] text-[#C87967] leading-relaxed font-mono break-all">{result.email_error}</p>
                  )}
                </div>
              )}
            </div>
            <div className="bg-[#F3F4F1] rounded-xl p-4 space-y-2">
              <div className="flex justify-between text-sm"><span className="text-[#6B7280]">E-Mail</span><span className="font-medium text-[#1C1F1D]">{result.email}</span></div>
              <div className="flex justify-between text-sm"><span className="text-[#6B7280]">Passwort</span><span className="font-mono font-medium text-[#4A5D4E]">{result.temp_password}</span></div>
              {result.user_id && (
                <div className="flex justify-between text-sm"><span className="text-[#6B7280]">BenutzerID</span><span className="font-mono text-[11px] text-[#4A5D4E]">{result.user_id}</span></div>
              )}
            </div>
            <Button
              onClick={() => { copyToClipboard(`E-Mail: ${result.email}\nPasswort: ${result.temp_password}`); toast.success('Zugangsdaten kopiert'); }}
              variant="outline" className="w-full rounded-lg border-[#E2E4E0] text-xs" data-testid="copy-credentials-btn">
              Zugangsdaten kopieren
            </Button>
            <Button onClick={() => onOpenChange(false)}
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg">
              Fertig
            </Button>
          </div>
        ) : (
          <div className="space-y-3 pt-2">
            {/* === STAMMDATEN (Pflicht) === */}
            <Section title="Stammdaten (Pflichtfelder mit *)" defaultOpen testId="invite-section-master">
              {/* Iter 379 — Toggle „Kein E-Mail-Konto". Wird verwendet für
                  Mitarbeitende ohne dienstliche E-Mail (Pflege, Reinigung etc.).
                  In dem Fall melden sie sich mit Personalnummer + Passwort an. */}
              <label className="flex items-center gap-2 p-2 bg-[#FAFAF9] border border-[#E2E4E0] rounded-lg cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!form.no_email}
                  onChange={e => onFormChange({ ...form, no_email: e.target.checked, email: e.target.checked ? '' : (form.email || '') })}
                  className="rounded border-[#E2E4E0]"
                  data-testid="invite-no-email-checkbox"
                />
                <span className="text-[11px] text-[#1A1D1B]">Kein E-Mail-Konto (Login dann mit Personalnummer + Initialpasswort)</span>
              </label>
              <div className={isNoEmail ? 'opacity-50 pointer-events-none' : ''}>
                <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
                  E-Mail {isNoEmail ? '(deaktiviert)' : '*'}
                </Label>
                <Input value={form.email || ''} onChange={e => onFormChange({ ...form, email: e.target.value })}
                  placeholder={isNoEmail ? 'wird automatisch erzeugt' : 'name@firma.de'}
                  disabled={isNoEmail}
                  className="border-[#E2E4E0] rounded-xl" data-testid="invite-email-input" />
              </div>
              {isNoEmail && (
                <div>
                  <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
                    Initial-Passwort *
                  </Label>
                  <Input
                    type="text"
                    value={form.initial_password || ''}
                    onChange={e => onFormChange({ ...form, initial_password: e.target.value })}
                    placeholder="z.B. StartPw1!"
                    className={`border-[#E2E4E0] rounded-xl font-mono ${pwInvalid ? 'border-rose-500' : ''}`}
                    data-testid="invite-initial-password-input"
                  />
                  <p className="text-[10px] text-[#9CA3AF] mt-1">
                    Mindestens 8 Zeichen, je 1 Gross-/Kleinbuchstabe, Ziffer und Sonderzeichen.
                    User muss das Passwort beim ersten Login ändern.
                  </p>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Vorname *</Label>
                  <Input value={form.first_name || ''} onChange={e => onFormChange({ ...form, first_name: e.target.value })}
                    placeholder="Max" className="border-[#E2E4E0] rounded-xl" data-testid="invite-first-name-input" />
                </div>
                <div>
                  <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Nachname *</Label>
                  <Input value={form.last_name || ''} onChange={e => onFormChange({ ...form, last_name: e.target.value })}
                    placeholder="Mustermann" className="border-[#E2E4E0] rounded-xl" data-testid="invite-last-name-input" />
                </div>
              </div>
              <div>
                <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Anzeigename</Label>
                <Input value={form.display_name || ''} onChange={e => onFormChange({ ...form, display_name: e.target.value })}
                  placeholder="optional — Standard: Vorname Nachname" className="border-[#E2E4E0] rounded-xl" data-testid="invite-display-name-input" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Abteilung *</Label>
                  <Input
                    value={form.department || ''}
                    onChange={e => onFormChange({ ...form, department: e.target.value })}
                    list="invite-department-list"
                    placeholder="z.B. Marketing"
                    className="border-[#E2E4E0] rounded-xl"
                    data-testid="invite-department-input"
                  />
                  {departments.length > 0 && (
                    <datalist id="invite-department-list">
                      {departments.map(d => <option key={d} value={d} />)}
                    </datalist>
                  )}
                </div>
                <div>
                  <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Position *</Label>
                  <Input value={form.position || ''} onChange={e => onFormChange({ ...form, position: e.target.value })}
                    placeholder="z.B. Teamleitung" className="border-[#E2E4E0] rounded-xl" data-testid="invite-position-input" />
                </div>
              </div>
              <div>
                <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Personalnummer *</Label>
                <Input value={form.personnel_number || ''} onChange={e => onFormChange({ ...form, personnel_number: e.target.value })}
                  placeholder="z.B. P-12345" className="border-[#E2E4E0] rounded-xl" data-testid="invite-personnel-number-input" />
              </div>
            </Section>

            {/* === BERECHTIGUNGEN === */}
            <Section title="Berechtigungen" testId="invite-section-perms">
              <div>
                <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Rolle</Label>
                <Select value={form.role || 'member'} onValueChange={v => onFormChange({ ...form, role: v })}>
                  <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="invite-role-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Administrator</SelectItem>
                    <SelectItem value="moderator">Moderator</SelectItem>
                    <SelectItem value="member">Mitarbeiter</SelectItem>
                    <SelectItem value="guest">Gast</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Gruppen</Label>
                {selectedGroupIds.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-2" data-testid="invite-selected-groups">
                    {selectedGroupIds.map(gid => {
                      const g = groups.find(x => x.group_id === gid);
                      return (
                        <Badge key={gid} variant="outline" className="gap-1 bg-[#4A5D4E]/5 border-[#4A5D4E]/30" data-testid={`invite-group-chip-${gid}`}>
                          {g?.name || gid}
                          <button type="button" onClick={() => removeGroup(gid)} className="ml-1 text-[#6B7280] hover:text-rose-600">
                            <X className="w-3 h-3" />
                          </button>
                        </Badge>
                      );
                    })}
                  </div>
                )}
                {remainingGroups.length > 0 ? (
                  <Select value="" onValueChange={addGroup}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="invite-group-add-select">
                      <SelectValue placeholder="Gruppe hinzufügen…" />
                    </SelectTrigger>
                    <SelectContent>
                      {remainingGroups.map(g => (
                        <SelectItem key={g.group_id} value={g.group_id} data-testid={`invite-group-option-${g.group_id}`}>
                          {g.name}{g.description ? ` — ${g.description}` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : selectedGroupIds.length === 0 ? (
                  <p className="text-[11px] text-[#9CA3AF]">Keine Gruppen vorhanden — unter Verwaltung → Gruppen anlegen.</p>
                ) : (
                  <p className="text-[11px] text-[#9CA3AF]">Alle Gruppen ausgewählt.</p>
                )}
              </div>
              <div>
                <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Direkte Rechte (Grants)</Label>
                {selectedGrants.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-2" data-testid="invite-grants-chips">
                    {selectedGrants.map(c => (
                      <Badge key={c} variant="outline" className="gap-1 bg-[#4A5D4E]/5 border-[#4A5D4E]/40 text-[#4A5D4E]">
                        {capsByKey[c]?.label || c}
                        <button type="button" onClick={() => removeGrant(c)} className="ml-1 hover:text-rose-600">
                          <X className="w-3 h-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
                <Select value="" onValueChange={addGrant}>
                  <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="invite-grant-add">
                    <SelectValue placeholder="Recht zusätzlich gewähren…" />
                  </SelectTrigger>
                  <SelectContent className="max-h-60 overflow-y-auto">
                    {capabilities
                      .filter(c => !selectedGrants.includes(c.key) && !selectedDenies.includes(c.key))
                      .map(c => (
                        <SelectItem key={c.key} value={c.key}>
                          {c.label} <span className="text-[10px] text-[#9CA3AF]">{c.key}</span>
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Rechte explizit entziehen (Denies)</Label>
                {selectedDenies.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-2" data-testid="invite-denies-chips">
                    {selectedDenies.map(c => (
                      <Badge key={c} variant="outline" className="gap-1 bg-[#C87967]/5 border-[#C87967]/40 text-[#C87967]">
                        {capsByKey[c]?.label || c}
                        <button type="button" onClick={() => removeDeny(c)} className="ml-1 hover:text-rose-600">
                          <X className="w-3 h-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
                <Select value="" onValueChange={addDeny}>
                  <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="invite-deny-add">
                    <SelectValue placeholder="Recht entziehen…" />
                  </SelectTrigger>
                  <SelectContent className="max-h-60 overflow-y-auto">
                    {capabilities
                      .filter(c => !selectedDenies.includes(c.key) && !selectedGrants.includes(c.key))
                      .map(c => (
                        <SelectItem key={c.key} value={c.key}>
                          {c.label} <span className="text-[10px] text-[#9CA3AF]">{c.key}</span>
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
            </Section>

            {/* === PROFIL-EXTRAS === */}
            <Section title="Profil-Extras (optional)" testId="invite-section-extras">
              <div>
                <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Telefonnummer</Label>
                <Input value={form.phone || ''} onChange={e => onFormChange({ ...form, phone: e.target.value })}
                  placeholder="+49 …" className="border-[#E2E4E0] rounded-xl" data-testid="invite-phone-input" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Standort</Label>
                  <Input value={form.location || ''} onChange={e => onFormChange({ ...form, location: e.target.value })}
                    placeholder="z.B. Berlin" className="border-[#E2E4E0] rounded-xl" data-testid="invite-location-input" />
                </div>
                <div>
                  <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Beruf</Label>
                  <Input value={form.profession || ''} onChange={e => onFormChange({ ...form, profession: e.target.value })}
                    placeholder="z.B. Arzt" className="border-[#E2E4E0] rounded-xl" data-testid="invite-profession-input" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Org-Einheit</Label>
                  <Input value={form.org_unit || ''} onChange={e => onFormChange({ ...form, org_unit: e.target.value })}
                    placeholder="z.B. Klinik Nord" className="border-[#E2E4E0] rounded-xl" data-testid="invite-org-unit-input" />
                </div>
                <div>
                  <Label className="text-[11px] uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Sprache</Label>
                  <Select value={form.language || 'de'} onValueChange={v => onFormChange({ ...form, language: v })}>
                    <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="invite-language-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="de">Deutsch</SelectItem>
                      <SelectItem value="en">English</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </Section>

            {/* Pflichtfeld-Hinweis */}
            {!canSubmit && (
              <div className="text-[11px] text-[#C87967] bg-[#C87967]/5 border border-[#C87967]/30 rounded-lg px-3 py-2" data-testid="invite-missing-hint">
                Pflichtfelder fehlen: <strong>{missingLabels.join(', ')}</strong>
              </div>
            )}

            <div className="flex gap-2 justify-end pt-1">
              <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-lg">{t('cancel')}</Button>
              <Button onClick={handleSubmit} disabled={!canSubmit}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg disabled:opacity-50"
                data-testid="confirm-invite-btn">
                <UserPlus className="w-3.5 h-3.5 mr-1" /> {t('invite')}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
