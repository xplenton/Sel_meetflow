import { useEffect, useState } from 'react';
import { Mail, Smartphone, Moon, Loader2 } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

const CATEGORY_LABELS = {
  news:     { de: 'News',        en: 'News' },
  meetings: { de: 'Meetings',    en: 'Meetings' },
  surveys:  { de: 'Umfragen',    en: 'Surveys' },
  chat:     { de: 'Chat',        en: 'Chat' },
  feedback: { de: 'Feedback',    en: 'Feedback' },
};

const CATEGORY_HINTS = {
  news:     'Neue News-Beiträge in deinen Zielgruppen',
  meetings: 'Meeting-Einladungen, Reminder, Änderungen',
  surveys:  'Neue Umfragen und Feedback-Formulare',
  chat:     'Neue Chat-Nachrichten (Anrufe & Dringendes ignorieren diese Einstellung)',
  feedback: 'Admin-Antworten auf dein Feedback',
};

function ToggleCell({ checked, onChange, testId, disabled }) {
  return (
    <label className="inline-flex items-center cursor-pointer select-none" data-testid={testId}>
      <input type="checkbox" className="sr-only peer" checked={checked} onChange={(e) => onChange(e.target.checked)} disabled={disabled} />
      <div className={`w-9 h-5 rounded-full transition-colors ${checked ? 'bg-[#4A5D4E]' : 'bg-[#E2E4E0]'} ${disabled ? 'opacity-50' : ''}`}>
        <div className={`w-4 h-4 bg-white rounded-full shadow transform transition-transform mt-0.5 ${checked ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
      </div>
    </label>
  );
}

export default function NotificationPrefsSection({ language = 'de' }) {
  const [prefs, setPrefs] = useState(null);
  const [quiet, setQuiet] = useState({ enabled: false, start: '22:00', end: '07:00' });
  const [checkinMin, setCheckinMin] = useState(15);
  const [checkoutEnabled, setCheckoutEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/users/me/notification-prefs');
        setPrefs(data.prefs);
        setQuiet(data.quiet_hours);
        if (data.checkin_reminder_minutes != null) setCheckinMin(data.checkin_reminder_minutes);
        if (data.checkout_reminder_enabled != null) setCheckoutEnabled(data.checkout_reminder_enabled);
      } catch {
        // silent — profile still works without this panel
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const patch = async (payload) => {
    setSaving(true);
    try {
      const { data } = await api.put('/users/me/notification-prefs', payload);
      setPrefs(data.prefs);
      setQuiet(data.quiet_hours);
      if (data.checkin_reminder_minutes != null) setCheckinMin(data.checkin_reminder_minutes);
      if (data.checkout_reminder_enabled != null) setCheckoutEnabled(data.checkout_reminder_enabled);
    } catch {
      toast.error(language === 'de' ? 'Speichern fehlgeschlagen' : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const updateChannel = (cat, channel, value) => {
    setPrefs((p) => ({ ...p, [cat]: { ...p[cat], [channel]: value } }));
    patch({ prefs: { [cat]: { [channel]: value } } });
  };

  const updateQuiet = (next) => {
    setQuiet(next);
    patch({ quiet_hours: next });
  };

  const updateCheckinMin = (v) => {
    const n = Math.max(0, Math.min(240, Number(v) || 0));
    setCheckinMin(n);
    patch({ checkin_reminder_minutes: n });
  };

  const updateCheckoutEnabled = (v) => {
    setCheckoutEnabled(v);
    patch({ checkout_reminder_enabled: v });
  };

  if (loading) return null;
  if (!prefs) return null;

  return (
    <section className="bg-white border border-[#E2E4E0] rounded-2xl p-5" data-testid="notification-prefs-section">
      <div className="flex items-center gap-2 mb-4">
        <h3 className="text-[13px] font-bold text-[#1C1F1D]">
          {language === 'de' ? 'Benachrichtigungen pro Kategorie' : 'Notification preferences'}
        </h3>
        {saving && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#9CA3AF]" />}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="notification-prefs-table">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-[#9CA3AF]">
              <th className="text-left pb-2 font-medium">{language === 'de' ? 'Kategorie' : 'Category'}</th>
              <th className="text-center pb-2 font-medium w-16">
                <span className="inline-flex items-center gap-1"><Mail className="w-3 h-3" /> E-Mail</span>
              </th>
              <th className="text-center pb-2 font-medium w-16">
                <span className="inline-flex items-center gap-1"><Smartphone className="w-3 h-3" /> Push</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {Object.keys(CATEGORY_LABELS).map((cat) => {
              const p = prefs[cat] || { email: true, push: true };
              return (
                <tr key={cat} className="border-t border-[#F3F4F1]" data-testid={`notification-prefs-row-${cat}`}>
                  <td className="py-3 pr-2">
                    <div className="text-sm text-[#1C1F1D]">{CATEGORY_LABELS[cat][language] || CATEGORY_LABELS[cat].de}</div>
                    <div className="text-[10px] text-[#9CA3AF] leading-tight mt-0.5">{CATEGORY_HINTS[cat]}</div>
                  </td>
                  <td className="py-3 text-center">
                    <ToggleCell checked={p.email} onChange={(v) => updateChannel(cat, 'email', v)} testId={`pref-${cat}-email`} />
                  </td>
                  <td className="py-3 text-center">
                    <ToggleCell checked={p.push} onChange={(v) => updateChannel(cat, 'push', v)} testId={`pref-${cat}-push`} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-5 pt-4 border-t border-[#F3F4F1]">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Moon className="w-4 h-4 text-[#4A5D4E]" />
            <div>
              <div className="text-sm font-medium text-[#1C1F1D]">{language === 'de' ? 'Ruhezeiten für Push' : 'Quiet hours (push)'}</div>
              <div className="text-[10px] text-[#9CA3AF]">
                {language === 'de'
                  ? 'In diesem Zeitfenster werden Push-Benachrichtigungen unterdrückt (Anrufe & Notfälle nicht).'
                  : 'Push notifications are suppressed within this window (calls & emergencies excluded).'}
              </div>
            </div>
          </div>
          <ToggleCell checked={quiet.enabled} onChange={(v) => updateQuiet({ ...quiet, enabled: v })} testId="pref-quiet-enabled" />
        </div>
        {quiet.enabled && (
          <div className="flex items-center gap-3 mt-3 pl-6">
            <div>
              <label className="text-[10px] text-[#9CA3AF] uppercase tracking-wider block mb-1">{language === 'de' ? 'Von' : 'From'}</label>
              <input type="time" value={quiet.start} onChange={(e) => updateQuiet({ ...quiet, start: e.target.value })}
                className="border border-[#E2E4E0] rounded-lg px-2 py-1 text-sm" data-testid="pref-quiet-start" />
            </div>
            <div>
              <label className="text-[10px] text-[#9CA3AF] uppercase tracking-wider block mb-1">{language === 'de' ? 'Bis' : 'To'}</label>
              <input type="time" value={quiet.end} onChange={(e) => updateQuiet({ ...quiet, end: e.target.value })}
                className="border border-[#E2E4E0] rounded-lg px-2 py-1 text-sm" data-testid="pref-quiet-end" />
            </div>
          </div>
        )}
      </div>

      {/* Iter 283 — Ressourcen-Buchungs-Erinnerungen */}
      <div className="mt-5 pt-4 border-t border-[#F3F4F1]" data-testid="checkin-reminder-config">
        <div className="text-sm font-medium text-[#1C1F1D] mb-1">
          {language === 'de' ? 'Check-in / Check-out Erinnerungen' : 'Check-in / Check-out reminders'}
        </div>
        <div className="text-[10px] text-[#9CA3AF] mb-3">
          {language === 'de'
            ? 'Für Buchungen von Räumen, Arbeitsplätzen und Fahrzeugen.'
            : 'For room, desk and vehicle bookings.'}
        </div>

        <div className="flex items-center justify-between gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <label className="text-sm text-[#1C1F1D]">
              {language === 'de' ? 'Check-in-Erinnerung (Minuten vor Beginn)' : 'Check-in reminder (minutes before start)'}
            </label>
            <div className="text-[10px] text-[#9CA3AF]">
              {language === 'de'
                ? '0 = keine Erinnerung. Maximum 240 Minuten.'
                : '0 = disabled. Max 240 minutes.'}
            </div>
          </div>
          <input
            type="number"
            min="0"
            max="240"
            step="5"
            value={checkinMin}
            onChange={(e) => updateCheckinMin(e.target.value)}
            className="w-20 border border-[#E2E4E0] rounded-lg px-2 py-1 text-sm text-right"
            data-testid="pref-checkin-reminder-minutes"
          />
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <label className="text-sm text-[#1C1F1D]">
              {language === 'de' ? 'Check-out-Erinnerung nach Buchungsende' : 'Check-out reminder after booking ends'}
            </label>
            <div className="text-[10px] text-[#9CA3AF]">
              {language === 'de'
                ? 'Push wenn die Buchung endet, aber noch nicht ausgecheckt wurde.'
                : 'Push when booking ends without check-out.'}
            </div>
          </div>
          <ToggleCell checked={checkoutEnabled} onChange={updateCheckoutEnabled} testId="pref-checkout-reminder-enabled" />
        </div>
      </div>
    </section>
  );
}
