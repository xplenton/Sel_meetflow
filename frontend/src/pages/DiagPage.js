import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api, { API_URL } from '../lib/api';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { useLanguage } from '../contexts/LanguageContext';
import {
  Smartphone, Camera, Mic, Wifi, Bell, Lock, Video, CheckCircle2, XCircle,
  AlertTriangle, Loader2, Monitor, Copy, RefreshCw, Globe, QrCode, Link2,
  Download, Trash2, FileText,
} from 'lucide-react';

// ---------- small UI pieces ----------

const StatusPill = ({ state, label }) => {
  const cfg = {
    ok:    { cls: 'bg-[#4A5D4E]/10 text-[#4A5D4E] border-[#4A5D4E]/30',   Icon: CheckCircle2 },
    warn:  { cls: 'bg-[#D4A574]/15 text-[#8B6F47] border-[#D4A574]/40',   Icon: AlertTriangle },
    fail:  { cls: 'bg-[#C87967]/15 text-[#C87967] border-[#C87967]/40',   Icon: XCircle },
    idle:  { cls: 'bg-[#F3F4F1] text-[#6B7280] border-[#E2E4E0]',         Icon: Loader2 },
  }[state] || { cls: 'bg-[#F3F4F1] text-[#6B7280] border-[#E2E4E0]', Icon: Loader2 };
  return (
    <Badge className={`border ${cfg.cls} rounded-full px-2 py-0.5 text-[10px] font-medium inline-flex items-center gap-1 shrink-0`}>
      <cfg.Icon className={`w-3 h-3 ${state === 'idle' ? 'animate-spin' : ''}`} />
      {label}
    </Badge>
  );
};

