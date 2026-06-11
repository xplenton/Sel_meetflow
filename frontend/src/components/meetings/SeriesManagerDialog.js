import { useState, useEffect, useCallback } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { CalendarDays, CalendarPlus, Repeat, Trash2 } from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { useLanguage } from '../../contexts/LanguageContext';

/**
 * SeriesManagerDialog — manages a recurring meeting series: list of
 * occurrences (cancel/restore individual ones) and bulk edit of meeting
 * settings across the whole series. Extracted from MeetingsPage during
 * the iter 217 refactor.
 */
export default function SeriesManagerDialog({ open, onClose, seriesId, title }) {
  const { t } = useLanguage();
  const [occurrences, setOccurrences] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [bulk, setBulk] = useState({
    lobby_enabled: null, guest_access: null, chat_enabled: null,
    reactions_enabled: null, recording_enabled: null, transcript_enabled: null,
  });
  const [scope, setScope] = useState('upcoming');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/meetings/recurring/${seriesId}`);
      setOccurrences(data || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [seriesId]);

  useEffect(() => {
    if (open) {
      setBulk({
        lobby_enabled: null, guest_access: null, chat_enabled: null,
        reactions_enabled: null, recording_enabled: null, transcript_enabled: null,
      });
      load();
    }
  }, [open, load]);

  const applyBulk = async () => {
    const updates = Object.fromEntries(Object.entries(bulk).filter(([, v]) => v !== null));
    if (Object.keys(updates).length === 0) { toast.error('Keine Änderungen ausgewählt'); return; }
    setSaving(true);
    try {
      const { data } = await api.patch(`/meetings/series/${seriesId}`, { ...updates, scope });
      toast.success(`${data.updated} Meetings aktualisiert`);
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
    finally { setSaving(false); }
  };

  const deleteSeries = async () => {
    if (!window.confirm(`Alle ${scope === 'all' ? '' : 'zukünftigen '}Meetings der Serie löschen?`)) return;
    setSaving(true);
    try {
      const { data } = await api.delete(`/meetings/series/${seriesId}?scope=${scope}`);
      toast.success(`${data.deleted} Meetings gelöscht`);
      onClose();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
    finally { setSaving(false); }
  };

  const cancelOccurrence = async (occMeetingId, index) => {
    if (!window.confirm(`Einzeltermin #${index} absagen? Der Termin wird als 'abgesagt' markiert und bleibt im Verlauf erhalten (wiederherstellbar).`)) return;
    try {
      await api.delete(`/meetings/${occMeetingId}?soft=true`);
      toast.success(`Termin #${index} abgesagt`);
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };

  const restoreOccurrence = async (occMeetingId, index) => {
    try {
      await api.post(`/meetings/${occMeetingId}/restore`);
      toast.success(`Termin #${index} wiederhergestellt`);
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler'); }
  };

  const fmt = (iso) => iso ? new Date(iso).toLocaleString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-';
  const statusBg = {
    scheduled: 'bg-[#4A5D4E]/10 text-[#4A5D4E]',
    active: 'bg-[#E25C5C]/10 text-[#E25C5C]',
    ended: 'bg-[#9CA3AF]/10 text-[#9CA3AF]',
    cancelled: 'bg-[#C87967]/10 text-[#C87967] line-through',
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[560px] max-h-[92vh] overflow-y-auto w-[calc(100vw-1rem)] p-4 sm:p-6" data-testid="series-manager-dialog">
        <DialogHeader>
          <DialogTitle className="text-base font-medium flex items-center gap-2">
            <CalendarDays className="w-4 h-4 text-[#D4A373]" /> Serie verwalten — {title}
          </DialogTitle>
        </DialogHeader>

        <div className="mt-2">
          <h3 className="text-[10px] uppercase tracking-wider font-bold text-[#6B7280] mb-2">Serientermine ({occurrences.length})</h3>
          {loading ? (
            <p className="text-xs text-[#9CA3AF]">Lade...</p>
          ) : (
            <div className="space-y-1 max-h-48 overflow-y-auto border border-[#E2E4E0] rounded-lg p-2 bg-[#F9F9F8]">
              {occurrences.map((occ, i) => (
                <div key={occ.meeting_id} className="flex items-center justify-between gap-2 text-xs py-1 group" data-testid={`series-occ-${i}`}>
                  <span className={`truncate flex-1 ${occ.status === 'cancelled' ? 'text-[#9CA3AF] line-through' : 'text-[#4B5563]'}`}>
                    #{i + 1} {fmt(occ.scheduled_at)} · {occ.duration}min
                  </span>
                  <Badge className={`text-[9px] px-1.5 py-0 ${statusBg[occ.status] || ''}`}>{occ.status}</Badge>
                  {occ.status === 'cancelled' && (
                    <button
                      onClick={() => restoreOccurrence(occ.meeting_id, i + 1)}
                      className="p-1 rounded hover:bg-[#6B8E23]/10 text-[#9CA3AF] hover:text-[#6B8E23]"
                      title={t('restoreOccurrence')}
                      data-testid={`restore-occ-${i}`}
                    >
                      <Repeat className="w-3 h-3" />
                    </button>
                  )}
                  {occ.status !== 'ended' && occ.status !== 'cancelled' && (
                    <button
                      onClick={() => cancelOccurrence(occ.meeting_id, i + 1)}
                      className="p-1 rounded hover:bg-[#C87967]/10 text-[#9CA3AF] hover:text-[#C87967] opacity-60 group-hover:opacity-100 transition-opacity"
                      title={t('cancelOccurrenceHint')}
                      data-testid={`cancel-occ-${i}`}
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                </div>
              ))}
              {occurrences.length === 0 && <p className="text-xs text-[#9CA3AF] text-center py-2">{t('noAppointments')}</p>}
            </div>
          )}
        </div>

        <div className="mt-4 bg-white border border-[#E2E4E0] rounded-xl p-3 space-y-3">
          <h3 className="text-[10px] uppercase tracking-wider font-bold text-[#6B7280]">{t('bulkChanges')}</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {[
              ['lobby_enabled', 'Lobby'],
              ['guest_access', 'Gast-Zugang'],
              ['chat_enabled', 'Chat'],
              ['reactions_enabled', 'Reaktionen'],
              ['recording_enabled', 'Aufnahme'],
              ['transcript_enabled', 'Transkript'],
            ].map(([key, label]) => (
              <div key={key} className="flex items-center gap-1.5 text-xs" data-testid={`bulk-${key}`}>
                <span className="text-[#4B5563] flex-1 truncate">{label}</span>
                <select
                  value={bulk[key] === null ? '' : String(bulk[key])}
                  onChange={e => setBulk(b => ({ ...b, [key]: e.target.value === '' ? null : e.target.value === 'true' }))}
                  className="text-[10px] border border-[#E2E4E0] rounded px-1.5 py-0.5 bg-white">
                  <option value="">—</option>
                  <option value="true">An</option>
                  <option value="false">Aus</option>
                </select>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1">
            <span className="text-[10px] text-[#6B7280] w-full sm:w-auto">Anwenden auf:</span>
            <label className="flex items-center gap-1 text-xs">
              <input type="radio" checked={scope === 'upcoming'} onChange={() => setScope('upcoming')} data-testid="scope-upcoming" /> {t('futureOccurrences')}
            </label>
            <label className="flex items-center gap-1 text-xs">
              <input type="radio" checked={scope === 'all'} onChange={() => setScope('all')} data-testid="scope-all" /> Alle
            </label>
          </div>
        </div>

        <DialogFooter className="gap-2 flex-col sm:flex-row mt-3">
          <Button variant="outline" onClick={deleteSeries} disabled={saving}
            className="rounded-full border-[#C87967]/40 text-[#C87967] hover:bg-[#C87967]/10 w-full sm:w-auto" data-testid="delete-series-btn">
            <Trash2 className="w-3.5 h-3.5 mr-1" /> Serie löschen
          </Button>
          <Button variant="outline" onClick={() => window.open(`${process.env.REACT_APP_BACKEND_URL}/api/meetings/series/${seriesId}/ical`, '_blank')}
            className="rounded-full border-[#E2E4E0] text-[#6B8E23] w-full sm:w-auto" data-testid="series-ical-btn">
            <CalendarPlus className="w-3.5 h-3.5 mr-1" /> {t('allAsIcs')}
          </Button>
          <div className="flex-1" />
          <Button variant="outline" onClick={onClose} className="rounded-full border-[#E2E4E0] w-full sm:w-auto">{t('close')}</Button>
          <Button onClick={applyBulk} disabled={saving}
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full w-full sm:w-auto" data-testid="apply-bulk-btn">
            {saving ? '...' : 'Übernehmen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
