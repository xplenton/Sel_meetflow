import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useLocation } from 'react-router-dom';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { LayoutDashboard, Newspaper, MessageCircle, Video, CircleDot, Keyboard, Sparkles } from 'lucide-react';
import api from '../lib/api';

const STORAGE_KEY = 'meetflow:onboarding:v1';

const STEPS = [
  { icon: Sparkles, title: 'Willkommen bei MeetFlow', body: 'Ein Rundgang durch die wichtigsten Bereiche - dauert unter 30 Sekunden.', color: '#4A5D4E' },
  { icon: LayoutDashboard, title: 'Dashboard', body: 'Dein Startpunkt. Hier siehst du Agenda, offene Meldungen, Pflicht-News und kannst Fokus-Zeit planen.', color: '#4A5D4E' },
  { icon: Newspaper, title: 'News & Mitteilungen', body: 'Lies wichtige Klinik-News. Pflicht-Beitraege erkennst du am roten Rand. Du kannst kommentieren, reagieren und Fragen stellen.', color: '#D4A373' },
  { icon: MessageCircle, title: 'Chat', body: 'Schreibe Kollegen direkt oder in Gruppen. Dateien, Sprache, Video-Call - alles inklusive. Siehe live wer online ist.', color: '#6B8E23' },
  { icon: Video, title: 'Webkonferenz', body: 'Sofort-Meetings starten oder Termine planen. Waehrend eines Calls bist du automatisch auf "Nicht stoeren".', color: '#C87967' },
  { icon: CircleDot, title: 'Status & DND', body: 'Unten links in der Sidebar setzt du deinen Status. "Nicht stoeren" kannst du auch nur für 30 Min oder bis zu einer bestimmten Uhrzeit aktivieren.', color: '#D4A373' },
  { icon: Keyboard, title: 'Shortcuts', body: 'Strg/Cmd+K oeffnet die globale Suche. Tippe "g" + "n" für News, "g" + "c" für Chat, "g" + "m" für Meetings.', color: '#4A5D4E' },
];

export default function OnboardingTour() {
  const { user } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  // Iter 378 — synchron checken ob Onboarding bereits in localStorage als
  // gesehen markiert ist (für jeden bekannten User). Wenn ja, NIE öffnen —
  // verhindert das kurze Aufblitzen des Dialogs nach 1.5s auf jedem Reload,
  // wenn der Server `onboarding_completed_at` noch nicht zurückgegeben hat
  // (Race: useEffect mit user-Update läuft schneller als `/auth/me`).
  useEffect(() => {
    if (!user?.user_id) return;
    // Skip during auth flow/public routes
    const publicPaths = ['/login', '/register', '/forgot', '/reset', '/auth/callback', '/book/', '/survey/', '/sign/', '/polls/', '/unsubscribe/'];
    if (publicPaths.some(p => location.pathname.startsWith(p))) return;
    // Server-side completion flag wins over localStorage (survives device changes)
    if (user.onboarding_completed_at) return;
    try {
      const key = `${STORAGE_KEY}:${user.user_id}`;
      const seen = localStorage.getItem(key);
      if (seen) return; // already dismissed on this device
      // Delay a bit to let app settle
      const t = setTimeout(() => setOpen(true), 1500);
      return () => clearTimeout(t);
    } catch {}
  }, [user, location.pathname]);

  const finish = () => {
    try { localStorage.setItem(`${STORAGE_KEY}:${user.user_id}`, new Date().toISOString()); } catch {}
    // Persist serverside so it survives device/browser changes
    api.post('/users/me/onboarding-complete').catch(() => {});
    setOpen(false);
    setStep(0);
  };

  const s = STEPS[step];
  if (!s) return null;
  const Icon = s.icon;
  const isLast = step === STEPS.length - 1;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) finish(); }}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="sr-only">Onboarding Tour</DialogTitle>
          <DialogDescription className="sr-only">Kurze Einfuehrung in MeetFlow</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col items-center text-center py-4" data-testid="onboarding-tour">
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4" style={{ backgroundColor: `${s.color}15` }}>
            <Icon className="w-7 h-7" style={{ color: s.color }} />
          </div>
          <h3 className="text-lg font-medium text-[#1C1F1D] mb-2" style={{ fontFamily: 'Manrope' }}>{s.title}</h3>
          <p className="text-sm text-[#6B7280] leading-relaxed max-w-[380px]">{s.body}</p>
          <div className="flex gap-1 mt-5">
            {STEPS.map((_, i) => (
              <span key={i} className={`h-1 rounded-full transition-all ${i === step ? 'w-6 bg-[#4A5D4E]' : 'w-2 bg-[#E2E4E0]'}`} />
            ))}
          </div>
          <div className="flex items-center justify-between w-full mt-6">
            <button onClick={finish} className="text-xs text-[#9CA3AF] hover:text-[#6B7280]" data-testid="onboarding-skip">
              Überspringen
            </button>
            <div className="flex gap-2">
              {step > 0 && (
                <Button variant="outline" size="sm" onClick={() => setStep(s => s - 1)} className="rounded-full border-[#E2E4E0]">
                  Zurück
                </Button>
              )}
              <Button size="sm" onClick={() => isLast ? finish() : setStep(s => s + 1)}
                className="bg-[#4A5D4E] hover:bg-[#3E4E42] text-white rounded-full"
                data-testid={isLast ? 'onboarding-done' : 'onboarding-next'}>
                {isLast ? 'Loslegen' : 'Weiter'}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
