import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { CalendarClock, Clock, Check, ChevronLeft, ChevronRight, UserCircle, Video, CalendarPlus, Link2, Copy } from 'lucide-react';
import axios from 'axios';
import { toast, Toaster } from 'sonner';
import { copyToClipboard } from '../lib/clipboard';
import { useLanguage } from '../contexts/LanguageContext';

const API = process.env.REACT_APP_BACKEND_URL;
const pubApi = axios.create({ baseURL: `${API}/api` });

export default function PublicBookingPage() {
  const { t } = useLanguage();
  const { username, slug } = useParams();
  const basePath = slug ? `/book/${encodeURIComponent(username)}/${encodeURIComponent(slug)}` : `/book/${encodeURIComponent(username)}`;
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState('');
  const [slots, setSlots] = useState([]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [guestName, setGuestName] = useState('');
  const [guestEmail, setGuestEmail] = useState('');
  const [topic, setTopic] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [booking, setBooking] = useState(null);
  const [currentMonth, setCurrentMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });

  useEffect(() => {
    (async () => {
      try {
        const { data } = await pubApi.get(`${basePath}/info`);
        setInfo(data);
      } catch { toast.error('Buchungsseite nicht verfügbar'); }
      finally { setLoading(false); }
    })();
  }, [basePath]);

  const fetchSlots = useCallback(async (date) => {
    setLoadingSlots(true);
    setSelectedSlot(null);
    try {
      const { data } = await pubApi.get(`${basePath}/slots?date=${date}`);
      setSlots(data.slots || []);
    } catch { setSlots([]); }
    finally { setLoadingSlots(false); }
  }, [basePath]);

  const handleDateClick = (date) => {
    const iso = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
    setSelectedDate(iso);
    fetchSlots(iso);
  };

  const handleBook = async () => {
    if (!guestName.trim()) { toast.error('Bitte Name eingeben'); return; }
    if (!selectedSlot) { toast.error('Bitte Zeitfenster auswählen'); return; }
    setSubmitting(true);
    try {
      const { data } = await pubApi.post(basePath, {
        date: selectedDate, start_time: selectedSlot.start_time,
        guest_name: guestName, guest_email: guestEmail, topic,
      });
      setBooking(data);
      toast.success('Termin gebucht!');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Buchung fehlgeschlagen');
    } finally { setSubmitting(false); }
  };

  // Mini calendar
  const renderCalendar = () => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const offset = firstDay === 0 ? 6 : firstDay - 1;
    const cells = [];
    for (let i = 0; i < offset; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));

    const monthNames = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

    return (
      <div>
        <div className="flex items-center justify-between mb-3">
          <button onClick={() => setCurrentMonth(new Date(year, month - 1, 1))} className="p-1.5 rounded-lg hover:bg-[#F3F4F1] text-[#6B7280]"><ChevronLeft className="w-4 h-4" /></button>
          <span className="text-sm font-medium text-[#1C1F1D]">{monthNames[month]} {year}</span>
          <button onClick={() => setCurrentMonth(new Date(year, month + 1, 1))} className="p-1.5 rounded-lg hover:bg-[#F3F4F1] text-[#6B7280]"><ChevronRight className="w-4 h-4" /></button>
        </div>
        <div className="grid grid-cols-7 gap-1 text-center">
          {['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map(d => (
            <div key={d} className="text-[10px] font-bold text-[#9CA3AF] py-1">{d}</div>
          ))}
          {cells.map((date, i) => {
            if (!date) return <div key={`e${i}`} />;
            const iso = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
            const isPast = date < today;
            const isSelected = iso === selectedDate;
            const isToday = date.getTime() === today.getTime();
            return (
              <button key={iso} disabled={isPast}
                onClick={() => handleDateClick(date)}
                data-testid={`cal-${iso}`}
                className={`w-9 h-9 rounded-lg text-sm transition-all
                  ${isPast ? 'text-[#D1D5DB] cursor-not-allowed' : 'hover:bg-[#4A5D4E]/10 cursor-pointer'}
                  ${isSelected ? 'bg-[#4A5D4E] text-white font-bold' : ''}
                  ${isToday && !isSelected ? 'ring-1 ring-[#4A5D4E] font-medium' : ''}
                `}>
                {date.getDate()}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8] text-[#9CA3AF]">Loading...</div>;
  if (!info) return (
    <div className="min-h-screen flex items-center justify-center bg-[#F9F9F8]">
      <div className="text-center"><CalendarClock className="w-12 h-12 text-[#E2E4E0] mx-auto mb-3" /><p className="text-[#9CA3AF] text-sm">{t('bookingPageUnavailable')}</p></div>
    </div>
  );

  if (booking) {
    return (
      <div className="min-h-screen bg-[#F9F9F8] flex items-center justify-center">
        <Toaster position="top-right" richColors />
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-8 max-w-md w-full text-center mx-4" data-testid="booking-confirmed">
          <div className="w-16 h-16 rounded-full bg-[#6B8E23]/10 flex items-center justify-center mx-auto mb-4">
            <Check className="w-8 h-8 text-[#6B8E23]" />
          </div>
          <h2 className="text-xl font-medium text-[#1C1F1D] mb-2" style={{ fontFamily: 'Manrope' }}>Termin gebucht!</h2>
          <div className="bg-[#F3F4F1] rounded-xl p-4 text-left mb-4 space-y-2">
            <div className="flex justify-between text-sm"><span className="text-[#6B7280]">Datum</span><span className="font-medium text-[#1C1F1D]">{new Date(booking.date + 'T00:00:00').toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' })}</span></div>
            <div className="flex justify-between text-sm"><span className="text-[#6B7280]">Uhrzeit</span><span className="font-medium text-[#1C1F1D]">{booking.start_time} - {booking.end_time}</span></div>
            {booking.host_name && <div className="flex justify-between text-sm"><span className="text-[#6B7280]">Mit</span><span className="font-medium text-[#1C1F1D]">{booking.host_name}</span></div>}
            {booking.topic && <div className="flex justify-between text-sm"><span className="text-[#6B7280]">Thema</span><span className="font-medium text-[#1C1F1D]">{booking.topic}</span></div>}
          </div>
          {booking.meeting_id && (
            <div className="mb-4">
              <span className="text-xs uppercase tracking-[0.15em] font-bold text-[#6B7280] block mb-1.5 text-left">Meeting-Link</span>
              <div className="flex items-center gap-2 bg-[#F3F4F1] rounded-lg p-2.5">
                <Link2 className="w-3.5 h-3.5 text-[#4A5D4E] flex-shrink-0" />
                <input readOnly value={`${window.location.origin}/meetings/${booking.meeting_id}/join`}
                  className="flex-1 bg-transparent text-xs text-[#4B5563] outline-none truncate" data-testid="booking-meeting-link" />
                <Button size="sm" onClick={() => { copyToClipboard(`${window.location.origin}/meetings/${booking.meeting_id}/join`); toast.success('Link kopiert'); }}
                  className="bg-[#4A5D4E] text-white rounded-full px-2.5 h-6 text-[10px]" data-testid="copy-booking-link">
                  <Copy className="w-3 h-3 mr-1" />Kopieren
                </Button>
              </div>
            </div>
          )}
          {booking.meeting_id && (
            <Button onClick={() => window.open(`${window.location.origin}/meetings/${booking.meeting_id}/join`, '_blank')}
              className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full px-5 h-10 mb-3 w-full" data-testid="booking-join-meeting">
              <Video className="w-4 h-4 mr-1.5" /> Zur Besprechung
            </Button>
          )}
          <p className="text-xs text-[#9CA3AF] mb-4">{t('meetFlowAutoCreated')}</p>
          <Button onClick={() => window.open(`${API}/api/bookings/${booking.booking_id}/ical`, '_blank')}
            className="bg-[#6B8E23] hover:bg-[#5A7C1E] text-white rounded-full px-5 h-10 w-full" data-testid="booking-add-to-calendar">
            <CalendarPlus className="w-4 h-4 mr-1.5" /> Zum Kalender hinzufügen
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9F9F8]">
      <Toaster position="top-right" richColors />
      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center gap-2.5 mb-6">
          <Video className="w-6 h-6 text-[#4A5D4E]" />
          <span className="text-lg font-semibold text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>MeetFlow</span>
        </div>

        <div className="bg-white border border-[#E2E4E0] rounded-xl p-6 mb-6">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center flex-shrink-0">
              {info.avatar ? (
                <img src={info.avatar.startsWith('/api/') ? `${API}${info.avatar}` : info.avatar} alt="" className="w-14 h-14 rounded-full object-cover" />
              ) : (
                <UserCircle className="w-8 h-8 text-[#4A5D4E]" />
              )}
            </div>
            <div>
              <h1 className="text-xl font-medium text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }} data-testid="booking-host-name">
                {info.title || info.user_name}
              </h1>
              <p className="text-sm text-[#6B7280]">{info.user_name}</p>
              {info.description && <p className="text-xs text-[#9CA3AF] mt-1">{info.description}</p>}
              <p className="text-xs text-[#6B7280] flex items-center gap-1.5 mt-1"><Clock className="w-3.5 h-3.5" />{info.slot_duration} Min. Meeting</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Calendar */}
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="booking-calendar">
            <h3 className="text-sm font-medium text-[#1C1F1D] mb-4">{t('selectDate')}</h3>
            {renderCalendar()}
          </div>

          {/* Slots + Form */}
          <div className="space-y-4">
            {selectedDate && (
              <div className="bg-white border border-[#E2E4E0] rounded-xl p-5" data-testid="booking-slots">
                <h3 className="text-sm font-medium text-[#1C1F1D] mb-3">
                  {new Date(selectedDate).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' })}
                </h3>
                {loadingSlots ? (
                  <p className="text-sm text-[#9CA3AF] text-center py-4">{t('loading')}</p>
                ) : slots.length === 0 ? (
                  <p className="text-sm text-[#9CA3AF] text-center py-4">{t('noFreeSlotsOnDay')}</p>
                ) : (
                  <div className="grid grid-cols-2 gap-2 max-h-60 overflow-y-auto">
                    {slots.map(slot => (
                      <button key={slot.start_time} onClick={() => setSelectedSlot(slot)} data-testid={`slot-${slot.start_time}`}
                        className={`p-2.5 rounded-lg text-sm font-medium text-center transition-all
                          ${selectedSlot?.start_time === slot.start_time
                            ? 'bg-[#4A5D4E] text-white'
                            : 'bg-[#F3F4F1] text-[#4B5563] hover:bg-[#4A5D4E]/10 hover:text-[#4A5D4E]'}`}>
                        {slot.start_time}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {selectedSlot && (
              <div className="bg-white border border-[#E2E4E0] rounded-xl p-5 space-y-3" data-testid="booking-form">
                <h3 className="text-sm font-medium text-[#1C1F1D]">{t('bookAppointment')}</h3>
                <div className="p-3 bg-[#4A5D4E]/5 rounded-lg text-sm text-[#4A5D4E] font-medium">
                  {new Date(selectedDate).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' })}, {selectedSlot.start_time} - {selectedSlot.end_time}
                </div>
                <Input data-testid="guest-name" value={guestName} onChange={e => setGuestName(e.target.value)} placeholder={t('yourName')} className="border-[#E2E4E0] rounded-xl" />
                <Input data-testid="guest-email" value={guestEmail} onChange={e => setGuestEmail(e.target.value)} placeholder={t('emailOptional')} className="border-[#E2E4E0] rounded-xl" />
                <Textarea data-testid="guest-topic" value={topic} onChange={e => setTopic(e.target.value)} placeholder={t('topicOptional')} className="border-[#E2E4E0] rounded-xl min-h-[60px]" />
                <Button onClick={handleBook} disabled={submitting} data-testid="book-submit"
                  className="w-full bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full h-11 font-medium">
                  {submitting ? 'Buche...' : 'Termin buchen'}
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
