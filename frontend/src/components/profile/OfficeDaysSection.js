import { useState, useEffect } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Loader2, Save, Calendar, RefreshCw } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import SlackWebhookWizard from './SlackWebhookWizard';

/**
 * OfficeDaysSection (iter 241).
 * Standard-Bürotage-Konfiguration im Profil:
 *  - Wochentag-Checkboxes
 *  - Bevorzugter Arbeitsplatz (Dropdown)
 *  - Start-/Endzeit
 *  - Button "Buchungen jetzt erstellen" → POST /users/me/office-days/generate
 *  - Slack-Webhook + Wizard (iter 244/245)
 *  - Ad-hoc-Skip mit Reasons (iter 242/243/244)
 *
 * Backend: GET/PUT /api/users/me/office-days, POST /api/users/me/office-days/generate
 *
 * Extracted from /app/frontend/src/pages/ProfilePage.js (iter 247).
 */
export default function OfficeDaysSection({ language }) {
  const WEEKDAYS_DE = [
    { id: 'mon', label: 'Mo', full: 'Montag' },
    { id: 'tue', label: 'Di', full: 'Dienstag' },
    { id: 'wed', label: 'Mi', full: 'Mittwoch' },
    { id: 'thu', label: 'Do', full: 'Donnerstag' },
    { id: 'fri', label: 'Fr', full: 'Freitag' },
    { id: 'sat', label: 'Sa', full: 'Samstag' },
    { id: 'sun', label: 'So', full: 'Sonntag' },
  ];
  // Iter 243 — Skip-Reasons mit Emoji-Icons
  const SKIP_REASONS = [
    { id: 'krank', emoji: '🤒', label_de: 'Krank', label_en: 'Sick' },
    { id: 'homeoffice', emoji: '🏠', label_de: 'Homeoffice', label_en: 'Remote' },
    { id: 'urlaub', emoji: '🌴', label_de: 'Urlaub', label_en: 'Vacation' },
    { id: 'sonstiges', emoji: '❔', label_de: 'Sonstiges', label_en: 'Other' },
  ];

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [desks, setDesks] = useState([]);
  const [cfg, setCfg] = useState({
    weekdays: [], preferred_desk_id: '', start_time: '08:00', end_time: '17:00', title: 'Bürotag',
    announce_to_conversation_id: '', slack_webhook_url: '',
  });
  const [hasAccess, setHasAccess] = useState(true);
  const [slackConfigured, setSlackConfigured] = useState(false);
  // Iter 244 — Skip-Note state pro booking
  const [skipNote, setSkipNote] = useState({});
  // Iter 245 — Slack-Wizard + Test
  const [showSlackWizard, setShowSlackWizard] = useState(false);
  const [testingSlack, setTestingSlack] = useState(false);
  // Iter 242 — Ad-hoc-Skip: upcoming + conversations
  const [upcoming, setUpcoming] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [skipping, setSkipping] = useState(null);
  // Iter 243 — Skip-Reason-Popover state
  const [openSkipFor, setOpenSkipFor] = useState(null);

  const reloadUpcoming = () => {
    api.get('/users/me/office-days/upcoming')
      .then(r => setUpcoming(r.data.upcoming || []))
      .catch(() => setUpcoming([]));
  };

  useEffect(() => {
    Promise.all([
      api.get('/users/me/office-days').then(r => r.data).catch(() => null),
      api.get('/resources?type=desk&include_children=true').then(r => r.data).catch((e) => {
        if (e.response?.status === 403) setHasAccess(false);
        return [];
      }),
      api.get('/chat/conversations').then(r => r.data).catch(() => []),
    ]).then(([c, d, convs]) => {
      if (c) {
        setCfg({
          weekdays: c.weekdays || [],
          preferred_desk_id: c.preferred_desk_id || '',
          start_time: c.start_time || '08:00',
          end_time: c.end_time || '17:00',
          title: c.title || 'Bürotag',
          announce_to_conversation_id: c.announce_to_conversation_id || '',
          slack_webhook_url: '',  // never echoed back for privacy
        });
        setSlackConfigured(!!c.slack_webhook_configured);
      }
      setDesks(Array.isArray(d) ? d : []);
      // Nur Gruppen-Konversationen + benannte direkte Chats anbieten
      const list = Array.isArray(convs) ? convs : (convs?.conversations || []);
      setConversations(list.filter(cv => cv.type === 'group' || cv.name));
      reloadUpcoming();
    }).finally(() => setLoading(false));
  }, []);

  const toggleDay = (id) => {
    setCfg(prev => ({
      ...prev,
      weekdays: prev.weekdays.includes(id) ? prev.weekdays.filter(x => x !== id) : [...prev.weekdays, id],
    }));
  };

  const save = async () => {
    setSaving(true);
    try {
      const body = {
        weekdays: cfg.weekdays,
        preferred_desk_id: cfg.preferred_desk_id || null,
        start_time: cfg.start_time,
        end_time: cfg.end_time,
        title: cfg.title,
        announce_to_conversation_id: cfg.announce_to_conversation_id || null,
      };
      // Iter 244: nur senden wenn User eine NEUE URL eingegeben hat
      if (cfg.slack_webhook_url) {
        body.slack_webhook_url = cfg.slack_webhook_url;
      }
      await api.put('/users/me/office-days', body);
      // Reset input field
      setCfg(prev => ({ ...prev, slack_webhook_url: '' }));
      if (cfg.slack_webhook_url) setSlackConfigured(true);
      toast.success(language === 'de' ? 'Standard-Bürotage gespeichert' : 'Office days saved');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Speichern');
    } finally { setSaving(false); }
  };

  const clearSlack = async () => {
    try {
      await api.put('/users/me/office-days', {
        ...cfg,
        preferred_desk_id: cfg.preferred_desk_id || null,
        announce_to_conversation_id: cfg.announce_to_conversation_id || null,
        slack_webhook_url: '',
      });
      setSlackConfigured(false);
      toast.success(language === 'de' ? 'Slack-Webhook entfernt' : 'Slack webhook removed');
    } catch (e) {
      toast.error('Fehler');
    }
  };

  const testSlack = async () => {
    setTestingSlack(true);
    try {
      const { data } = await api.post('/users/me/office-days/slack/test');
      if (data.success) {
        toast.success(language === 'de' ? 'Slack-Verbindung erfolgreich' : 'Slack connection successful');
      } else {
        toast.error(
          language === 'de'
            ? `Slack-Test fehlgeschlagen: ${data.error || 'Unbekannter Fehler'}`
            : `Slack test failed: ${data.error || 'Unknown error'}`
        );
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Slack-Test');
    } finally { setTestingSlack(false); }
  };

  const generate = async () => {
    if (cfg.weekdays.length === 0) {
      toast.error(language === 'de' ? 'Bitte mindestens einen Wochentag wählen' : 'Pick at least one weekday');
      return;
    }
    if (!cfg.preferred_desk_id) {
      toast.error(language === 'de' ? 'Bitte bevorzugten Arbeitsplatz wählen' : 'Pick a preferred desk');
      return;
    }
    setGenerating(true);
    try {
      const { data } = await api.post('/users/me/office-days/generate', { weeks: 4 });
      const created = data.created_count || 0;
      const skippedOwned = (data.skipped_already_booked || []).length;
      const skippedConflict = (data.skipped_desk_conflict || []).length;
      const announced = data.announced;
      const slack = data.slack_notified;
      const channels = [
        announced && (language === 'de' ? 'Team-Chat' : 'team chat'),
        slack && 'Slack',
      ].filter(Boolean).join(' + ');
      toast.success(
        language === 'de'
          ? `${created} Buchungen erstellt · ${skippedOwned} bereits gebucht · ${skippedConflict} Konflikte${channels ? ` · ${channels} benachrichtigt` : ''}`
          : `${created} created · ${skippedOwned} existing · ${skippedConflict} conflicts${channels ? ` · ${channels} notified` : ''}`
      );
      reloadUpcoming();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler bei der Generierung');
    } finally { setGenerating(false); }
  };

  const skipDay = async (bookingId, reason) => {
    setSkipping(bookingId);
    try {
      await api.post('/users/me/office-days/skip', {
        booking_id: bookingId,
        reason: reason || null,
        note: skipNote[bookingId] || null,
      });
      const reasonLabel = SKIP_REASONS.find(r => r.id === reason)?.label_de;
      toast.success(
        language === 'de'
          ? (reason ? `Bürotag als "${reasonLabel}" markiert` : 'Bürotag gelöscht')
          : (reason ? `Office day marked as "${reasonLabel}"` : 'Office day deleted')
      );
      setUpcoming(prev => prev.filter(u => u.booking_id !== bookingId));
      setOpenSkipFor(null);
      setSkipNote(prev => { const { [bookingId]: _, ...rest } = prev; return rest; });
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Stornieren');
    } finally { setSkipping(null); }
  };

  if (loading) return null;
  if (!hasAccess) return null;  // User darf Ressourcen nicht sehen

  return (
    <div className="border border-[#E2E4E0] rounded-xl p-4 space-y-4" data-testid="office-days-block">
      <div className="flex items-center gap-2">
        <Calendar className="w-4 h-4 text-[#4A5D4E]" />
        <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280]">
          {language === 'de' ? 'Standard-Bürotage (Hybrid-Work)' : 'Recurring Office Days'}
        </Label>
      </div>
      <p className="text-xs text-[#9CA3AF] -mt-2">
        {language === 'de'
          ? 'Lege deine Wunsch-Bürotage fest und erstelle Desk-Buchungen für die nächsten 4 Wochen mit einem Klick.'
          : 'Pick your preferred office days and generate desk bookings for the next 4 weeks with one click.'}
      </p>

      {/* Wochentag-Chips */}
      <div className="flex flex-wrap gap-1.5" data-testid="office-days-weekdays">
        {WEEKDAYS_DE.map(w => {
          const active = cfg.weekdays.includes(w.id);
          return (
            <button
              key={w.id}
              type="button"
              onClick={() => toggleDay(w.id)}
              data-testid={`office-day-${w.id}`}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                active
                  ? 'bg-[#4A5D4E] text-white border-[#4A5D4E]'
                  : 'bg-white text-[#4B5563] border-[#E2E4E0] hover:border-[#4A5D4E]'
              }`}
              title={w.full}
            >
              {w.label}
            </button>
          );
        })}
      </div>

      {/* Desk-Selector */}
      <div>
        <Label className="text-xs text-[#6B7280] block mb-1">
          {language === 'de' ? 'Bevorzugter Arbeitsplatz' : 'Preferred desk'}
        </Label>
        <Select value={cfg.preferred_desk_id || 'none'}
          onValueChange={(v) => setCfg(prev => ({ ...prev, preferred_desk_id: v === 'none' ? '' : v }))}>
          <SelectTrigger className="h-9" data-testid="office-day-desk-select">
            <SelectValue placeholder={language === 'de' ? 'Arbeitsplatz wählen' : 'Pick a desk'} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">— {language === 'de' ? 'Keiner' : 'None'} —</SelectItem>
            {desks.map(d => (
              <SelectItem key={d.resource_id} value={d.resource_id}>
                {d.name}{d.desk_number ? ` · ${d.desk_number}` : ''}{d.floor ? ` · ${d.floor}` : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Zeit-Inputs */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs text-[#6B7280] block mb-1">
            {language === 'de' ? 'Von' : 'From'}
          </Label>
          <Input type="time" value={cfg.start_time}
            onChange={(e) => setCfg(prev => ({ ...prev, start_time: e.target.value }))}
            className="h-9" data-testid="office-day-start-time" />
        </div>
        <div>
          <Label className="text-xs text-[#6B7280] block mb-1">
            {language === 'de' ? 'Bis' : 'To'}
          </Label>
          <Input type="time" value={cfg.end_time}
            onChange={(e) => setCfg(prev => ({ ...prev, end_time: e.target.value }))}
            className="h-9" data-testid="office-day-end-time" />
        </div>
      </div>

      {/* Optional: Team-Chat-Auswahl für Auto-Announce (iter 242) */}
      {conversations.length > 0 && (
        <div>
          <Label className="text-xs text-[#6B7280] block mb-1">
            {language === 'de' ? 'Team benachrichtigen in Chat (optional)' : 'Notify team in chat (optional)'}
          </Label>
          <Select value={cfg.announce_to_conversation_id || 'none'}
            onValueChange={(v) => setCfg(prev => ({ ...prev, announce_to_conversation_id: v === 'none' ? '' : v }))}>
            <SelectTrigger className="h-9" data-testid="office-day-conv-select">
              <SelectValue placeholder={language === 'de' ? 'Kein Chat — keine Benachrichtigung' : 'No chat'} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">— {language === 'de' ? 'Keine Benachrichtigung' : 'No notification'} —</SelectItem>
              {conversations.map(c => (
                <SelectItem key={c.conversation_id} value={c.conversation_id}>
                  {c.name || (language === 'de' ? 'Unbenannt' : 'Untitled')}
                  {c.type === 'group' ? ' (Gruppe)' : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Iter 244 — Slack Webhook (optional, extern) — Iter 245 mit Wizard */}
      <div data-testid="office-day-slack-block">
        <Label className="text-xs text-[#6B7280] block mb-1">
          {language === 'de' ? 'Slack-Webhook URL (optional, extern)' : 'Slack webhook URL (optional, external)'}
        </Label>
        {slackConfigured ? (
          <div className="flex items-center gap-2">
            <div className="flex-1 h-9 px-3 text-xs text-[#4A5D4E] bg-[#F3F4F1] rounded-md flex items-center"
              data-testid="office-day-slack-status">
              <span className="mr-2">✓</span>
              {language === 'de' ? 'Slack-Webhook konfiguriert' : 'Slack webhook configured'}
            </div>
            <Button size="sm" variant="outline" onClick={testSlack} disabled={testingSlack}
              data-testid="office-day-slack-test"
              className="h-9 text-xs">
              {testingSlack ? '...' : (language === 'de' ? 'Testen' : 'Test')}
            </Button>
            <Button size="sm" variant="outline" onClick={clearSlack}
              data-testid="office-day-slack-clear"
              className="h-9 text-xs">
              {language === 'de' ? 'Entfernen' : 'Remove'}
            </Button>
          </div>
        ) : (
          <Input
            value={cfg.slack_webhook_url}
            onChange={(e) => setCfg(prev => ({ ...prev, slack_webhook_url: e.target.value }))}
            placeholder="https://hooks.slack.com/services/T0/B0/XXX"
            type="url"
            className="h-9 text-xs"
            data-testid="office-day-slack-input"
          />
        )}
        <div className="flex items-center justify-between mt-1">
          <p className="text-[10px] text-[#9CA3AF]">
            {language === 'de'
              ? 'Optional. Wird beim "Buchungen erstellen" mit benachrichtigt.'
              : 'Optional. Notified on "Generate bookings".'}
          </p>
          <button type="button" onClick={() => setShowSlackWizard(v => !v)}
            data-testid="office-day-slack-wizard-toggle"
            className="text-[10px] text-[#4A5D4E] hover:underline flex items-center gap-0.5">
            {showSlackWizard ? '▾' : '▸'} {language === 'de' ? 'Anleitung anzeigen' : 'Show setup guide'}
          </button>
        </div>
        {showSlackWizard && <SlackWebhookWizard language={language} />}
      </div>

      <div className="flex flex-col sm:flex-row gap-2 pt-2">
        <Button onClick={save} disabled={saving}
          variant="outline" className="w-full sm:flex-1"
          data-testid="office-days-save-btn">
          {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />}
          {language === 'de' ? 'Speichern' : 'Save'}
        </Button>
        <Button onClick={generate} disabled={generating || cfg.weekdays.length === 0 || !cfg.preferred_desk_id}
          className="w-full sm:flex-1 bg-[#4A5D4E] hover:bg-[#3E4F40] text-white"
          data-testid="office-days-generate-btn">
          {generating ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <RefreshCw className="w-4 h-4 mr-2" />}
          {language === 'de' ? 'Buchungen erstellen' : 'Generate bookings'}
        </Button>
      </div>

      {/* Iter 242 — Ad-hoc-Skip: Liste der kommenden auto-generierten Tage */}
      {upcoming.length > 0 && (
        <div className="border-t border-[#E2E4E0] pt-3" data-testid="office-days-upcoming">
          <Label className="text-[10px] uppercase tracking-wider font-bold text-[#6B7280] block mb-2">
            {language === 'de' ? 'Kommende Bürotage' : 'Upcoming office days'} ({upcoming.length})
          </Label>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {upcoming.map(u => {
              const d = new Date(u.start_at);
              const isOpen = openSkipFor === u.booking_id;
              return (
                <div key={u.booking_id}
                  data-testid={`office-day-upcoming-${u.booking_id}`}>
                  <div className="flex items-center justify-between gap-2 px-2 py-1.5 rounded bg-[#F9F9F8] text-xs">
                    <div className="flex-1 min-w-0 truncate">
                      <span className="font-medium">
                        {d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })}
                      </span>
                      <span className="text-[#6B7280] ml-2 truncate">
                        {u.desk_number}{u.floor ? ` · ${u.floor}` : ''}
                      </span>
                    </div>
                    <Button size="sm" variant="ghost" disabled={skipping === u.booking_id}
                      onClick={() => setOpenSkipFor(isOpen ? null : u.booking_id)}
                      data-testid={`office-day-skip-${u.booking_id}`}
                      className="shrink-0 h-6 px-2 text-[10px] hover:text-[#C87967] hover:bg-rose-50">
                      {skipping === u.booking_id
                        ? '...'
                        : (language === 'de' ? 'überspringen' : 'skip')}
                    </Button>
                  </div>
                  {isOpen && (
                    <div className="mt-1 mb-2 px-2 py-2 bg-white border border-[#E2E4E0] rounded-lg space-y-2"
                      data-testid={`office-day-skip-reasons-${u.booking_id}`}>
                      <div className="text-[10px] text-[#6B7280]">
                        {language === 'de' ? 'Grund auswählen (für Team-Transparenz):' : 'Pick reason (for team transparency):'}
                      </div>
                      <Input
                        value={skipNote[u.booking_id] || ''}
                        onChange={e => setSkipNote(prev => ({ ...prev, [u.booking_id]: e.target.value }))}
                        placeholder={language === 'de' ? 'Notiz (optional) z.B. „bis Mittwoch"' : 'Note (optional)'}
                        className="h-7 text-[11px]"
                        data-testid={`skip-note-${u.booking_id}`}
                      />
                      <div className="flex flex-wrap gap-1">
                        {SKIP_REASONS.map(r => (
                          <Button key={r.id} size="sm" variant="outline"
                            onClick={() => skipDay(u.booking_id, r.id)}
                            disabled={skipping === u.booking_id}
                            data-testid={`skip-reason-${r.id}-${u.booking_id}`}
                            className="h-7 text-[11px] px-2">
                            <span className="mr-1">{r.emoji}</span>{language === 'de' ? r.label_de : r.label_en}
                          </Button>
                        ))}
                        <Button size="sm" variant="ghost"
                          onClick={() => skipDay(u.booking_id, null)}
                          disabled={skipping === u.booking_id}
                          data-testid={`skip-reason-none-${u.booking_id}`}
                          className="h-7 text-[10px] px-2 text-[#9CA3AF] hover:text-[#C87967]">
                          {language === 'de' ? 'Ohne Grund · löschen' : 'No reason · delete'}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
