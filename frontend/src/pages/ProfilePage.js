import { useState, useRef, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useLanguage } from '../contexts/LanguageContext';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import { UserCircle, Mail, Globe, Save, Camera, Loader2, BellOff, MailOpen, Shield, ChevronDown, Calendar, AlertCircle, CheckCircle2, RefreshCw, Download, Trash2, Stethoscope, MessageSquare, ShieldOff } from 'lucide-react';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '../components/ui/alert-dialog';
import api from '../lib/api';
import { toast } from 'sonner';
import { getPushSubscriptionStatus, subscribeToPush, ensureServerHasPushSubscription, isPushSupported } from '../lib/push';
import NotificationPrefsSection from '../components/NotificationPrefsSection';
import DelegatesSection from '../components/DelegatesSection';
import TwoFactorSection from '../components/TwoFactorSection';
import DriverLicenseSection from '../components/DriverLicenseSection';
import PrivacySection from '../components/profile/PrivacySection';
import OfficeDaysSection from '../components/profile/OfficeDaysSection';
import useProfileForm from '../hooks/useProfileForm';

const CATEGORY_LABELS = {
  module: 'Modul-Zugriff',
  news: 'News & Mitteilungen',
  meetings: 'Meetings',
  chat: 'Chat',
  documents: 'Dokumente & Whiteboard',
  scheduling: 'Terminfindung',
  surveys: 'Umfragen & Feedback',
  admin: 'Administration',
  global: 'Allgemein',
};

