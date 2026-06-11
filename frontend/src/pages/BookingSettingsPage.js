import { copyToClipboard } from '../lib/clipboard';
import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import Sidebar from '../components/Sidebar';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Textarea } from '../components/ui/textarea';
import { ArrowLeft, Copy, ExternalLink, Clock, Calendar, Trash2, Plus, Link2, Pencil, Globe, Users, ChevronDown, ChevronUp, XCircle, User, Mail } from 'lucide-react';
import { TimeRangeInput } from '../components/DateTimeInput';
import api from '../lib/api';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { flushSync } from 'react-dom';

import { useLanguage } from '../contexts/LanguageContext';
const DAYS = [
  { key: 'mon', label: 'Montag' }, { key: 'tue', label: 'Dienstag' },
  { key: 'wed', label: 'Mittwoch' }, { key: 'thu', label: 'Donnerstag' },
  { key: 'fri', label: 'Freitag' }, { key: 'sat', label: 'Samstag' },
  { key: 'sun', label: 'Sonntag' },
];

const DEFAULT_WEEKDAYS = {
  mon: { enabled: true, start: '09:00', end: '17:00' },
  tue: { enabled: true, start: '09:00', end: '17:00' },
  wed: { enabled: true, start: '09:00', end: '17:00' },
  thu: { enabled: true, start: '09:00', end: '17:00' },
  fri: { enabled: true, start: '09:00', end: '17:00' },
  sat: { enabled: false, start: '09:00', end: '17:00' },
  sun: { enabled: false, start: '09:00', end: '17:00' },
};

