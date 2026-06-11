import { useState, useEffect } from 'react';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import api from '../../lib/api';
import { toast } from 'sonner';

import { useLanguage } from '../../contexts/LanguageContext';
export default function ReminderConfigPanel() {
  const { t } = useLanguage();
  const [config, setConfig] = useState({ default_minutes: 15, enabled: true });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/admin/reminder-config');
        setConfig(data);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put('/admin/reminder-config', config);
      setTimeout(() => toast.success('Erinnerungs-Konfiguration gespeichert'), 50);
    } catch {
      toast.error('Fehler beim Speichern');
    }
    setSaving(false);
  };

  if (loading) return <div className="text-center py-8 text-[#9CA3AF] text-sm">Laden...</div>;

  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 max-w-lg" data-testid="reminder-config-panel">
      <h3 className="text-sm font-medium text-[#1C1F1D] mb-4">{t('reminderSettings')}</h3>
      <p className="text-xs text-[#9CA3AF] mb-5">Konfigurieren Sie die Standard-Erinnerung für geplante Meetings. Erinnerungen werden per E-Mail an alle Teilnehmer und den Host gesendet.</p>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-[#1C1F1D]">{t('remindersEnabled')}</p>
            <p className="text-[10px] text-[#9CA3AF]">Automatische E-Mail-Erinnerungen vor Meetings</p>
          </div>
          <Switch checked={config.enabled !== false}
            onCheckedChange={(v) => setConfig(prev => ({ ...prev, enabled: v }))}
            data-testid="reminder-enabled-switch" />
        </div>

        <div>
          <Label className="text-xs text-[#6B7280] mb-1 block">Standard-Erinnerungszeit</Label>
          <Select value={String(config.default_minutes || 15)}
            onValueChange={v => setConfig(prev => ({ ...prev, default_minutes: parseInt(v) }))}>
            <SelectTrigger className="border-[#E2E4E0] rounded-xl" data-testid="reminder-default-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="5">5 Minuten vorher</SelectItem>
              <SelectItem value="10">10 Minuten vorher</SelectItem>
              <SelectItem value="15">15 Minuten vorher</SelectItem>
              <SelectItem value="30">30 Minuten vorher</SelectItem>
              <SelectItem value="60">1 Stunde vorher</SelectItem>
              <SelectItem value="1440">1 Tag vorher</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button onClick={save} disabled={saving}
          className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-xl text-sm"
          data-testid="save-reminder-config">
          {saving ? 'Speichern...' : 'Speichern'}
        </Button>
      </div>
    </div>
  );
}
