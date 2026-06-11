import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import api from '../lib/api';
import { getPushSubscriptionStatus, isPushSupported } from '../lib/push';

/**
 * useProfileForm — bundles the 18+ useState hooks ProfilePage used to
 * declare inline into a single cohesive hook. Owns:
 *   • basic profile (name, language, auto-reply)
 *   • e-mail preferences (newsletter/meeting/digest)
 *   • permissions snapshot
 *   • CalDAV inbound config + outgoing iCal-feed token
 *   • push status
 *   • DSGVO export/delete state
 *   • "my feedback" list
 *
 * All initial data is fetched in a single useEffect on mount.
 *
 * Extracted from ProfilePage during the iter 219 refactor.
 */
export default function useProfileForm({ user, setUser, language, setLanguage }) {
  // Basic profile
  const [name, setName] = useState(user?.name || '');
  const [lang, setLang] = useState(user?.language || language);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(user?.auto_reply_enabled || false);
  const [autoReplyMessage, setAutoReplyMessage] = useState(user?.auto_reply_message || '');
  // Iter 340 — Stammdaten-Erweiterung im eigenen Profil.
  const [firstName, setFirstName] = useState(user?.first_name || '');
  const [lastName, setLastName] = useState(user?.last_name || '');
  const [displayName, setDisplayName] = useState(user?.display_name || '');
  const [phone, setPhone] = useState(user?.phone || '');
  const [department, setDepartment] = useState(user?.department || '');

  // E-Mail preferences
  const [newsletterEnabled, setNewsletterEnabled] = useState(true);
  const [meetingInvitesEnabled, setMeetingInvitesEnabled] = useState(true);
  const [digestFrequency, setDigestFrequency] = useState('immediate');
  const [savingPrefs, setSavingPrefs] = useState(false);

  // Permissions snapshot
  const [permInfo, setPermInfo] = useState(null);
  const [permsOpen, setPermsOpen] = useState(false);

  // CalDAV
  const [caldav, setCaldav] = useState(null);
  const [caldavPw, setCaldavPw] = useState('');
  const [savingCaldav, setSavingCaldav] = useState(false);
  const [syncingCaldav, setSyncingCaldav] = useState(false);

  // Outgoing iCal feed
  const [icalFeed, setIcalFeed] = useState(null);
  const [rotatingIcal, setRotatingIcal] = useState(false);

  // DSGVO
  const [exporting, setExporting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  // Push health
  const [pushStatus, setPushStatus] = useState({ supported: isPushSupported(), permission: 'default', subscribed: false });
  const [repairing, setRepairing] = useState(false);

  // My feedback
  const [myFeedback, setMyFeedback] = useState([]);
  const [myFeedbackOpen, setMyFeedbackOpen] = useState(false);

  // Initial data load
  useEffect(() => {
    api.get('/users/profile').then(({ data }) => {
      setAutoReplyEnabled(data.auto_reply_enabled || false);
      setAutoReplyMessage(data.auto_reply_message || '');
      // Iter 340 — Stammdaten frisch vom Server holen statt aus user-Cache.
      if (data.first_name !== undefined) setFirstName(data.first_name || '');
      if (data.last_name !== undefined) setLastName(data.last_name || '');
      if (data.display_name !== undefined) setDisplayName(data.display_name || '');
      if (data.phone !== undefined) setPhone(data.phone || '');
      if (data.department !== undefined) setDepartment(data.department || '');
    }).catch(() => {});
    getPushSubscriptionStatus().then(setPushStatus).catch(() => {});
    api.get('/users/me/email-preferences').then(({ data }) => {
      setNewsletterEnabled(data.newsletter_enabled !== false);
      setMeetingInvitesEnabled(data.meeting_invites_enabled !== false);
      setDigestFrequency(data.digest_frequency || 'immediate');
    }).catch(() => {});
    api.get('/user/permissions').then(({ data }) => setPermInfo(data)).catch(() => {});
    api.get('/users/me/caldav-config').then(({ data }) => setCaldav(data)).catch(() => {});
    api.get('/calendar/my-feed-token').then(({ data }) => setIcalFeed(data)).catch(() => {});
    api.get('/feedback/my').then(({ data }) => setMyFeedback(data || [])).catch(() => {});
    if (typeof window !== 'undefined' && window.location.hash === '#my-feedback') {
      setMyFeedbackOpen(true);
      setTimeout(() => {
        const el = document.querySelector('[data-testid="my-feedback-section"]');
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 300);
    }
  }, []);

  // Handlers
  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const { data } = await api.put('/users/profile', {
        name, language: lang,
        auto_reply_enabled: autoReplyEnabled,
        auto_reply_message: autoReplyMessage,
        // Iter 340 — Stammdaten mitspeichern.
        first_name: firstName,
        last_name: lastName,
        display_name: displayName,
        phone,
        department,
      });
      setUser(prev => ({ ...prev, ...data }));
      setLanguage(lang);
      toast.success('Profil aktualisiert');
    } catch {
      toast.error('Fehler beim Aktualisieren');
    } finally { setSaving(false); }
  }, [name, lang, autoReplyEnabled, autoReplyMessage, firstName, lastName, displayName, phone, department, setUser, setLanguage]);

  const handleSavePrefs = useCallback(async () => {
    setSavingPrefs(true);
    try {
      await api.put('/users/me/email-preferences', {
        newsletter_enabled: newsletterEnabled,
        meeting_invites_enabled: meetingInvitesEnabled,
        digest_frequency: digestFrequency,
      });
      toast.success(language === 'de' ? 'E-Mail-Einstellungen gespeichert' : 'E-Mail preferences saved');
    } catch {
      toast.error(language === 'de' ? 'Fehler beim Speichern' : 'Failed to save');
    } finally { setSavingPrefs(false); }
  }, [newsletterEnabled, meetingInvitesEnabled, digestFrequency, language]);

  const handleAvatarUpload = useCallback(async (file) => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { toast.error('Datei zu gross (max. 5MB)'); return; }
    if (!file.type.startsWith('image/')) { toast.error('Nur Bilddateien erlaubt'); return; }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const { data } = await api.post('/users/avatar', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setUser(prev => ({
        ...prev,
        avatar: data.avatar,
        avatar_updated_at: data.avatar_updated_at,
      }));
      toast.success('Avatar hochgeladen');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload fehlgeschlagen');
    } finally { setUploading(false); }
  }, [setUser]);

  const handleDataExport = useCallback(async () => {
    setExporting(true);
    try {
      const { data } = await api.get('/users/me/export');
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `meetflow-daten-${(user?.email || 'export').replace(/[^a-z0-9@.]/gi, '_')}-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('Datenexport heruntergeladen');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Export fehlgeschlagen');
    } finally { setExporting(false); }
  }, [user?.email]);

  const handleAccountDelete = useCallback(async () => {
    setDeleting(true);
    try {
      await api.delete('/users/me');
      toast.success('Account gelöscht – du wirst abgemeldet.');
      setTimeout(() => { window.location.href = '/login'; }, 1200);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Löschen fehlgeschlagen');
      setDeleting(false);
    }
  }, []);

  const saveCaldav = useCallback(async () => {
    setSavingCaldav(true);
    try {
      const payload = {
        enabled: !!caldav.enabled,
        url: (caldav.url || '').trim(),
        username: caldav.username || '',
        auto_sync: caldav.auto_sync !== false,
      };
      if (caldavPw) payload.password = caldavPw;
      const { data } = await api.put('/users/me/caldav-config', payload);
      setCaldav(data);
      setCaldavPw('');
      toast.success(language === 'de' ? 'Kalender-Einstellungen gespeichert' : 'Calendar settings saved');
    } catch {
      toast.error(language === 'de' ? 'Fehler beim Speichern' : 'Save failed');
    } finally { setSavingCaldav(false); }
  }, [caldav, caldavPw, language]);

  const syncCaldavNow = useCallback(async () => {
    setSyncingCaldav(true);
    try {
      const { data } = await api.post('/users/me/caldav-sync');
      toast.success(language === 'de' ? `${data.events} Termine importiert` : `${data.events} events imported`);
      const { data: cfg } = await api.get('/users/me/caldav-config');
      setCaldav(cfg);
    } catch (err) {
      toast.error(err.response?.data?.detail || (language === 'de' ? 'Sync fehlgeschlagen' : 'Sync failed'));
      try { const { data: cfg } = await api.get('/users/me/caldav-config'); setCaldav(cfg); } catch {}
    } finally { setSyncingCaldav(false); }
  }, [language]);

  const regenerateIcalFeed = useCallback(async () => {
    if (!window.confirm(language === 'de'
      ? 'Aktuelle Abo-URL wird ungültig. Du musst den neuen Link in deinen Kalender-Apps neu eintragen. Fortfahren?'
      : 'Current subscription URL will become invalid. You need to re-add the new link in all calendar apps. Continue?'
    )) return;
    setRotatingIcal(true);
    try {
      const { data } = await api.post('/calendar/my-feed-token/regenerate');
      setIcalFeed(data);
      toast.success(language === 'de' ? 'Neuer Abo-Link erzeugt' : 'New subscription link generated');
    } catch {
      toast.error(language === 'de' ? 'Fehler beim Erneuern' : 'Regeneration failed');
    } finally { setRotatingIcal(false); }
  }, [language]);

  return {
    // basic
    name, setName, lang, setLang, saving, uploading,
    autoReplyEnabled, setAutoReplyEnabled, autoReplyMessage, setAutoReplyMessage,
    // Iter 340 — Stammdaten
    firstName, setFirstName, lastName, setLastName, displayName, setDisplayName,
    phone, setPhone, department, setDepartment,
    // email prefs
    newsletterEnabled, setNewsletterEnabled,
    meetingInvitesEnabled, setMeetingInvitesEnabled,
    digestFrequency, setDigestFrequency, savingPrefs,
    // permissions
    permInfo, permsOpen, setPermsOpen,
    // CalDAV
    caldav, setCaldav, caldavPw, setCaldavPw, savingCaldav, syncingCaldav,
    // iCal feed
    icalFeed, rotatingIcal,
    // DSGVO
    exporting, deleting, deleteConfirmText, setDeleteConfirmText,
    // push
    pushStatus, setPushStatus, repairing, setRepairing,
    // my feedback
    myFeedback, myFeedbackOpen, setMyFeedbackOpen,
    // handlers
    handleSave, handleSavePrefs, handleAvatarUpload,
    handleDataExport, handleAccountDelete,
    saveCaldav, syncCaldavNow, regenerateIcalFeed,
  };
}