export default function ProfilePage() {
  const { user, setUser, logout } = useAuth();
  const { t, language, setLanguage } = useLanguage();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const icalFeedInputRef = useRef(null);  // Iter 277 — fallback selection target for clipboard helper

  // Iter 274 — "Logout everywhere" state
  const [loggingOutAll, setLoggingOutAll] = useState(false);

  const handleLogoutEverywhere = async () => {
    setLoggingOutAll(true);
    // Iter 276 — suppress SessionExpiryBanner during intentional logout
    window.__mf_logging_out = true;
    try {
      await api.post('/auth/logout-everywhere');
      toast.success('Alle Sitzungen wurden beendet');
      await logout();
      navigate('/login', { replace: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Fehler beim Abmelden');
    } finally {
      setLoggingOutAll(false);
      setTimeout(() => { window.__mf_logging_out = false; }, 1500);
    }
  };

  // iter 219 — All form state + side-effects bundled in a single hook.
  // See `/app/frontend/src/hooks/useProfileForm.js` for the full surface.
  const f = useProfileForm({ user, setUser, language, setLanguage });
  const {
    name, setName, lang, setLang, saving, uploading,
    autoReplyEnabled, setAutoReplyEnabled, autoReplyMessage, setAutoReplyMessage,
    newsletterEnabled, setNewsletterEnabled,
    meetingInvitesEnabled, setMeetingInvitesEnabled,
    digestFrequency, setDigestFrequency, savingPrefs,
    permInfo, permsOpen, setPermsOpen,
    caldav, setCaldav, caldavPw, setCaldavPw, savingCaldav, syncingCaldav,
    icalFeed, rotatingIcal,
    exporting, deleting, deleteConfirmText, setDeleteConfirmText,
    pushStatus, setPushStatus, repairing, setRepairing,
    myFeedback, myFeedbackOpen, setMyFeedbackOpen,
    handleSave, handleSavePrefs, handleAvatarUpload: doUpload,
    handleDataExport, handleAccountDelete,
    saveCaldav, syncCaldavNow, regenerateIcalFeed,
  } = f;

  const handleAvatarUpload = (e) => doUpload(e.target.files?.[0]);

  const avatarSrc = user?.avatar
    ? (() => {
        // Iter 275 — cache-bust by appending an updated_at marker so the
        // browser does not show the old image after a successful re-upload.
        const base = user.avatar.startsWith('/api/')
          ? `${process.env.REACT_APP_BACKEND_URL}${user.avatar}`
          : user.avatar;
        const sep = base.includes('?') ? '&' : '?';
        return `${base}${sep}v=${user.avatar_updated_at || user.avatar_storage_path || ''}`;
      })()
    : '';

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="profile-page">
        <div className="max-w-lg mx-auto">
          <h1 className="text-2xl font-medium tracking-tight mb-6" style={{ fontFamily: 'Manrope' }}>{t('editProfile')}</h1>

          <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 space-y-6">
            {/* Avatar Upload */}
            <div className="flex items-center gap-5">
              <div className="relative group">
                <div className="w-20 h-20 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center overflow-hidden flex-shrink-0 ring-2 ring-[#E2E4E0] ring-offset-2">
                  {avatarSrc ? (
                    <img src={avatarSrc} alt="" className="w-20 h-20 rounded-full object-cover" data-testid="avatar-image" />
                  ) : (
                    <UserCircle className="w-10 h-10 text-[#4A5D4E]" />
                  )}
                </div>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  data-testid="avatar-upload-button"
                  className="absolute inset-0 rounded-full bg-black/0 group-hover:bg-black/40 flex items-center justify-center transition-all cursor-pointer">
                  {uploading ? (
                    <Loader2 className="w-5 h-5 text-white animate-spin" />
                  ) : (
                    <Camera className="w-5 h-5 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                  )}
                </button>
                <input ref={fileInputRef} type="file" accept="image/*" onChange={handleAvatarUpload}
                  className="hidden" data-testid="avatar-file-input" />
              </div>
              <div>
                <p className="text-sm font-medium text-[#1C1F1D]">{user?.name || 'User'}</p>
                <p className="text-xs text-[#9CA3AF] mt-0.5">{user?.email}</p>
                <button onClick={() => fileInputRef.current?.click()} disabled={uploading}
                  className="text-xs text-[#4A5D4E] hover:underline mt-1.5 font-medium" data-testid="change-avatar-link">
                  {uploading ? 'Hochladen...' : 'Foto ändern'}
                </button>
              </div>
            </div>

            {/* Iter 340 — Stammdaten-Block: BenutzerID (read-only) +
                Vor-/Nachname + Anzeigename + Telefon + Abteilung. `name`
                bleibt darunter für Backwards-Compat erhalten, wird aber
                serverseitig automatisch aus first+last abgeleitet wenn leer. */}
            <div className="bg-[#F3F4F1] rounded-lg p-2.5 flex items-center justify-between" data-testid="profile-user-id-block">
              <span className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">BenutzerID</span>
              <span className="font-mono text-[11px] text-[#4A5D4E]">{user?.user_id}</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Vorname</Label>
                <Input data-testid="profile-first-name-input" value={f.firstName} onChange={e => f.setFirstName(e.target.value)}
                  className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Nachname</Label>
                <Input data-testid="profile-last-name-input" value={f.lastName} onChange={e => f.setLastName(e.target.value)}
                  className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" />
              </div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Anzeigename</Label>
              <Input data-testid="profile-display-name-input" value={f.displayName} onChange={e => f.setDisplayName(e.target.value)}
                placeholder="optional — wird statt Name angezeigt"
                className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Telefonnummer</Label>
                <Input data-testid="profile-phone-input" value={f.phone} onChange={e => f.setPhone(e.target.value)}
                  placeholder="+49 …"
                  className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Abteilung</Label>
                <Input data-testid="profile-department-input" value={f.department} onChange={e => f.setDepartment(e.target.value)}
                  placeholder="z.B. Marketing"
                  className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" />
              </div>
            </div>

            {/* Name (Legacy/Backup) */}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('name')}</Label>
              <Input data-testid="profile-name-input" value={name} onChange={e => setName(e.target.value)}
                placeholder="wird aus Vor-/Nachname abgeleitet wenn leer"
                className="border-[#E2E4E0] focus:border-[#4A5D4E] rounded-xl" />
            </div>

            {/* Email (read-only) */}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">{t('email')}</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9CA3AF]" />
                <Input data-testid="profile-email" value={user?.email || ''} disabled className="pl-10 border-[#E2E4E0] rounded-xl bg-[#F3F4F1]" />
              </div>
            </div>

            {/* iter 212 — link to "Meine Berechtigungen" transparency page */}
            <a href="/me/permissions" data-testid="profile-my-permissions-link"
              className="flex items-center justify-between px-4 py-3 border border-[#E2E4E0] rounded-xl hover:bg-[#F5F4F0] transition group">
              <div className="flex items-center gap-2.5">
                <Shield className="w-4 h-4 text-[#4A5D4E]" />
                <div>
                  <div className="text-sm font-medium text-[#1A1D1B]">Meine Berechtigungen</div>
                  <div className="text-[11px] text-[#6B7280]">Übersicht: Was darfst du, und woher kommen deine Rechte?</div>
                </div>
              </div>
              <ChevronDown className="w-4 h-4 text-[#9CA3AF] group-hover:text-[#4A5D4E] -rotate-90" />
            </a>

            {/* Language */}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">
                <Globe className="w-3.5 h-3.5 inline mr-1" />{t('language')}
              </Label>
              <Select value={lang} onValueChange={setLang}>
                <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="language-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">{t('english')}</SelectItem>
                  <SelectItem value="de">{t('german')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Auto-Reply (Focus Mode) */}
            <div className="border border-[#E2E4E0] rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <BellOff className="w-4 h-4 text-[#D4A373]" />
                  <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">
                    {language === 'de' ? 'Automatische Abwesenheitsnachricht' : 'Auto-Reply (Focus Mode)'}
                  </Label>
                </div>
                <Switch checked={autoReplyEnabled} onCheckedChange={setAutoReplyEnabled} data-testid="auto-reply-toggle" />
              </div>
              {autoReplyEnabled && (
                <div className="space-y-2">
                  <Label className="text-[10px] text-[#9CA3AF] block mb-1.5">
                    {language === 'de' ? 'Nachricht die automatisch gesendet wird wenn du in einer Fokus-Zeit bist:' : 'Message sent automatically when you are in focus mode:'}
                  </Label>
                  <Input value={autoReplyMessage} onChange={e => setAutoReplyMessage(e.target.value)}
                    placeholder={language === 'de' ? 'Ich bin gerade in einer Fokus-Session und antworte später.' : 'I am currently in a focus session and will reply later.'}
                    className="border-[#E2E4E0] rounded-xl text-sm" data-testid="auto-reply-message-input" />
                </div>
              )}
              {/* Iter 275 — Inline-Save direkt am Feld, weil der globale Save-Button weit unten ist */}
              <Button
                onClick={handleSave}
                disabled={saving}
                size="sm"
                variant="outline"
                data-testid="auto-reply-save-btn"
                className="w-full h-9 text-xs rounded-full border-[#4A5D4E]/40 text-[#4A5D4E] hover:bg-[#4A5D4E]/5"
              >
                {saving
                  ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Speichert …</>
                  : <><Save className="w-3.5 h-3.5 mr-1.5" /> {language === 'de' ? 'Abwesenheit speichern' : 'Save away message'}</>}
              </Button>
            </div>

            {/* E-Mail-Praeferenzen (Newsletter / Meeting-Einladungen) */}
            <div className="border border-[#E2E4E0] rounded-xl p-4 space-y-3" data-testid="email-preferences-block">
              <div className="flex items-center gap-2">
                <MailOpen className="w-4 h-4 text-[#4A5D4E]" />
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">
                  {language === 'de' ? 'E-Mail-Einstellungen' : 'E-Mail Preferences'}
                </Label>
              </div>

              <div className="flex items-center justify-between py-1">
                <div>
                  <p className="text-sm font-medium text-[#1C1F1D]">
                    {language === 'de' ? 'Newsletter' : 'Newsletter'}
                  </p>
                  <p className="text-xs text-[#9CA3AF] mt-0.5">
                    {language === 'de'
                      ? 'HTML-Newsletter zu wichtigen News-Beiträgen'
                      : 'HTML newsletter for important news posts'}
                  </p>
                </div>
                <Switch
                  checked={newsletterEnabled}
                  onCheckedChange={setNewsletterEnabled}
                  data-testid="newsletter-enabled-toggle"
                />
              </div>

              <div className="flex items-center justify-between py-1">
                <div>
                  <p className="text-sm font-medium text-[#1C1F1D]">
                    {language === 'de' ? 'Meeting-Einladungen' : 'Meeting invitations'}
                  </p>
                  <p className="text-xs text-[#9CA3AF] mt-0.5">
                    {language === 'de'
                      ? 'ICS-Einladungen per E-Mail bei neuen Meetings'
                      : 'ICS invitations by e-mail for new meetings'}
                  </p>
                </div>
                <Switch
                  checked={meetingInvitesEnabled}
                  onCheckedChange={setMeetingInvitesEnabled}
                  data-testid="meeting-invites-toggle"
                />
              </div>

              <div>
                <Label className="text-[10px] text-[#9CA3AF] block mb-1.5">
                  {language === 'de' ? 'Zusammenfassung-Frequenz' : 'Digest frequency'}
                </Label>
                <Select value={digestFrequency} onValueChange={setDigestFrequency}>
                  <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="digest-frequency-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="immediate">{language === 'de' ? 'Sofort' : 'Immediate'}</SelectItem>
                    <SelectItem value="daily">{language === 'de' ? 'Taeglich' : 'Daily'}</SelectItem>
                    <SelectItem value="weekly">{language === 'de' ? 'Woechentlich' : 'Weekly'}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button
                onClick={handleSavePrefs}
                disabled={savingPrefs}
                data-testid="save-email-preferences-button"
                variant="outline"
                className="w-full border-[#E2E4E0] hover:bg-[#F3F4F1] rounded-full h-9 text-sm"
              >
                {savingPrefs
                  ? '...'
                  : (language === 'de' ? 'E-Mail-Einstellungen speichern' : 'Save e-mail preferences')}
              </Button>
            </div>

            {/* Privatsphaere — In-Office-Widget Opt-Out (iter 238) */}
            <PrivacySection language={language} />

            {/* Standard-Bürotage (iter 241) — Recurring Desk-Bookings */}
            <OfficeDaysSection language={language} />

            {/* Meine Rechte (effektive Capabilities) */}
            {permInfo && (
              <div className="border border-[#E2E4E0] rounded-xl overflow-hidden" data-testid="my-permissions-block">
                <button
                  type="button"
                  onClick={() => setPermsOpen(o => !o)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-[#F3F4F1] transition-colors"
                  data-testid="my-permissions-toggle"
                >
                  <div className="flex items-center gap-2">
                    <Shield className="w-4 h-4 text-[#4A5D4E]" />
                    <div className="text-left">
                      <p className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">
                        {language === 'de' ? 'Meine Rechte' : 'My permissions'}
                      </p>
                      <p className="text-[11px] text-[#9CA3AF] mt-0.5">
                        {(permInfo.capabilities || []).length} {language === 'de' ? 'aktive Rechte' : 'active capabilities'}
                        {' · '}
                        {language === 'de' ? 'Rolle' : 'Role'}: <span className="font-medium capitalize">{permInfo.role}</span>
                      </p>
                    </div>
                  </div>
                  <ChevronDown
                    className={`w-4 h-4 text-[#9CA3AF] transition-transform ${permsOpen ? 'rotate-180' : ''}`}
                  />
                </button>
                {permsOpen && (
                  <div className="px-4 pb-4 pt-1 space-y-4 border-t border-[#E2E4E0]" data-testid="my-permissions-list">
                    {(permInfo.groups || []).length > 0 && (
                      <div>
                        <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#9CA3AF] mb-1.5">
                          {language === 'de' ? 'Gruppen' : 'Groups'}
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {permInfo.groups.map((g, i) => (
                            <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-[#4A5D4E]/10 text-[#4A5D4E]">
                              {g}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Group capabilities by category */}
                    {(() => {
                      const byCat = {};
                      const labels = permInfo.capability_labels || {};
                      (permInfo.capabilities || []).forEach(cap => {
                        const meta = labels[cap] || { label: cap, category: 'global' };
                        (byCat[meta.category] = byCat[meta.category] || []).push({ key: cap, ...meta });
                      });
                      const order = Object.keys(CATEGORY_LABELS);
                      const sorted = order.filter(c => byCat[c]);
                      Object.keys(byCat).forEach(c => { if (!sorted.includes(c)) sorted.push(c); });
                      return sorted.map(cat => (
                        <div key={cat} data-testid={`cap-category-${cat}`}>
                          <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-[#9CA3AF] mb-1.5">
                            {CATEGORY_LABELS[cat] || cat}
                          </p>
                          <div className="flex flex-wrap gap-1.5">
                            {byCat[cat].map(c => (
                              <span
                                key={c.key}
                                title={c.description || c.key}
                                className="text-xs px-2 py-0.5 rounded-full bg-[#F3F4F1] text-[#4A5D4E] border border-[#E2E4E0]"
                              >
                                {c.label || c.key}
                              </span>
                            ))}
                          </div>
                        </div>
                      ));
                    })()}

                    {(permInfo.capabilities || []).length === 0 && (
                      <p className="text-xs text-[#9CA3AF]">
                        {language === 'de' ? 'Keine aktiven Rechte.' : 'No active capabilities.'}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* CalDAV / ICS Subscription (read-only external calendar) */}
            {caldav && (
              <div className="border border-[#E2E4E0] rounded-xl p-4 space-y-3" data-testid="caldav-block">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-[#4A5D4E]" />
                    <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">
                      {language === 'de' ? 'Externer Kalender (ICS)' : 'External calendar (ICS)'}
                    </Label>
                  </div>
                  <Switch checked={!!caldav.enabled}
                    onCheckedChange={v => setCaldav(p => ({ ...p, enabled: v }))}
                    data-testid="caldav-enabled-toggle" />
                </div>
                <p className="text-[11px] text-[#9CA3AF]">
                  {language === 'de'
                    ? 'Verbinde Outlook oder Google per öffentlichem ICS-Link (Outlook: „Kalender veröffentlichen" · Google: „Geheime Adresse im iCal-Format"). Zeigt Konflikte beim Buchen neuer Meetings.'
                    : 'Subscribe to Outlook or Google via the public ICS link. Warns when booking conflicts.'}
                </p>
                <div>
                  <Label className="text-[10px] text-[#9CA3AF] block mb-1">ICS-URL</Label>
                  <Input value={caldav.url || ''}
                    onChange={e => setCaldav(p => ({ ...p, url: e.target.value }))}
                    placeholder="https://outlook.office365.com/owa/calendar/.../calendar.ics"
                    className="border-[#E2E4E0] rounded-xl font-mono text-xs"
                    data-testid="caldav-url-input" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div>
                    <Label className="text-[10px] text-[#9CA3AF] block mb-1">
                      {language === 'de' ? 'Benutzer (optional)' : 'Username (optional)'}
                    </Label>
                    <Input value={caldav.username || ''}
                      onChange={e => setCaldav(p => ({ ...p, username: e.target.value }))}
                      placeholder="user@klinik.de"
                      className="border-[#E2E4E0] rounded-xl text-xs"
                      data-testid="caldav-username-input" />
                  </div>
                  <div>
                    <Label className="text-[10px] text-[#9CA3AF] block mb-1">
                      {language === 'de' ? 'Passwort (optional)' : 'Password (optional)'}
                    </Label>
                    <Input type="password" value={caldavPw}
                      onChange={e => setCaldavPw(e.target.value)}
                      placeholder={caldav.has_password ? '•••••• (gespeichert)' : ''}
                      className="border-[#E2E4E0] rounded-xl text-xs"
                      data-testid="caldav-password-input" />
                  </div>
                </div>
                <div className="flex items-center justify-between py-1">
                  <div>
                    <span className="text-xs text-[#1C1F1D]">
                      {language === 'de' ? 'Stündlich automatisch synchronisieren' : 'Auto-sync hourly'}
                    </span>
                  </div>
                  <Switch checked={caldav.auto_sync !== false}
                    onCheckedChange={v => setCaldav(p => ({ ...p, auto_sync: v }))}
                    data-testid="caldav-auto-sync-toggle" />
                </div>
                <div className="flex gap-2 items-center">
                  <Button size="sm" onClick={saveCaldav} disabled={savingCaldav}
                    className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-8 text-xs px-4"
                    data-testid="caldav-save-btn">
                    {savingCaldav ? '...' : (language === 'de' ? 'Speichern' : 'Save')}
                  </Button>
                  <Button size="sm" variant="outline" onClick={syncCaldavNow}
                    disabled={syncingCaldav || !caldav.url || !caldav.enabled}
                    className="rounded-full h-8 text-xs px-4 border-[#E2E4E0]"
                    data-testid="caldav-sync-btn">
                    {syncingCaldav ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}
                    {language === 'de' ? 'Jetzt synchronisieren' : 'Sync now'}
                  </Button>
                </div>
                {(caldav.last_sync_at || caldav.last_sync_error) && (
                  <div className="text-[11px] pt-1 border-t border-[#E2E4E0]">
                    {caldav.last_sync_error ? (
                      <p className="text-[#C87967] flex items-start gap-1">
                        <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" /> {caldav.last_sync_error}
                      </p>
                    ) : (
                      <p className="text-[#6B8E23] flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        {caldav.events_count || 0} {language === 'de' ? 'Termine' : 'events'} · zuletzt {new Date(caldav.last_sync_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Outgoing iCal Feed — Meetings → external calendar (Google/Outlook/Apple) */}
            {icalFeed && (
              <div className="border border-[#E2E4E0] rounded-xl p-4 space-y-3" data-testid="ical-feed-block">
                <div className="flex items-center gap-2">
                  <Download className="w-4 h-4 text-[#4A5D4E]" />
                  <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">
                    {language === 'de' ? 'MeetFlow → eigener Kalender (Abo-Link)' : 'MeetFlow → your calendar (subscribe)'}
                  </Label>
                </div>
                <p className="text-[11px] text-[#9CA3AF]">
                  {language === 'de'
                    ? 'Abonniere deine MeetFlow-Meetings in Google Calendar, Apple Kalender oder Outlook. Änderungen werden automatisch übernommen (aktualisiert meist alle 1–24 h je nach Anbieter).'
                    : 'Subscribe to your MeetFlow meetings in Google Calendar, Apple Calendar or Outlook. Changes sync automatically.'}
                </p>
                <div>
                  <Label className="text-[10px] text-[#9CA3AF] block mb-1">{language === 'de' ? 'Abo-URL (HTTPS)' : 'Subscribe URL (HTTPS)'}</Label>
                  <div className="flex gap-2">
                    <Input
                      readOnly
                      ref={icalFeedInputRef}
                      value={icalFeed.subscribe_url || ''}
                      className="border-[#E2E4E0] rounded-xl font-mono text-[10px] bg-[#F9F9F8]"
                      data-testid="ical-feed-url"
                      onFocus={e => e.target.select()}
                    />
                    <Button size="sm" variant="outline"
                      onClick={async () => {
                        const { copyToClipboard } = await import('../lib/clipboard');
                        const res = await copyToClipboard(icalFeed.subscribe_url || '', icalFeedInputRef.current);
                        if (res.ok) {
                          toast.success(language === 'de' ? 'Abo-URL kopiert' : 'Subscribe URL copied');
                        } else if (res.selected) {
                          toast.info(language === 'de'
                            ? 'Bitte Strg+C / ⌘+C drücken (Browser-Sandbox blockiert automatisches Kopieren)'
                            : 'Press Ctrl+C / ⌘+C to copy (browser sandbox blocks automatic copy)');
                        } else {
                          toast.error(language === 'de' ? 'Kopieren nicht möglich' : 'Copy not possible');
                        }
                      }}
                      className="rounded-full h-9 text-xs px-3 border-[#E2E4E0] shrink-0"
                      data-testid="ical-feed-copy-btn">
                      {language === 'de' ? 'Kopieren' : 'Copy'}
                    </Button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <a href={icalFeed.webcal_url} data-testid="ical-feed-webcal-btn"
                    className="inline-flex items-center gap-1.5 text-[11px] bg-[#4A5D4E] text-white rounded-full px-3 h-8 hover:bg-[#3E4E42] transition-colors">
                    <Calendar className="w-3 h-3" />
                    {language === 'de' ? 'In Kalender-App öffnen' : 'Open in calendar app'}
                  </a>
                  <button
                    type="button"
                    data-testid="ical-feed-google-btn"
                    onClick={async () => {
                      // Iter 277 — robust "Add to Google Calendar" flow:
                      // copy the URL first (so the user only needs to Ctrl+V),
                      // then open the official Add-by-URL page. The legacy
                      // `?cid=` deep-link is unreliable for non-whitelisted
                      // domains and produces the dreaded "URL überprüfen" error.
                      const url = icalFeed.subscribe_url || '';
                      const { copyToClipboard } = await import('../lib/clipboard');
                      const res = await copyToClipboard(url, icalFeedInputRef.current);
                      if (res.ok) {
                        toast.success(language === 'de'
                          ? 'URL kopiert. Im Google-Tab bei „Aus URL hinzufügen" einfügen.'
                          : 'URL copied. Paste it in the Google tab under "Add by URL".');
                      } else {
                        toast.info(language === 'de'
                          ? 'URL ist oben markiert — bitte mit Strg+C / ⌘+C kopieren und in Google einfügen.'
                          : 'URL is selected above — copy with Ctrl+C / ⌘+C and paste in Google.');
                      }
                      window.open('https://calendar.google.com/calendar/u/0/r/settings/addbyurl', '_blank', 'noopener,noreferrer');
                    }}
                    className="inline-flex items-center gap-1.5 text-[11px] bg-white border border-[#E2E4E0] text-[#1C1F1D] rounded-full px-3 h-8 hover:bg-[#F3F4F1] transition-colors">
                    {language === 'de' ? 'Zu Google Calendar' : 'Add to Google Calendar'}
                  </button>
                  <Button size="sm" variant="outline" onClick={regenerateIcalFeed} disabled={rotatingIcal}
                    className="rounded-full h-8 text-xs px-3 border-[#E2E4E0]"
                    data-testid="ical-feed-rotate-btn">
                    {rotatingIcal ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}
                    {language === 'de' ? 'Neu erzeugen' : 'Regenerate'}
                  </Button>
                </div>
                <div className="text-[10px] text-[#9CA3AF] space-y-1 pt-1 border-t border-[#E2E4E0]">
                  <p className="font-medium text-[#6B7280]">
                    {language === 'de' ? 'Anleitung:' : 'Instructions:'}
                  </p>
                  <p>• <strong>Google:</strong> {language === 'de' ? 'Klick „Zu Google Calendar" → URL ist kopiert → in Google mit Strg+V einfügen → „Kalender hinzufügen"' : 'Click "Add to Google Calendar" → URL is copied → paste in Google with Ctrl+V → "Add calendar"'}</p>
                  <p>• <strong>Apple:</strong> {language === 'de' ? 'Systemeinstellungen → Internet-Accounts → Kalenderabo hinzufügen → URL einfügen' : 'System Prefs → Internet Accounts → Add calendar subscription → paste URL'}</p>
                  <p>• <strong>Outlook:</strong> {language === 'de' ? 'Kalender → „Kalender hinzufügen" → „Aus dem Internet abonnieren" → URL einfügen' : 'Calendar → "Add calendar" → "Subscribe from web" → paste URL'}</p>
                </div>
              </div>
            )}

            {/* Role */}
            <div className="p-3 bg-[#F3F4F1] rounded-lg">
              <span className="text-xs text-[#6B7280]">Role: </span>
              <span className="text-xs font-medium text-[#4A5D4E] capitalize" data-testid="user-role">{user?.role}</span>
            </div>

            <Button onClick={handleSave} disabled={saving} data-testid="save-profile-button"
              className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11 font-medium transition-all active:scale-95">
              {saving ? '...' : <><Save className="w-4 h-4 mr-2" /> {t('editProfile')}</>}
            </Button>

            {/* iter 153 — Push-Health Warn-Banner */}
            {pushStatus.supported && (
              <div
                className={`flex items-start gap-3 p-3 rounded-xl border ${
                  pushStatus.permission === 'granted' && pushStatus.subscribed
                    ? 'bg-[#6B8E23]/5 border-[#6B8E23]/30'
                    : 'bg-[#FFF8E7] border-[#D4A373]/40'
                }`}
                data-testid="push-health-banner"
              >
                {pushStatus.permission === 'granted' && pushStatus.subscribed ? (
                  <CheckCircle2 className="w-4 h-4 mt-0.5 text-[#6B8E23] flex-shrink-0" />
                ) : (
                  <BellOff className="w-4 h-4 mt-0.5 text-[#D4A373] flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[#1C1F1D]">
                    {pushStatus.permission === 'granted' && pushStatus.subscribed
                      ? 'Push-Benachrichtigungen aktiv'
                      : pushStatus.permission === 'denied'
                      ? 'Push-Benachrichtigungen blockiert'
                      : 'Push-Benachrichtigungen nicht aktiv'}
                  </p>
                  <p className="text-[11px] text-[#6B7280] leading-snug mt-0.5">
                    {pushStatus.permission === 'granted' && pushStatus.subscribed
                      ? 'Du erhältst Anrufe und wichtige Nachrichten auch bei gesperrtem Bildschirm.'
                      : pushStatus.permission === 'denied'
                      ? 'Browser hat Push blockiert. Freigabe in den Browser-Einstellungen (Schloss-Symbol in der Adressleiste → Benachrichtigungen → „Zulassen"), danach Seite neu laden.'
                      : 'Klicke „Jetzt aktivieren" und bestätige im Browser-Popup mit „Zulassen". Push funktioniert nur über HTTPS und nicht im Inkognito-Modus.'}
                  </p>
                  {pushStatus.permission !== 'denied' && (
                    <button
                      onClick={async () => {
                        setRepairing(true);
                        try {
                          if (pushStatus.permission !== 'granted') {
                            await subscribeToPush();
                            toast.success('Push aktiviert');
                          } else {
                            const res = await ensureServerHasPushSubscription();
                            if (res.ok) toast.success('Push-Registrierung repariert');
                            else toast.error('Reparatur fehlgeschlagen: ' + res.reason);
                          }
                          const s = await getPushSubscriptionStatus();
                          setPushStatus(s);
                        } catch (e) {
                          toast.error(e.message || 'Fehler');
                        } finally { setRepairing(false); }
                      }}
                      disabled={repairing}
                      data-testid="push-repair-button"
                      className="mt-2 px-3 py-1 rounded-lg text-[11px] font-medium bg-[#4A5D4E] text-white hover:bg-[#3E4E42] disabled:opacity-50 transition-colors"
                    >
                      {repairing ? '...' : (pushStatus.permission === 'granted' ? 'Erneut registrieren' : 'Jetzt aktivieren')}
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Geräte-Diagnose & Push-Test — für iOS/Android User zum Testen von WebRTC + Push */}
            <Link
              to="/diag"
              data-testid="profile-diag-link"
              className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-[#E2E4E0] hover:bg-[#F3F4F1] transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center">
                  <Stethoscope className="w-4 h-4 text-[#4A5D4E]" />
                </div>
                <div>
                  <div className="text-sm font-medium text-[#1C1F1D]">
                    {language === 'de' ? 'Geräte-Diagnose & Push-Test' : 'Device diagnostics & push test'}
                  </div>
                  <div className="text-[11px] text-[#6B7280]">
                    {language === 'de'
                      ? 'Kamera, Mikrofon, WebRTC & Push-Benachrichtigungen prüfen'
                      : 'Check camera, microphone, WebRTC & push notifications'}
                  </div>
                </div>
              </div>
              <ChevronDown className="w-4 h-4 -rotate-90 text-[#9CA3AF] group-hover:text-[#4A5D4E] transition-colors" />
            </Link>

            {/* iter 183 — per-user notification preferences */}
            <NotificationPrefsSection language={language} />

            {/* iter 283 — Stellvertreter (Buchungsvollmacht) */}
            <DelegatesSection language={language} />

            {/* iter 292 — multi-license self-service with photos */}
            <DriverLicenseSection />

            {/* Mein Feedback (signed submissions only) */}
            {myFeedback.length > 0 && (
              <div className="pt-5 mt-2 border-t border-[#E2E4E0]" data-testid="my-feedback-section">
                <button
                  type="button"
                  onClick={() => setMyFeedbackOpen(v => !v)}
                  className="w-full flex items-center justify-between gap-2 hover:bg-[#F3F4F1] -mx-2 px-2 py-1 rounded-lg transition-colors"
                  data-testid="toggle-my-feedback"
                >
                  <div className="flex items-center gap-2">
                    <MessageSquare className="w-4 h-4 text-[#4A5D4E]" />
                    <h3 className="text-sm font-semibold text-[#1C1F1D]">
                      {language === 'de' ? 'Mein Feedback' : 'My Feedback'}
                    </h3>
                    <span className="text-[10px] bg-[#4A5D4E]/10 text-[#4A5D4E] rounded-full px-2 py-0.5">
                      {myFeedback.length}
                    </span>
                  </div>
                  <ChevronDown className={`w-4 h-4 text-[#9CA3AF] transition-transform ${myFeedbackOpen ? 'rotate-180' : ''}`} />
                </button>
                {myFeedbackOpen && (
                  <div className="mt-3 space-y-2" data-testid="my-feedback-list">
                    <p className="text-[11px] text-[#6B7280] leading-relaxed">
                      {language === 'de'
                        ? 'Hier siehst du nur dein nicht-anonym abgesendetes Feedback samt Bearbeitungsstatus und Admin-Antworten. Anonymes Feedback erscheint nicht in dieser Liste.'
                        : 'Only your non-anonymous feedback is listed here with status and admin replies. Anonymous feedback is not tracked.'}
                    </p>
                    {myFeedback.map(fb => {
                      const statusLabel = fb.status === 'new'
                        ? (language === 'de' ? 'Neu' : 'New')
                        : fb.status === 'in_progress'
                        ? (language === 'de' ? 'In Bearbeitung' : 'In Progress')
                        : (language === 'de' ? 'Erledigt' : 'Resolved');
                      const statusColor = fb.status === 'new' ? '#C87967' : fb.status === 'in_progress' ? '#D4A373' : '#6B8E23';
                      return (
                        <div key={fb.feedback_id} className="border border-[#E2E4E0] rounded-xl p-3" data-testid={`my-feedback-${fb.feedback_id}`}>
                          <div className="flex items-center gap-2 flex-wrap mb-1.5">
                            <span className="text-xs font-medium text-[#1C1F1D]">{fb.subject || (language === 'de' ? 'Feedback' : 'Feedback')}</span>
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium"
                              style={{ backgroundColor: `${statusColor}15`, color: statusColor }}>
                              {statusLabel}
                            </span>
                            <span className="text-[10px] text-[#9CA3AF] ml-auto">
                              {new Date(fb.created_at).toLocaleDateString(language === 'de' ? 'de-DE' : 'en-US')}
                            </span>
                          </div>
                          <p className="text-xs text-[#4B5563] break-words whitespace-pre-wrap">{fb.content}</p>
                          {fb.admin_response && (
                            <div className="mt-2 p-2.5 bg-[#F3F4F1] rounded-lg border-l-2 border-[#4A5D4E]">
                              <div className="flex items-center gap-1.5 mb-1">
                                <CheckCircle2 className="w-3 h-3 text-[#4A5D4E]" />
                                <span className="text-[10px] font-medium text-[#4A5D4E]">
                                  {fb.responded_by || (language === 'de' ? 'Admin' : 'Admin')}
                                  {language === 'de' ? ' hat geantwortet:' : ' replied:'}
                                </span>
                              </div>
                              <p className="text-xs text-[#4B5563] break-words whitespace-pre-wrap">{fb.admin_response}</p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Zwei-Faktor (iter 188) */}
            <TwoFactorSection />

            {/* Iter 274 — Sicherheit: Aus allen Geräten abmelden */}
            <div className="pt-5 mt-2 border-t border-[#E2E4E0]">
              <div className="flex items-center gap-2 mb-1">
                <ShieldOff className="w-4 h-4 text-[#C87967]" />
                <h3 className="text-sm font-semibold text-[#1C1F1D]">Sicherheit</h3>
              </div>
              <p className="text-[11px] text-[#6B7280] mb-3 leading-relaxed">
                Du hast dich an einem fremden Gerät vergessen oder dein Handy verloren?
                Mit einem Klick beendest du alle aktiven Sitzungen — auf diesem Gerät,
                anderen Browsern und Smartphones gleichzeitig.
              </p>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="outline"
                    data-testid="profile-logout-everywhere-btn"
                    className="w-full border-[#C87967]/40 text-[#C87967] rounded-full h-10 text-sm hover:bg-[#C87967]/5 hover:text-[#C87967]"
                  >
                    <ShieldOff className="w-4 h-4 mr-2" /> Aus allen Geräten abmelden
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent data-testid="profile-logout-everywhere-dialog">
                  <AlertDialogHeader>
                    <AlertDialogTitle className="text-[#C87967] flex items-center gap-2">
                      <ShieldOff className="w-5 h-5" /> Wirklich aus allen Geräten abmelden?
                    </AlertDialogTitle>
                    <AlertDialogDescription className="text-xs text-[#6B7280] space-y-2 pt-2">
                      Alle bestehenden Sitzungen werden sofort beendet. Du musst dich
                      anschließend an jedem Gerät neu anmelden. Diese Aktion kann
                      nicht rückgängig gemacht werden.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel data-testid="profile-logout-everywhere-cancel">Abbrechen</AlertDialogCancel>
                    <AlertDialogAction
                      data-testid="profile-logout-everywhere-confirm"
                      onClick={handleLogoutEverywhere}
                      disabled={loggingOutAll}
                      className="bg-[#C87967] hover:bg-[#B5624F] text-white"
                    >
                      {loggingOutAll
                        ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />…</>
                        : 'Ja, überall abmelden'}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>

            {/* DSGVO / Datenschutz */}
            <div className="pt-5 mt-2 border-t border-[#E2E4E0]">
              <div className="flex items-center gap-2 mb-1">
                <Shield className="w-4 h-4 text-[#4A5D4E]" />
                <h3 className="text-sm font-semibold text-[#1C1F1D]">Datenschutz &amp; DSGVO</h3>
              </div>
              <p className="text-[11px] text-[#6B7280] mb-3 leading-relaxed">
                Nach DSGVO Art. 17 und Art. 20 kannst du jederzeit eine Kopie deiner gespeicherten
                Daten herunterladen oder dein Konto vollständig löschen lassen.
              </p>

              <div className="space-y-2">
                <Button
                  variant="outline"
                  onClick={handleDataExport}
                  disabled={exporting}
                  data-testid="dsgvo-export-button"
                  className="w-full border-[#E2E4E0] rounded-full h-10 text-sm hover:bg-[#F3F4F1]"
                >
                  {exporting
                    ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Export wird erstellt …</>
                    : <><Download className="w-4 h-4 mr-2" /> {t('exportMyDataJson')}</>}
                </Button>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="outline"
                      data-testid="dsgvo-delete-button"
                      className="w-full border-[#C87967]/40 text-[#C87967] rounded-full h-10 text-sm hover:bg-[#C87967]/5 hover:text-[#C87967]"
                    >
                      <Trash2 className="w-4 h-4 mr-2" /> {t('deleteAccountForever')}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent data-testid="dsgvo-delete-dialog">
                    <AlertDialogHeader>
                      <AlertDialogTitle className="text-[#C87967] flex items-center gap-2">
                        <AlertCircle className="w-5 h-5" /> {t('deleteAccountConfirm')}
                      </AlertDialogTitle>
                      <AlertDialogDescription asChild>
                        <div className="text-xs text-[#6B7280] space-y-2 pt-2">
                          <p>{t('thisActionIs')} <strong>{t('irreversible')}</strong>. {language === 'de' ? 'Folgendes passiert:' : 'The following happens:'}</p>
                          <ul className="list-disc list-inside space-y-0.5 pl-1">
                            <li>Alle privaten Daten werden gelöscht: Chats, Reaktionen, Lesebestätigungen, Push-Abos, Focus-Zeiten</li>
                            <li>{t('publishedContentNote')} <em>{language === 'de' ? '„Gelöschter Nutzer"' : '"Deleted user"'}</em></li>
                            <li>{t('sessionsWillBeInvalid')}</li>
                          </ul>
                          <p className="pt-1">
                            {t('typeToConfirm')} <code className="bg-[#F3F4F1] px-1.5 py-0.5 rounded">{language === 'de' ? 'LÖSCHEN' : 'DELETE'}</code> {t('inTheField')}
                          </p>
                          <Input
                            value={deleteConfirmText}
                            onChange={e => setDeleteConfirmText(e.target.value)}
                            placeholder={language === 'de' ? 'LÖSCHEN' : 'DELETE'}
                            className="border-[#E2E4E0] rounded-lg text-sm mt-1"
                            data-testid="dsgvo-delete-confirm-input"
                          />
                        </div>
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel
                        onClick={() => setDeleteConfirmText('')}
                        data-testid="dsgvo-delete-cancel"
                      >Abbrechen</AlertDialogCancel>
                      <AlertDialogAction
                        disabled={deleteConfirmText !== (language === 'de' ? 'LÖSCHEN' : 'DELETE') || deleting}
                        onClick={handleAccountDelete}
                        data-testid="dsgvo-delete-confirm"
                        className="bg-[#C87967] hover:bg-[#B5624F] text-white"
                      >
                        {deleting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Ja, löschen'}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
