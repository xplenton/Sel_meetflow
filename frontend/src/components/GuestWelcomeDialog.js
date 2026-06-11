import { useState, useEffect } from 'react';
import { UserCircle, ArrowRight, Check, Send } from 'lucide-react';
import { Dialog, DialogContent } from './ui/dialog';
import { Button } from './ui/button';
import api from '../lib/api';
import { toast } from 'sonner';
import { useAuth } from '../contexts/AuthContext';

/**
 * Guest Welcome Tour (iter 155)
 *
 * Shows a friendly 2-slide welcome dialog on first login for users who
 * are in the "Gast" group and haven't seen the tour yet. Purpose:
 * explain why the user-picker / search / mentions are empty so external
 * guests don't think the app is broken.
 *
 * Visibility logic:
 *   * user.is_guest === true (server-computed in /auth/me)
 *   * user.guest_onboarded_at is falsy
 * On dismiss we POST /users/me/guest-onboarding-complete so the dialog
 * stays dismissed across device changes.
 */
export default function GuestWelcomeDialog() {
  const { user, setUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [slide, setSlide] = useState(0);
  const [saving, setSaving] = useState(false);
  const [notifying, setNotifying] = useState(false);
  const [notified, setNotified] = useState(false);

  useEffect(() => {
    if (!user) return;
    if (user.is_guest && !user.guest_onboarded_at) {
      setOpen(true);
      setSlide(0);
    }
  }, [user]);

  const finish = async () => {
    setSaving(true);
    try {
      await api.post('/users/me/guest-onboarding-complete');
      if (setUser) setUser({ ...user, guest_onboarded_at: new Date().toISOString() });
    } catch { /* silent — worst case the dialog shows again next login */ }
    setOpen(false);
    setSaving(false);
  };

  const notifyHost = async () => {
    setNotifying(true);
    try {
      await api.post('/users/me/notify-host');
      setNotified(true);
      toast.success('Dein Gastgeber wurde benachrichtigt');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Benachrichtigung fehlgeschlagen');
    } finally { setNotifying(false); }
  };

  const slides = [
    {
      icon: <UserCircle className="w-10 h-10 text-[#4A5D4E]" />,
      title: `Willkommen bei MeetFlow, ${user?.name?.split(' ')?.[0] || ''}!`,
      body: (
        <>
          <p className="text-sm text-[#4A5D4E] leading-relaxed">
            Du bist als <span className="font-semibold">Gast</span> angemeldet. Wir freuen uns,
            dass du dabei bist!
          </p>
          <p className="text-sm text-[#6B7280] leading-relaxed mt-3">
            Als Gast siehst du nur die Chats und Meetings, zu denen du eingeladen wurdest —
            also nur die Personen, mit denen du tatsächlich kommunizieren sollst.
          </p>
        </>
      ),
    },
    {
      icon: <Check className="w-10 h-10 text-[#6B8E23]" />,
      title: 'So kommst du zu weiteren Gesprächen',
      body: (
        <>
          <p className="text-sm text-[#4A5D4E] leading-relaxed">
            Wenn du mit weiteren Personen sprechen möchtest, bitte deinen Gastgeber dich zu
            einem Chat oder Meeting hinzuzufügen.
          </p>
          {/* iter 156 — 1-click "notify host" */}
          <Button
            onClick={notifyHost}
            disabled={notifying || notified}
            variant="outline"
            className="w-full mt-3 border-[#4A5D4E]/30 text-[#4A5D4E] hover:bg-[#4A5D4E]/5 text-sm h-10"
            data-testid="guest-notify-host-button"
          >
            {notified ? (
              <><Check className="w-3.5 h-3.5 mr-2 text-[#6B8E23]" /> Benachrichtigt</>
            ) : notifying ? (
              'Sende...'
            ) : (
              <><Send className="w-3.5 h-3.5 mr-2" /> Gastgeber jetzt benachrichtigen</>
            )}
          </Button>
          <div className="mt-4 p-3 rounded-lg bg-[#FFF8E7] border border-[#D4A373]/40">
            <p className="text-[11px] text-[#B8875C] leading-snug">
              <strong>Tipp:</strong> In deinen bestehenden Chats kannst du jederzeit neue
              Nachrichten schreiben, Anrufe starten und Dateien teilen.
            </p>
          </div>
        </>
      ),
    },
  ];

  const current = slides[slide];
  const isLast = slide === slides.length - 1;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) finish(); }}>
      <DialogContent className="max-w-md p-0 overflow-hidden" data-testid="guest-welcome-dialog">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-full bg-[#F3F4F1] flex items-center justify-center flex-shrink-0">
              {current.icon}
            </div>
            <div className="text-xs text-[#9CA3AF] uppercase tracking-wider font-medium">
              Schritt {slide + 1} von {slides.length}
            </div>
          </div>
          <h2 className="text-xl font-bold text-[#1C1F1D] mb-3" data-testid={`guest-welcome-slide-${slide}-title`}>
            {current.title}
          </h2>
          <div data-testid={`guest-welcome-slide-${slide}-body`}>
            {current.body}
          </div>
        </div>
        <div className="flex items-center justify-between px-6 py-4 border-t border-[#E2E4E0] bg-[#FAFAF9]">
          <div className="flex gap-1.5">
            {slides.map((_, i) => (
              <div
                key={i}
                className={`w-1.5 h-1.5 rounded-full transition-colors ${i === slide ? 'bg-[#4A5D4E]' : 'bg-[#E2E4E0]'}`}
              />
            ))}
          </div>
          <Button
            onClick={isLast ? finish : () => setSlide(slide + 1)}
            disabled={saving}
            className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-lg text-sm h-9 px-4"
            data-testid="guest-welcome-next"
          >
            {isLast ? 'Verstanden' : 'Weiter'}
            {!isLast && <ArrowRight className="w-3.5 h-3.5 ml-1.5" />}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