export default function BookingSettingsPage() {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editPage, setEditPage] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    slug: '', title: '', description: '',
    weekdays: DEFAULT_WEEKDAYS, slot_duration: 30, buffer_time: 10, enabled: true,
  });
  const [expandedPage, setExpandedPage] = useState(null);
  const [pageBookings, setPageBookings] = useState({});
  const [allBookings, setAllBookings] = useState([]);
  const [showAllBookings, setShowAllBookings] = useState(false);

  const fetchPages = useCallback(async () => {
    try {
      const { data } = await api.get('/booking/pages');
      setPages(data);
    } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchPages(); }, [fetchPages]);

  const openCreate = () => {
    setEditPage(null);
    setForm({ slug: '', title: '', description: '', weekdays: DEFAULT_WEEKDAYS, slot_duration: 30, buffer_time: 10, enabled: true, booking_until: '', max_advance_days: '' });
    setDialogOpen(true);
  };

  const openEdit = (p) => {
    setEditPage(p);
    setForm({
      slug: p.slug, title: p.title || '', description: p.description || '',
      weekdays: p.weekdays || DEFAULT_WEEKDAYS,
      slot_duration: p.slot_duration || 30, buffer_time: p.buffer_time || 10,
      enabled: p.enabled !== false,
      booking_until: p.booking_until || '',
      max_advance_days: p.max_advance_days ?? '',
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!editPage && !form.slug.trim()) { toast.error('Slug ist erforderlich'); return; }
    setSaving(true);
    try {
      if (editPage) {
        await api.put(`/booking/pages/${editPage.page_id}`, form);
      } else {
        await api.post('/booking/pages', form);
      }
      flushSync(() => setDialogOpen(false));
      setTimeout(() => { toast.success(editPage ? 'Buchungsseite aktualisiert' : 'Buchungsseite erstellt'); setEditPage(null); }, 50);
      fetchPages();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern');
    } finally { setSaving(false); }
  };

  const handleDelete = async (p) => {
    if (!window.confirm(`"${p.title || p.slug}" wirklich löschen?`)) return;
    try {
      await api.delete(`/booking/pages/${p.page_id}`);
      toast.success('Buchungsseite gelöscht');
      fetchPages();
    } catch { toast.error('Fehler beim Löschen'); }
  };

  const updateDay = (day, field, value) => {
    setForm(prev => ({
      ...prev,
      weekdays: { ...prev.weekdays, [day]: { ...prev.weekdays[day], [field]: value } }
    }));
  };

  const toggleBookings = async (pageId) => {
    if (expandedPage === pageId) { setExpandedPage(null); return; }
    setExpandedPage(pageId);
    if (!pageBookings[pageId]) {
      try {
        const { data } = await api.get(`/booking/pages/${pageId}/bookings`);
        setPageBookings(prev => ({ ...prev, [pageId]: data.bookings }));
      } catch { toast.error('Buchungen konnten nicht geladen werden'); }
    }
  };

  const cancelBooking = async (bookingId, pageId) => {
    if (!window.confirm('Buchung wirklich stornieren?')) return;
    try {
      await api.delete(`/booking/${bookingId}`);
      toast.success('Buchung storniert');
      if (pageId) {
        setPageBookings(prev => ({
          ...prev,
          [pageId]: (prev[pageId] || []).map(b => b.booking_id === bookingId ? { ...b, status: 'cancelled' } : b)
        }));
      }
      setAllBookings(prev => prev.map(b => b.booking_id === bookingId ? { ...b, status: 'cancelled' } : b));
    } catch { toast.error('Fehler beim Stornieren'); }
  };

  const fetchAllBookings = async () => {
    setShowAllBookings(prev => !prev);
    if (allBookings.length > 0) return;
    try {
      const { data } = await api.get('/booking/all-bookings');
      setAllBookings(data.bookings);
    } catch { toast.error('Buchungen konnten nicht geladen werden'); }
  };

  const getBookingUrl = (slug) => {
    if (!user) return '';
    const nameSlug = (user.name || '').trim().toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9\-]/g, '');
    return `${window.location.origin}/book/${nameSlug}/${slug}`;
  };

  if (loading) return <div className="flex min-h-screen bg-[#F9F9F8]"><Sidebar /><main className="flex-1 ml-0 md:ml-[260px] p-8 text-center pt-24 text-[#9CA3AF]">Laden...</main></div>;

  return (
    <div className="flex min-h-screen bg-[#F9F9F8]">
      <Sidebar />
      <main className="flex-1 ml-0 md:ml-[260px] p-4 pt-14 md:px-8 md:pt-20 md:pb-8 animate-fade-in" data-testid="booking-settings-page">
        <div className="max-w-2xl mx-auto">
          <button onClick={() => navigate('/schedule')} className="flex items-center gap-1.5 text-sm text-[#4B5563] hover:text-[#1C1F1D] mb-6">
            <ArrowLeft className="w-4 h-4" /> Zurück
          </button>

          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-medium tracking-tight" style={{ fontFamily: 'Manrope' }}>Buchungsseiten</h1>
            <Button onClick={openCreate} disabled={pages.length >= 5}
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-sm" data-testid="create-booking-page-btn">
              <Plus className="w-4 h-4 mr-1" /> Neue Seite
            </Button>
          </div>

          {pages.length >= 5 && (
            <p className="text-xs text-[#C87967] mb-4">Maximal 5 Buchungsseiten erreicht</p>
          )}

          {pages.length === 0 ? (
            <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 text-center">
              <Globe className="w-10 h-10 text-[#E2E4E0] mx-auto mb-3" />
              <p className="text-sm text-[#9CA3AF] mb-4">{t('noBookingPagesYet')}</p>
              <Button onClick={openCreate} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full text-sm">
                <Plus className="w-4 h-4 mr-1" /> Erste Seite erstellen
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {pages.map(p => {
                const url = getBookingUrl(p.slug);
                const bookings = pageBookings[p.page_id] || [];
                const isExpanded = expandedPage === p.page_id;
                const confirmedCount = bookings.filter(b => b.status === 'confirmed').length;
                return (
                  <div key={p.page_id} className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden" data-testid={`booking-page-${p.page_id}`}>
                    <div className="p-5">
                      <div className="flex items-start justify-between mb-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="text-sm font-medium text-[#1C1F1D] truncate">{p.title || p.slug}</h3>
                            <Badge className={p.enabled ? 'bg-[#4A5D4E]/10 text-[#4A5D4E] text-[10px]' : 'bg-[#9CA3AF]/10 text-[#9CA3AF] text-[10px]'}>
                              {p.enabled ? 'Aktiv' : 'Inaktiv'}
                            </Badge>
                          </div>
                          {p.description && <p className="text-xs text-[#9CA3AF] mb-2">{p.description}</p>}
                          <div className="flex items-center gap-3 text-xs text-[#6B7280]">
                            <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{p.slot_duration} Min.</span>
                            <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />
                              {Object.values(p.weekdays || {}).filter(d => d.enabled).length} Tage/Woche
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <Button variant="ghost" size="sm" onClick={() => openEdit(p)} className="h-7 w-7 p-0 text-[#6B7280]" title="Bearbeiten" data-testid={`edit-page-${p.page_id}`}>
                            <Pencil className="w-3.5 h-3.5" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => handleDelete(p)} className="h-7 w-7 p-0 text-[#C87967]" title="Löschen" data-testid={`delete-page-${p.page_id}`}>
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 bg-[#F3F4F1] rounded-lg p-2.5">
                        <Link2 className="w-3.5 h-3.5 text-[#4A5D4E] flex-shrink-0" />
                        <input readOnly value={url} className="flex-1 bg-transparent text-xs text-[#4B5563] outline-none truncate" />
                        <Button size="sm" onClick={() => { copyToClipboard(url); toast.success('Link kopiert'); }}
                          className="bg-[#4A5D4E] text-white rounded-full px-2.5 h-6 text-[10px]" data-testid={`copy-link-${p.page_id}`}>
                          <Copy className="w-3 h-3 mr-1" />Kopieren
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => window.open(url, '_blank')}
                          className="rounded-full border-[#E2E4E0] px-2 h-6">
                          <ExternalLink className="w-3 h-3" />
                        </Button>
                      </div>

                      {/* Bookings toggle */}
                      <button onClick={() => toggleBookings(p.page_id)}
                        className="flex items-center gap-1.5 mt-3 text-xs text-[#4A5D4E] hover:text-[#3E4E42] font-medium transition-colors"
                        data-testid={`toggle-bookings-${p.page_id}`}>
                        <Users className="w-3.5 h-3.5" />
                        Buchungen anzeigen {isExpanded && confirmedCount > 0 && `(${confirmedCount})`}
                        {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </button>
                    </div>

                    {/* Expanded bookings list */}
                    {isExpanded && (
                      <div className="border-t border-[#E2E4E0] bg-[#FAFAF9]" data-testid={`bookings-list-${p.page_id}`}>
                        {bookings.length === 0 ? (
                          <div className="p-6 text-center">
                            <Calendar className="w-8 h-8 text-[#E2E4E0] mx-auto mb-2" />
                            <p className="text-xs text-[#9CA3AF]">{t('noBookingsForThisPage')}</p>
                          </div>
                        ) : (
                          <div className="divide-y divide-[#E2E4E0]">
                            {bookings.map(b => (
                              <div key={b.booking_id} className={`px-5 py-3 flex items-center gap-3 ${b.status === 'cancelled' ? 'opacity-50' : ''}`}
                                data-testid={`booking-${b.booking_id}`}>
                                <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
                                  <User className="w-4 h-4 text-[#4A5D4E]" />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2">
                                    <span className="text-sm font-medium text-[#1C1F1D] truncate">{b.guest_name}</span>
                                    <Badge className={b.status === 'confirmed'
                                      ? 'bg-[#6B8E23]/10 text-[#6B8E23] text-[10px]'
                                      : 'bg-[#C87967]/10 text-[#C87967] text-[10px]'}>
                                      {b.status === 'confirmed' ? 'Bestätigt' : 'Storniert'}
                                    </Badge>
                                  </div>
                                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-[#6B7280] mt-0.5">
                                    {b.guest_email && (
                                      <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{b.guest_email}</span>
                                    )}
                                    <span className="flex items-center gap-1">
                                      <Calendar className="w-3 h-3" />
                                      {new Date(b.date + 'T12:00').toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}
                                    </span>
                                    <span className="flex items-center gap-1">
                                      <Clock className="w-3 h-3" />{b.start_time} - {b.end_time}
                                    </span>
                                    {b.topic && <span className="truncate max-w-[150px]">{b.topic}</span>}
                                  </div>
                                </div>
                                {b.status === 'confirmed' && (
                                  <Button variant="ghost" size="sm" onClick={() => cancelBooking(b.booking_id, p.page_id)}
                                    className="h-7 px-2 text-[#C87967] hover:text-[#C87967] hover:bg-[#C87967]/10 flex-shrink-0"
                                    title="Stornieren" data-testid={`cancel-booking-${b.booking_id}`}>
                                    <XCircle className="w-3.5 h-3.5 mr-1" /><span className="text-[10px]">Stornieren</span>
                                  </Button>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* All Bookings Overview */}
          <div className="mt-8">
            <button onClick={fetchAllBookings}
              className="flex items-center gap-2 text-sm font-medium text-[#1C1F1D] hover:text-[#4A5D4E] mb-4 transition-colors"
              data-testid="toggle-all-bookings">
              <Users className="w-4 h-4" />
              Alle Buchungen anzeigen
              {showAllBookings ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showAllBookings && (
              <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden" data-testid="all-bookings-list">
                {allBookings.length === 0 ? (
                  <div className="p-8 text-center">
                    <Calendar className="w-10 h-10 text-[#E2E4E0] mx-auto mb-2" />
                    <p className="text-sm text-[#9CA3AF]">{t('noBookingsYet')}</p>
                  </div>
                ) : (
                  <div className="divide-y divide-[#E2E4E0]">
                    <div className="px-5 py-3 bg-[#F3F4F1] flex items-center gap-2 text-xs font-medium text-[#6B7280]">
                      <span>{allBookings.length} Buchungen gesamt</span>
                      <span>({allBookings.filter(b => b.status === 'confirmed').length} bestätigt)</span>
                    </div>
                    {allBookings.map(b => (
                      <div key={b.booking_id} className={`px-5 py-3 flex items-center gap-3 ${b.status === 'cancelled' ? 'opacity-50' : ''}`}
                        data-testid={`all-booking-${b.booking_id}`}>
                        <div className="w-8 h-8 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
                          <User className="w-4 h-4 text-[#4A5D4E]" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-[#1C1F1D] truncate">{b.guest_name}</span>
                            <Badge className={b.status === 'confirmed'
                              ? 'bg-[#6B8E23]/10 text-[#6B8E23] text-[10px]'
                              : 'bg-[#C87967]/10 text-[#C87967] text-[10px]'}>
                              {b.status === 'confirmed' ? 'Bestätigt' : 'Storniert'}
                            </Badge>
                            {b.page_slug && (
                              <Badge className="bg-[#4A5D4E]/10 text-[#4A5D4E] text-[10px]">{b.page_slug}</Badge>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-[#6B7280] mt-0.5">
                            {b.guest_email && (
                              <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{b.guest_email}</span>
                            )}
                            <span className="flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              {new Date(b.date + 'T12:00').toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}
                            </span>
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3" />{b.start_time} - {b.end_time}
                            </span>
                            {b.topic && <span className="truncate max-w-[200px]">{b.topic}</span>}
                          </div>
                        </div>
                        {b.status === 'confirmed' && (
                          <Button variant="ghost" size="sm" onClick={() => cancelBooking(b.booking_id, null)}
                            className="h-7 px-2 text-[#C87967] hover:text-[#C87967] hover:bg-[#C87967]/10 flex-shrink-0"
                            title="Stornieren" data-testid={`cancel-all-booking-${b.booking_id}`}>
                            <XCircle className="w-3.5 h-3.5 mr-1" /><span className="text-[10px]">Stornieren</span>
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[560px] max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editPage ? 'Buchungsseite bearbeiten' : 'Neue Buchungsseite'}</DialogTitle>
            <DialogDescription>
              {editPage ? 'Einstellungen für diese Buchungsseite anpassen' : 'Erstellen Sie eine neue Buchungsseite mit eigenem Link'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            {!editPage && (
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Slug (URL-Pfad)</Label>
                <Input value={form.slug} onChange={e => setForm(prev => ({ ...prev, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') }))}
                  placeholder="z.B. intern, extern, beratung" className="border-[#E2E4E0] rounded-xl" data-testid="page-slug-input" />
                <p className="text-[10px] text-[#9CA3AF] mt-1">{getBookingUrl(form.slug || 'slug')}</p>
              </div>
            )}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Titel</Label>
              <Input value={form.title} onChange={e => setForm(prev => ({ ...prev, title: e.target.value }))}
                placeholder="z.B. Externe Beratung" className="border-[#E2E4E0] rounded-xl" data-testid="page-title-input" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Beschreibung</Label>
              <Textarea value={form.description} onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Kurze Beschreibung der Buchungsseite" className="border-[#E2E4E0] rounded-xl resize-none h-16" data-testid="page-desc-input" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Slot-Dauer</Label>
                <Select value={String(form.slot_duration)} onValueChange={v => setForm(prev => ({ ...prev, slot_duration: Number(v) }))}>
                  <SelectTrigger className="border-[#E2E4E0] rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[15, 30, 45, 60, 90, 120].map(m => <SelectItem key={m} value={String(m)}>{m} Minuten</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-1.5 block">Puffer</Label>
                <Select value={String(form.buffer_time)} onValueChange={v => setForm(prev => ({ ...prev, buffer_time: Number(v) }))}>
                  <SelectTrigger className="border-[#E2E4E0] rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[0, 5, 10, 15, 30].map(m => <SelectItem key={m} value={String(m)}>{m === 0 ? 'Kein Puffer' : `${m} Min.`}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Weekly schedule */}
            <div>
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] mb-2 block">Wochenplan</Label>
              <div className="space-y-2">
                {DAYS.map(({ key, label }) => {
                  const day = form.weekdays?.[key] || { enabled: false, start: '09:00', end: '17:00' };
                  return (
                    <div key={key} className={`flex flex-wrap items-center gap-2 p-2 rounded-lg ${day.enabled ? 'bg-[#F3F4F1]' : 'bg-[#F9F9F8] opacity-60'}`}>
                      <Switch checked={day.enabled} onCheckedChange={v => updateDay(key, 'enabled', v)} />
                      <span className="text-xs font-medium text-[#1C1F1D] w-16">{label}</span>
                      {day.enabled && (
                        <TimeRangeInput startTime={day.start} endTime={day.end}
                          onStartChange={v => updateDay(key, 'start', v)}
                          onEndChange={v => updateDay(key, 'end', v)}
                          className="flex-1 basis-full sm:basis-auto min-w-0" />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="flex items-center justify-between p-3 bg-[#F3F4F1] rounded-lg">
              <span className="text-sm text-[#1C1F1D]">{t('bookingPageEnabled')}</span>
              <Switch checked={form.enabled} onCheckedChange={v => setForm(prev => ({ ...prev, enabled: v }))} data-testid="page-enabled-toggle" />
            </div>

            {/* iter 189 — Buchungs-Horizont (max-Datum + max-Tage-im-Voraus) */}
            <div className="border border-[#E2E4E0] rounded-lg p-3 space-y-3">
              <Label className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] block">
                Buchungs-Zeitraum begrenzen <span className="text-[10px] normal-case text-[#9CA3AF]">(beide optional)</span>
              </Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <Label className="text-[11px] text-[#6B7280] mb-1 block">Buchbar bis (Datum)</Label>
                  <Input
                    type="date"
                    value={form.booking_until || ''}
                    onChange={e => setForm(prev => ({ ...prev, booking_until: e.target.value }))}
                    className="border-[#E2E4E0] rounded-lg h-9 text-sm"
                    data-testid="booking-until-input"
                  />
                  <p className="text-[10px] text-[#9CA3AF] mt-1">Nach diesem Tag keine neuen Buchungen.</p>
                </div>
                <div>
                  <Label className="text-[11px] text-[#6B7280] mb-1 block">Max. Tage im Voraus</Label>
                  <Input
                    type="number" min="1" max="365"
                    value={form.max_advance_days ?? ''}
                    onChange={e => setForm(prev => ({ ...prev, max_advance_days: e.target.value ? Number(e.target.value) : '' }))}
                    placeholder="z.B. 30"
                    className="border-[#E2E4E0] rounded-lg h-9 text-sm"
                    data-testid="max-advance-days-input"
                  />
                  <p className="text-[10px] text-[#9CA3AF] mt-1">Rollendes Fenster ab heute.</p>
                </div>
              </div>
            </div>

            <div className="flex gap-2 justify-end pt-2">
              <Button variant="outline" onClick={() => setDialogOpen(false)} className="rounded-lg">Abbrechen</Button>
              <Button onClick={handleSave} disabled={saving} className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg" data-testid="save-booking-page-btn">
                {saving ? '...' : editPage ? 'Speichern' : 'Erstellen'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
