import { copyToClipboard } from '../../lib/clipboard';
import { useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { DateTimeInput, parseDateTime, combineDateTime } from '../DateTimeInput';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '../ui/dropdown-menu';
import {
  Video, Clock, Users, ArrowRight, Copy, Sparkles, Mail, Repeat, MoreVertical,
  Pencil, Trash2, Link2, MessageCircle, Send, CalendarPlus, ClipboardList,
  CalendarDays, BellRing, FileDown,
} from 'lucide-react';
import api from '../../lib/api';
import { toast } from 'sonner';
import ReachabilityPopover from './ReachabilityPopover';
import SeriesManagerDialog from './SeriesManagerDialog';

/**
 * MeetingRow — single meeting in the meetings list, with status badges,
 * quick actions (copy link/code, join, ring, calendar export), edit/delete
 * dialogs and an inline series-manager. Extracted from MeetingsPage during
 * the iter 217 refactor.
 */
export default function MeetingRow({ meeting, t, formatDate, statusColor, navigate, onRefresh }) {
  const { user } = useAuth();
  const m = meeting;
  const isHost = user?.user_id && m.host_id === user.user_id;
  const canRing = isHost && (m.status === 'scheduled' || m.status === 'active');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [seriesOpen, setSeriesOpen] = useState(false);
  const [editTitle, setEditTitle] = useState(m.title);
  const [editDesc, setEditDesc] = useState(m.description || '');
  const [editDate, setEditDate] = useState(m.scheduled_at ? m.scheduled_at.slice(0, 16) : '');
  const [editAutoRering, setEditAutoRering] = useState(!!m.auto_rering);
  const [saving, setSaving] = useState(false);

  const joinLink = `${window.location.origin}/meetings/${m.meeting_id}/join`;

  const copyLink = () => {
    copyToClipboard(joinLink);
    toast.success('Meeting-Link kopiert!');
  };

  const copyCode = () => {
    copyToClipboard(m.meeting_code);
    toast.success('Code kopiert!');
  };

  const shareWhatsApp = () => {
    const text = `Nimm an meinem Meeting teil: ${m.title}\n${joinLink}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank');
  };

  const shareEmail = () => {
    const subject = `Einladung: ${m.title}`;
    const body = `Hallo,\n\nich lade dich zu folgendem Meeting ein:\n\n${m.title}${m.scheduled_at ? `\nDatum: ${new Date(m.scheduled_at).toLocaleString('de-DE', { dateStyle: 'long', timeStyle: 'short' })}` : ''}\n\nBeitreten: ${joinLink}\nMeeting-Code: ${m.meeting_code}\n\nBis bald!`;
    window.open(`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`);
  };

  const handleEdit = async () => {
    setSaving(true);
    try {
      await api.put(`/meetings/${m.meeting_id}`, {
        title: editTitle, description: editDesc,
        scheduled_at: editDate || null,
        auto_rering: editAutoRering,
      });
      toast.success('Meeting aktualisiert');
      setEditOpen(false);
      onRefresh?.();
    } catch { toast.error('Fehler beim Aktualisieren'); }
    finally { setSaving(false); }
  };

  const handleDelete = async () => {
    try {
      await api.delete(`/meetings/${m.meeting_id}`);
      toast.success('Meeting gelöscht');
      setDeleteOpen(false);
      onRefresh?.();
    } catch { toast.error('Fehler beim Löschen'); }
  };

  const handleRing = async () => {
    try {
      const { data } = await api.post(`/meetings/${m.meeting_id}/ring`);
      if (data.rang > 0) toast.success(`Klingelt bei ${data.rang} Teilnehmer${data.rang === 1 ? '' : 'n'}`);
      else toast.info('Keine abwesenden Teilnehmer zu benachrichtigen');
    } catch (err) { toast.error(err.response?.data?.detail || 'Klingeln fehlgeschlagen'); }
  };

  return (
    <>
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-4 flex flex-wrap items-center gap-3 sm:gap-4 hover:border-[#4A5D4E]/30 transition-colors"
        data-testid={`meeting-row-${m.meeting_id}`}>
        <div className="w-10 h-10 rounded-lg bg-[#4A5D4E]/8 flex items-center justify-center flex-shrink-0">
          <Video className="w-5 h-5 text-[#4A5D4E]" />
        </div>
        <div className="flex-1 min-w-0 basis-[calc(100%-56px)] sm:basis-auto">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <h3 className="font-medium text-[#1C1F1D] text-sm truncate">{m.title}</h3>
            <Badge className={`text-[10px] px-2 py-0 ${statusColor[m.status] || ''}`}>{t(m.status)}</Badge>
            {m.status === 'active' && <span className="w-2 h-2 rounded-full bg-[#E25C5C] pulse-live" />}
            {m.recurring && (
              <Badge
                className="text-[10px] bg-[#D4A373]/10 text-[#D4A373] px-1.5 py-0 cursor-pointer"
                onClick={() => setSeriesOpen(true)}
                data-testid={`series-badge-${m.meeting_id}`}
                title={m.series_id ? 'Serie verwalten' : (m.recurring_pattern || 'recurring')}
              >
                <Repeat className="w-2.5 h-2.5 mr-0.5" />
                {m.series_id && m.series_index && m.series_total
                  ? `Serie ${m.series_index}/${m.series_total}`
                  : (m.recurring_pattern || 'recurring')}
              </Badge>
            )}
            {m.meeting_mode && m.meeting_mode !== 'standard' && <Badge className="text-[10px] bg-[#4A5D4E]/10 text-[#4A5D4E] px-1.5 py-0 capitalize">{m.meeting_mode}</Badge>}
            {m.auto_rering && (m.status === 'scheduled' || m.status === 'active') && (
              <Badge className="text-[10px] bg-[#D4A373]/10 text-[#D4A373] px-1.5 py-0" title="Auto-Nachklingeln aktiv"
                data-testid={`auto-rering-badge-${m.meeting_id}`}>
                <BellRing className="w-2.5 h-2.5 mr-0.5" />Auto
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-[#9CA3AF]">
            {m.scheduled_at && <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{formatDate(m.scheduled_at)}</span>}
            <span className="flex items-center gap-1"><Users className="w-3 h-3" />{m.participant_count || 0}</span>
            <span className="flex items-center gap-1 cursor-pointer hover:text-[#4A5D4E]" onClick={copyCode}><Copy className="w-3 h-3" />{m.meeting_code}</span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap ml-auto">
          <Button size="sm" variant="ghost" onClick={copyLink} data-testid={`copy-link-${m.meeting_id}`}
            className="text-[#9CA3AF] hover:text-[#4A5D4E] h-8 w-8 p-0" title="Link kopieren">
            <Link2 className="w-4 h-4" />
          </Button>

          {m.status === 'ended' && (
            <>
              <Button size="sm" variant="ghost" data-testid={`summary-${m.meeting_id}`}
                onClick={() => navigate(`/meetings/${m.meeting_id}/summary`)}
                className="text-[#4A5D4E] text-xs h-8 px-2"><Sparkles className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">{t('summary')}</span></Button>
              <Button size="sm" variant="ghost" data-testid={`attendance-${m.meeting_id}`}
                onClick={() => navigate(`/meetings/${m.meeting_id}/attendance`)}
                className="text-[#4A5D4E] text-xs h-8 px-2"><ClipboardList className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">Anwesenheit</span></Button>
              <Button size="sm" variant="ghost" data-testid={`export-csv-${m.meeting_id}`}
                onClick={() => { window.open(`${process.env.REACT_APP_BACKEND_URL}/api/meetings/${m.meeting_id}/report/csv`, '_blank'); }}
                className="text-[#9CA3AF] text-xs hover:text-[#4A5D4E] h-8 w-8 p-0"><FileDown className="w-3.5 h-3.5" /></Button>
            </>
          )}
          {(m.status === 'active' || m.status === 'scheduled') && (
            <>
              {canRing && <ReachabilityPopover meetingId={m.meeting_id} meeting={m} />}
              {canRing && (
                <Button size="sm" variant="ghost" data-testid={`ring-${m.meeting_id}`}
                  onClick={handleRing}
                  className="text-[#D4A373] hover:text-[#B8875C] hover:bg-[#D4A373]/10 text-xs h-8 px-2"
                  title="Abwesende Teilnehmer anklingeln">
                  <BellRing className="w-3.5 h-3.5 sm:mr-1" /><span className="hidden sm:inline">Klingeln</span>
                </Button>
              )}
              <Button size="sm" variant="ghost" data-testid={`attendance-${m.meeting_id}`}
                onClick={() => navigate(`/meetings/${m.meeting_id}/attendance`)}
                className="text-[#9CA3AF] text-xs hover:text-[#4A5D4E]"><ClipboardList className="w-3.5 h-3.5" /></Button>
              <Button size="sm" data-testid={`join-${m.meeting_id}`}
                onClick={() => navigate(`/meetings/${m.meeting_id}/join`)}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-xs h-8 px-4">
                {t('join')} <ArrowRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            </>
          )}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="p-1.5 rounded-lg hover:bg-[#F3F4F1] text-[#9CA3AF]" data-testid={`menu-${m.meeting_id}`}>
                <MoreVertical className="w-4 h-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[200px]">
              <DropdownMenuItem onClick={copyLink} data-testid={`menu-copy-link-${m.meeting_id}`}>
                <Link2 className="w-3.5 h-3.5 mr-2" /> Link kopieren
              </DropdownMenuItem>
              <DropdownMenuItem onClick={copyCode}>
                <Copy className="w-3.5 h-3.5 mr-2" /> Code kopieren
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={shareWhatsApp} data-testid={`menu-share-whatsapp-${m.meeting_id}`}>
                <MessageCircle className="w-3.5 h-3.5 mr-2 text-[#25D366]" /> Per WhatsApp teilen
              </DropdownMenuItem>
              <DropdownMenuItem onClick={shareEmail} data-testid={`menu-share-email-${m.meeting_id}`}>
                <Mail className="w-3.5 h-3.5 mr-2 text-[#4A5D4E]" /> Per E-Mail teilen
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {m.scheduled_at && (
                <DropdownMenuItem onClick={() => window.open(`${process.env.REACT_APP_BACKEND_URL}/api/meetings/${m.meeting_id}/ical`, '_blank')} data-testid={`menu-ical-${m.meeting_id}`}>
                  <CalendarPlus className="w-3.5 h-3.5 mr-2 text-[#6B8E23]" /> {t('toCalendar')}
                </DropdownMenuItem>
              )}
              {m.status !== 'ended' && (
                <DropdownMenuItem onClick={() => setEditOpen(true)} data-testid={`menu-edit-${m.meeting_id}`}>
                  <Pencil className="w-3.5 h-3.5 mr-2" /> Bearbeiten
                </DropdownMenuItem>
              )}
              {canRing && (
                <DropdownMenuItem onClick={handleRing} data-testid={`menu-ring-${m.meeting_id}`}>
                  <BellRing className="w-3.5 h-3.5 mr-2 text-[#D4A373]" /> Jetzt klingeln
                </DropdownMenuItem>
              )}
              {m.series_id && (
                <DropdownMenuItem onClick={() => setSeriesOpen(true)} data-testid={`menu-series-${m.meeting_id}`}>
                  <CalendarDays className="w-3.5 h-3.5 mr-2 text-[#D4A373]" /> Serie verwalten
                </DropdownMenuItem>
              )}
              {m.status === 'ended' && (
                <>
                  <DropdownMenuItem onClick={() => navigate(`/meetings/${m.meeting_id}/summary`)} data-testid={`menu-summary-${m.meeting_id}`}>
                    <Sparkles className="w-3.5 h-3.5 mr-2 text-[#D4A373]" /> Zusammenfassung
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={async () => {
                    try {
                      const { data } = await api.post(`/meetings/${m.meeting_id}/send-summary-email`);
                      toast.success(`Zusammenfassung an ${data.sent_to} Teilnehmer gesendet`);
                    } catch (err) { toast.error(err.response?.data?.detail || 'Fehler beim Senden'); }
                  }} data-testid={`menu-send-summary-${m.meeting_id}`}>
                    <Send className="w-3.5 h-3.5 mr-2 text-[#4A5D4E]" /> {t('sendSummary')}
                  </DropdownMenuItem>
                </>
              )}
              <DropdownMenuItem onClick={() => setDeleteOpen(true)} className="text-[#C87967]" data-testid={`menu-delete-${m.meeting_id}`}>
                <Trash2 className="w-3.5 h-3.5 mr-2" /> Löschen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader><DialogTitle className="text-base font-medium">{t('editMeeting')}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Titel</label>
              <Input value={editTitle} onChange={e => setEditTitle(e.target.value)} className="border-[#E2E4E0] rounded-xl" data-testid="edit-meeting-title" />
            </div>
            <div>
              <label className="text-xs font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Beschreibung</label>
              <Input value={editDesc} onChange={e => setEditDesc(e.target.value)} className="border-[#E2E4E0] rounded-xl" data-testid="edit-meeting-desc" />
            </div>
            <div>
              <label className="text-xs font-bold text-[#6B7280] uppercase tracking-wider block mb-1">Datum & Uhrzeit</label>
              <DateTimeInput
                date={parseDateTime(editDate).date}
                time={parseDateTime(editDate).time}
                onDateChange={v => setEditDate(combineDateTime(v, parseDateTime(editDate).time))}
                onTimeChange={v => setEditDate(combineDateTime(parseDateTime(editDate).date, v))}
              />
            </div>
            <div className="flex items-start gap-3 p-3 rounded-xl bg-[#FFF8E7] border border-[#D4A373]/30">
              <input
                type="checkbox"
                id={`auto-rering-${m.meeting_id}`}
                checked={editAutoRering}
                onChange={e => setEditAutoRering(e.target.checked)}
                className="mt-0.5 w-4 h-4 accent-[#D4A373]"
                data-testid={`edit-auto-rering-${m.meeting_id}`}
              />
              <label htmlFor={`auto-rering-${m.meeting_id}`} className="flex-1 cursor-pointer">
                <div className="text-sm font-medium text-[#1C1F1D] flex items-center gap-1.5">
                  <BellRing className="w-3.5 h-3.5 text-[#D4A373]" />
                  Auto-Nachklingeln
                </div>
                <p className="text-[11px] text-[#9CA3AF] leading-snug mt-0.5">
                  Klingelt automatisch bis zu 3× (alle 30 s) bei abwesenden Teilnehmern, wenn das Meeting gestartet wird.
                </p>
              </label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)} className="rounded-full border-[#E2E4E0]">{t('cancel')}</Button>
            <Button onClick={handleEdit} disabled={saving} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full" data-testid="save-edit-meeting">
              {saving ? '...' : 'Speichern'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-[380px]">
          <DialogHeader><DialogTitle className="text-base font-medium">{t('deleteMeeting')}</DialogTitle></DialogHeader>
          <p className="text-sm text-[#4B5563]">"{m.title}" wird unwiderruflich gelöscht.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)} className="rounded-full border-[#E2E4E0]">{t('cancel')}</Button>
            <Button onClick={handleDelete} className="bg-[#C87967] hover:bg-[#B56555] text-white rounded-full" data-testid="confirm-delete-meeting">{t('delete')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {m.series_id && (
        <SeriesManagerDialog
          open={seriesOpen}
          onClose={() => { setSeriesOpen(false); onRefresh?.(); }}
          seriesId={m.series_id}
          title={m.title}
        />
      )}
    </>
  );
}