const DiagRow = ({ title, state, detail, stateLabel, children }) => (
  <div className="py-3 border-b border-[#E2E4E0] last:border-b-0" data-testid={`diag-row-${title.replace(/\s+/g, '-').toLowerCase()}`}>
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-[#1C1F1D]">{title}</div>
        {detail && <div className="text-[11px] text-[#6B7280] mt-0.5 font-mono break-all">{detail}</div>}
      </div>
      <StatusPill state={state} label={stateLabel || state.toUpperCase()} />
    </div>
    {children && <div className="mt-2 pl-0">{children}</div>}
  </div>
);

// ---------- main page ----------

export default function DiagPage() {
  const { t } = useLanguage();
  const [ua, setUa] = useState('');
  const [secureCtx, setSecureCtx] = useState(null);
  const [mediaState, setMediaState] = useState({ state: 'idle', detail: 'Nicht gestartet' });
  const [camState, setCamState] = useState({ state: 'idle', detail: '—' });
  const [micState, setMicState] = useState({ state: 'idle', detail: '—' });
  const [screenState, setScreenState] = useState({ state: 'idle', detail: 'Tippe testen' });
  const [pushState, setPushState] = useState({ state: 'idle', detail: 'Prüfe …' });
  const [vapidState, setVapidState] = useState({ state: 'idle', detail: 'Prüfe …' });
  const [subState, setSubState] = useState({ state: 'idle', detail: 'Prüfe …' });
  const [netState, setNetState] = useState({ state: 'idle', detail: 'Prüfe …' });
  const [iceState, setIceState] = useState({ state: 'idle', detail: 'Noch nicht getestet' });
  const [logs, setLogs] = useState([]);
  const [sendingTest, setSendingTest] = useState(false);

  // ---- Admin Tools (only rendered for admin/moderator) ----
  const { user } = useAuth() || {};
  const isAdmin = user?.role === 'admin' || user?.role === 'moderator';
  const [shareTokens, setShareTokens] = useState([]);
  const [shareNote, setShareNote] = useState('');
  const [shareDays, setShareDays] = useState(7);
  const [creatingShare, setCreatingShare] = useState(false);
  const [shareError, setShareError] = useState('');

  const log = (msg) => {
    const ts = new Date().toLocaleTimeString('de-DE', { hour12: false });
    setLogs((prev) => [...prev, `[${ts}] ${msg}`].slice(-40));
  };

  // ---------- static checks on mount ----------
  useEffect(() => {
    setUa(navigator.userAgent);
    const sec = window.isSecureContext;
    setSecureCtx(sec);
    log(`Page loaded — secureContext=${sec}`);

    const online = navigator.onLine;
    const conn = navigator.connection || {};
    setNetState({
      state: online ? 'ok' : 'fail',
      detail: online
        ? `online · ${conn.effectiveType || 'unknown'}${conn.downlink ? ` · ${conn.downlink} Mbit/s` : ''}`
        : 'offline',
    });

    // Push & Notification API
    if (!('Notification' in window)) {
      setPushState({ state: 'fail', detail: 'Notification API nicht verfügbar' });
    } else if (!('serviceWorker' in navigator)) {
      setPushState({ state: 'fail', detail: 'Service Worker nicht verfügbar' });
    } else if (!('PushManager' in window)) {
      setPushState({ state: 'fail', detail: 'Push Manager nicht verfügbar' });
    } else {
      const perm = Notification.permission;
      setPushState({
        state: perm === 'granted' ? 'ok' : perm === 'denied' ? 'fail' : 'warn',
        detail: `Notification permission: ${perm}`,
      });
    }

    // Fetch VAPID key + subscription status (auth is via HTTP-only cookie)
    api.get('/news/push/vapid-public-key')
      .then((r) => {
        const k = r.data?.public_key || r.data?.publicKey || '';
        setVapidState({ state: k ? 'ok' : 'warn', detail: k ? `${k.slice(0, 24)}…` : 'Kein Key konfiguriert' });
      })
      .catch((e) => setVapidState({ state: 'fail', detail: e?.response?.data?.detail || e.message }));
    api.get('/news/push/status')
      .then((r) => {
        const sub = r.data?.subscribed;
        setSubState({ state: sub ? 'ok' : 'warn', detail: sub ? 'Gerät registriert' : 'Nicht registriert' });
      })
      .catch((e) => setSubState({ state: 'fail', detail: e?.response?.data?.detail || e.message }));
  }, []);

  // Load share-tokens for admin tools (only for admin/moderator)
  useEffect(() => {
    if (!isAdmin) return;
    api.get('/diag/shared')
      .then(({ data }) => setShareTokens(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, [isAdmin]);

  const createShareLink = async () => {
    setCreatingShare(true);
    setShareError('');
    try {
      const { data } = await api.post('/diag/shared', { note: shareNote, days: shareDays });
      setShareTokens((prev) => [data, ...prev]);
      setShareNote('');
      log(`✓ Shareable Diag-Link erstellt: ${data.token.slice(0, 8)}…`);
    } catch (e) {
      setShareError(e?.response?.data?.detail || e.message);
    } finally {
      setCreatingShare(false);
    }
  };

  const revokeShareLink = async (token) => {
    if (!window.confirm('Link widerrufen? Gesendete QR-Codes funktionieren danach nicht mehr.')) return;
    try {
      await api.delete(`/diag/shared/${token}`);
      setShareTokens((prev) => prev.filter((x) => x.token !== token));
    } catch (e) {
      setShareError(e?.response?.data?.detail || e.message);
    }
  };

  const copyShareUrl = async (url) => {
    try {
      await navigator.clipboard.writeText(url);
      log('📋 Link kopiert');
    } catch {
      log('✗ Clipboard failed');
    }
  };

  const exportPosts = (fmt) => {
    // Opens endpoint in new tab — browser handles the download via Content-Disposition
    const url = `${API_URL}/api/news/export/posts?fmt=${fmt}`;
    window.open(url, '_blank', 'noopener');
    log(`⇣ Posts-Export (${fmt}) angefragt`);
  };

  // ---------- interactive tests ----------
  const testMedia = async () => {
    setMediaState({ state: 'idle', detail: 'Frage Berechtigung an …' });
    log('getUserMedia({audio, video}) requested');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      const vid = stream.getVideoTracks()[0];
      const aud = stream.getAudioTracks()[0];
      setCamState(vid
        ? { state: 'ok', detail: `${vid.label || 'unnamed'} · ${vid.getSettings?.().width || '?'}×${vid.getSettings?.().height || '?'}` }
        : { state: 'fail', detail: 'Kein Video-Track' });
      setMicState(aud
        ? { state: 'ok', detail: aud.label || 'unnamed' }
        : { state: 'fail', detail: 'Kein Audio-Track' });
      setMediaState({ state: 'ok', detail: 'Berechtigung erteilt' });
      log(`✓ getUserMedia OK — video=${!!vid} audio=${!!aud}`);
      stream.getTracks().forEach((t) => t.stop());
    } catch (e) {
      setMediaState({ state: 'fail', detail: `${e.name}: ${e.message}` });
      setCamState({ state: 'fail', detail: e.name === 'NotAllowedError' ? 'Berechtigung verweigert' : e.message });
      setMicState({ state: 'fail', detail: e.name === 'NotAllowedError' ? 'Berechtigung verweigert' : e.message });
      log(`✗ getUserMedia failed — ${e.name}: ${e.message}`);
    }
  };

  const testScreenShare = async () => {
    setScreenState({ state: 'idle', detail: 'Frage Berechtigung an …' });
    log('getDisplayMedia() requested');
    try {
      if (!navigator.mediaDevices?.getDisplayMedia) {
        setScreenState({ state: 'fail', detail: 'getDisplayMedia nicht unterstützt (iOS Safari)' });
        log('✗ getDisplayMedia not available — iOS Safari blocks this');
        return;
      }
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      setScreenState({ state: 'ok', detail: 'Bildschirmfreigabe OK' });
      log('✓ getDisplayMedia OK');
      stream.getTracks().forEach((t) => t.stop());
    } catch (e) {
      setScreenState({ state: 'fail', detail: `${e.name}: ${e.message}` });
      log(`✗ getDisplayMedia failed — ${e.name}: ${e.message}`);
    }
  };

  const testWebRTC = async () => {
    setIceState({ state: 'idle', detail: 'Sammle ICE-Kandidaten …' });
    log('Testing WebRTC peer-connection with Google STUN');
    try {
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
      });
      const candidates = [];
      let timer;
      await new Promise((resolve) => {
        pc.onicecandidate = (e) => {
          if (e.candidate) candidates.push(e.candidate.candidate);
          if (!e.candidate) resolve();
        };
        pc.createDataChannel('diag');
        pc.createOffer().then((o) => pc.setLocalDescription(o));
        timer = setTimeout(resolve, 5000);
      });
      clearTimeout(timer);
      pc.close();
      const types = [...new Set(candidates.map((c) => c.split(' ')[7]))];
      setIceState({
        state: candidates.length > 0 ? 'ok' : 'fail',
        detail: candidates.length > 0
          ? `${candidates.length} Kandidaten · Typen: ${types.join(', ')}`
          : 'Keine ICE-Kandidaten (Firewall?)',
      });
      log(`✓ WebRTC ICE — ${candidates.length} candidates`);
    } catch (e) {
      setIceState({ state: 'fail', detail: `${e.name}: ${e.message}` });
      log(`✗ WebRTC failed — ${e.message}`);
    }
  };

  const requestPushPermission = async () => {
    if (!('Notification' in window)) return;
    log('Notification.requestPermission()');
    const perm = await Notification.requestPermission();
    setPushState({
      state: perm === 'granted' ? 'ok' : perm === 'denied' ? 'fail' : 'warn',
      detail: `Notification permission: ${perm}`,
    });
    log(`Permission result: ${perm}`);
  };

  const sendTestPush = async () => {
    setSendingTest(true);
    try {
      const { data } = await api.post('/news/push/test', {});
      log(`✓ Test-Push versendet — sent=${data?.result?.sent} errors=${data?.result?.errors}`);
    } catch (e) {
      log(`✗ Test-Push fehlgeschlagen — ${e.response?.data?.detail || e.message}`);
    } finally {
      setSendingTest(false);
    }
  };

  const copyDiag = async () => {
    const payload = [
      `MeetFlow Diagnose — ${new Date().toISOString()}`,
      `UserAgent: ${ua}`,
      `SecureContext: ${secureCtx}`,
      `Network: ${netState.detail}`,
      `Camera: ${camState.state} — ${camState.detail}`,
      `Mic: ${micState.state} — ${micState.detail}`,
      `ScreenShare: ${screenState.state} — ${screenState.detail}`,
      `Push: ${pushState.state} — ${pushState.detail}`,
      `VAPID: ${vapidState.state} — ${vapidState.detail}`,
      `PushSubscription: ${subState.state} — ${subState.detail}`,
      `WebRTC ICE: ${iceState.state} — ${iceState.detail}`,
      '',
      'Logs:',
      ...logs,
    ].join('\n');
    try {
      await navigator.clipboard.writeText(payload);
      log('📋 Diagnose kopiert');
    } catch {
      log('✗ Clipboard fehlgeschlagen — lange drücken um Text zu markieren');
    }
  };

  return (
    <div className="min-h-screen bg-[#FAFAF8] pb-24" data-testid="diag-page">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 pt-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center">
            <Smartphone className="w-5 h-5 text-[#4A5D4E]" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[#1C1F1D]">{t('deviceDiagnosticsPage')}</h1>
            <p className="text-xs text-[#6B7280] mt-0.5">Hilft iPhone/Android-Probleme bei WebRTC &amp; Push zu finden</p>
          </div>
        </div>

        {/* Environment */}
        <Card className="p-4 mb-4 bg-white border-[#E2E4E0]">
          <div className="flex items-center gap-2 mb-2">
            <Globe className="w-4 h-4 text-[#6B7280]" />
            <h2 className="text-sm font-semibold text-[#1C1F1D]">Umgebung</h2>
          </div>
          <DiagRow
            title="Sicherer Kontext"
            state={secureCtx ? 'ok' : 'fail'}
            stateLabel={secureCtx ? 'HTTPS' : 'UNSICHER'}
            detail={secureCtx
              ? 'HTTPS aktiv — getUserMedia & Push erlaubt'
              : 'HTTPS fehlt — iOS blockiert Camera/Push ohne HTTPS'}
          />
          <DiagRow title="Netzwerk" state={netState.state} detail={netState.detail} />
          <DiagRow
            title="User-Agent"
            state={/iPhone|iPad|iPod/.test(ua) ? 'warn' : 'ok'}
            stateLabel={/iPhone|iPad|iPod/.test(ua) ? 'iOS' : 'OK'}
            detail={ua}
          />
        </Card>

        {/* Media / WebRTC */}
        <Card className="p-4 mb-4 bg-white border-[#E2E4E0]">
          <div className="flex items-center gap-2 mb-2">
            <Video className="w-4 h-4 text-[#6B7280]" />
            <h2 className="text-sm font-semibold text-[#1C1F1D]">Kamera, Mikrofon &amp; WebRTC</h2>
          </div>
          <DiagRow title="getUserMedia" state={mediaState.state} detail={mediaState.detail} />
          <DiagRow title="Kamera" state={camState.state} detail={camState.detail} />
          <DiagRow title="Mikrofon" state={micState.state} detail={micState.detail} />
          <DiagRow title="Bildschirmfreigabe" state={screenState.state} detail={screenState.detail} />
          <DiagRow title="WebRTC ICE" state={iceState.state} detail={iceState.detail} />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button onClick={testMedia} size="sm" className="bg-[#4A5D4E] hover:bg-[#3A4A3E] text-white rounded-full" data-testid="diag-test-media">
              <Camera className="w-4 h-4 mr-1.5" /> Cam &amp; Mic
            </Button>
            <Button onClick={testScreenShare} size="sm" variant="outline" className="rounded-full" data-testid="diag-test-screen">
              <Monitor className="w-4 h-4 mr-1.5" /> Bildschirm
            </Button>
            <Button onClick={testWebRTC} size="sm" variant="outline" className="rounded-full" data-testid="diag-test-webrtc">
              <RefreshCw className="w-4 h-4 mr-1.5" /> WebRTC
            </Button>
          </div>
        </Card>

        {/* Push */}
        <Card className="p-4 mb-4 bg-white border-[#E2E4E0]">
          <div className="flex items-center gap-2 mb-2">
            <Bell className="w-4 h-4 text-[#6B7280]" />
            <h2 className="text-sm font-semibold text-[#1C1F1D]">{t('pushNotifications')}</h2>
          </div>
          <DiagRow title="Notification Permission" state={pushState.state} detail={pushState.detail} />
          <DiagRow title="VAPID Public Key" state={vapidState.state} detail={vapidState.detail} />
          <DiagRow title="Push-Subscription" state={subState.state} detail={subState.detail} />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button onClick={requestPushPermission} size="sm" className="bg-[#4A5D4E] hover:bg-[#3A4A3E] text-white rounded-full" data-testid="diag-request-push">
              <Lock className="w-4 h-4 mr-1.5" /> Berechtigung anfragen
            </Button>
            <Button onClick={sendTestPush} disabled={sendingTest} size="sm" variant="outline" className="rounded-full" data-testid="diag-send-test-push">
              {sendingTest ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Bell className="w-4 h-4 mr-1.5" />}
              Test-Push senden
            </Button>
          </div>
          {/iPhone|iPad|iPod/.test(ua) && (
            <div className="mt-3 p-3 rounded-md bg-[#FAF7F2] border border-[#D4A574]/30 text-xs text-[#8B6F47]">
              <div className="font-medium mb-1 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> iOS Hinweis</div>
              Push funktioniert auf iOS 16.4+ nur als <strong>PWA zum Home-Bildschirm</strong>. Tippe unten <strong>Teilen</strong> → <strong>Zum Home-Bildschirm</strong>, öffne die App von dort, logge dich erneut ein und aktiviere Push.
            </div>
          )}
        </Card>

        {/* Admin Tools — visible only to admin/moderator */}
        {isAdmin && (
          <Card className="p-4 mb-4 bg-white border-[#E2E4E0]" data-testid="admin-tools-panel">
            <div className="flex items-center gap-2 mb-3">
              <Lock className="w-4 h-4 text-[#6B7280]" />
              <h2 className="text-sm font-semibold text-[#1C1F1D]">Admin-Tools</h2>
            </div>

            {/* Posts export quick-actions */}
            <div className="pb-3 mb-3 border-b border-[#E2E4E0]">
              <div className="flex items-center gap-2 mb-1.5">
                <FileText className="w-3.5 h-3.5 text-[#6B7280]" />
                <span className="text-xs font-medium text-[#1C1F1D]">News-Posts exportieren</span>
              </div>
              <p className="text-[11px] text-[#6B7280] mb-2">
                {t('fullExportForAudit')}
              </p>
              <div className="flex gap-2 flex-wrap">
                <Button onClick={() => exportPosts('csv')} size="sm" variant="outline" className="rounded-full" data-testid="export-posts-csv">
                  <Download className="w-3.5 h-3.5 mr-1.5" /> CSV
                </Button>
                <Button onClick={() => exportPosts('json')} size="sm" variant="outline" className="rounded-full" data-testid="export-posts-json">
                  <Download className="w-3.5 h-3.5 mr-1.5" /> JSON
                </Button>
              </div>
            </div>

            {/* Shareable Diag-Link creator */}
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <QrCode className="w-3.5 h-3.5 text-[#6B7280]" />
                <span className="text-xs font-medium text-[#1C1F1D]">Shareable Diagnose-Link</span>
              </div>
              <p className="text-[11px] text-[#6B7280] mb-2">
                Sende einem Mitarbeiter einen QR-Code. Er öffnet automatisch eine Diagnose-Seite
                (ohne Login) und sendet die Ergebnisse zurück an dich.
              </p>
              <div className="flex gap-2 mb-2 flex-wrap">
                <Input
                  value={shareNote}
                  onChange={(e) => setShareNote(e.target.value)}
                  placeholder="Notiz (z. B. 'Station 3 iPhone')"
                  className="flex-1 text-xs h-9 min-w-[160px]"
                  maxLength={200}
                  data-testid="share-note-input"
                />
                <Input
                  type="number"
                  min="1" max="30"
                  value={shareDays}
                  onChange={(e) => setShareDays(parseInt(e.target.value || '7', 10))}
                  className="w-20 text-xs h-9"
                  data-testid="share-days-input"
                />
                <Button
                  onClick={createShareLink}
                  disabled={creatingShare}
                  size="sm"
                  className="bg-[#4A5D4E] hover:bg-[#3A4A3E] text-white rounded-full"
                  data-testid="create-share-link"
                >
                  {creatingShare ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <QrCode className="w-3.5 h-3.5 mr-1.5" />}
                  Erstellen
                </Button>
              </div>
              {shareError && (
                <div className="text-[11px] text-[#C87967] bg-[#C87967]/10 border border-[#C87967]/30 rounded px-2 py-1 mb-2">
                  {shareError}
                </div>
              )}
              {shareTokens.length === 0 && (
                <p className="text-[11px] text-[#9CA3AF] italic mt-2">{t('noLinksCreatedYet')}</p>
              )}
              {shareTokens.map((tok) => (
                <div key={tok.token} className="p-3 rounded-md border border-[#E2E4E0] bg-[#FAFAF8] mb-2" data-testid={`share-token-row-${tok.token.slice(0, 6)}`}>
                  <div className="flex items-start gap-3">
                    {tok.qr_png && (
                      <img src={tok.qr_png} alt="QR" className="w-16 h-16 shrink-0 rounded bg-white border border-[#E2E4E0]" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-[#1C1F1D] truncate">{tok.note || '(keine Notiz)'}</div>
                      <div className="text-[10px] text-[#6B7280] font-mono truncate mt-0.5">
                        {tok.share_url || `${window.location.origin}/diag/shared/${tok.token}`}
                      </div>
                      <div className="text-[10px] text-[#9CA3AF] mt-1">
                        {(tok.submissions || []).length > 0
                          ? `${tok.submissions.length} Einreichung(en) · läuft ab ${(tok.expires_at || '').slice(0, 10)}`
                          : `Keine Einreichungen · läuft ab ${(tok.expires_at || '').slice(0, 10)}`}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1 shrink-0">
                      <Button
                        onClick={() => copyShareUrl(tok.share_url || `${window.location.origin}/diag/shared/${tok.token}`)}
                        size="sm" variant="ghost" className="h-7 px-2 text-xs"
                        data-testid={`copy-share-${tok.token.slice(0, 6)}`}
                      >
                        <Link2 className="w-3 h-3 mr-1" /> Link
                      </Button>
                      <Button
                        onClick={() => revokeShareLink(tok.token)}
                        size="sm" variant="ghost" className="h-7 px-2 text-xs text-[#C87967] hover:text-[#C87967] hover:bg-[#C87967]/10"
                        data-testid={`revoke-share-${tok.token.slice(0, 6)}`}
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                  {(tok.submissions || []).length > 0 && (
                    <details className="mt-2">
                      <summary className="text-[11px] text-[#4A5D4E] cursor-pointer select-none">{t('viewSubmissions')}</summary>
                      <div className="mt-2 space-y-1.5">
                        {tok.submissions.map((s, i) => (
                          <div key={i} className="p-2 rounded bg-white border border-[#E2E4E0] text-[10px] font-mono">
                            <div className="text-[#1C1F1D] font-sans text-xs mb-1">
                              {s.reporter_name} — <span className="text-[#9CA3AF] font-normal">{(s.submitted_at || '').slice(0, 19).replace('T', ' ')}</span>
                            </div>
                            <div className="text-[#6B7280] break-all">UA: {s.user_agent}</div>
                            <div className="text-[#6B7280]">
                              {Object.entries(s.results || {}).map(([k, v]) => (
                                <span key={k} className={`inline-block mr-2 ${v?.state === 'ok' ? 'text-[#4A5D4E]' : v?.state === 'fail' ? 'text-[#C87967]' : 'text-[#8B6F47]'}`}>
                                  {k}:{v?.state || '?'}
                                </span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Logs */}
        <Card className="p-4 mb-4 bg-white border-[#E2E4E0]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Wifi className="w-4 h-4 text-[#6B7280]" />
              <h2 className="text-sm font-semibold text-[#1C1F1D]">Live-Log</h2>
            </div>
            <Button onClick={copyDiag} size="sm" variant="outline" className="rounded-full" data-testid="diag-copy-report">
              <Copy className="w-4 h-4 mr-1.5" /> Kopieren
            </Button>
          </div>
          <pre className="text-[10px] leading-relaxed font-mono text-[#6B7280] bg-[#F9F9F8] p-2 rounded max-h-48 overflow-auto whitespace-pre-wrap break-all" data-testid="diag-log">
            {logs.length === 0 ? '— noch keine Einträge —' : logs.join('\n')}
          </pre>
        </Card>

        <p className="text-[10px] text-[#9CA3AF] text-center mt-2">MeetFlow · Diagnose v1</p>
      </div>
    </div>
  );
}
