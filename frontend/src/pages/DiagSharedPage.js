import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { useLanguage } from '../contexts/LanguageContext';
import {
  Smartphone, Camera, Send, CheckCircle2, XCircle, AlertTriangle, Loader2,
  Monitor, RefreshCw, Globe, Bell, Heart,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL || '';
const api = axios.create({ baseURL: `${API}/api` });

const StatusPill = ({ state, label }) => {
  const cfg = {
    ok:   { cls: 'bg-[#4A5D4E]/10 text-[#4A5D4E] border-[#4A5D4E]/30',   Icon: CheckCircle2 },
    warn: { cls: 'bg-[#D4A574]/15 text-[#8B6F47] border-[#D4A574]/40',   Icon: AlertTriangle },
    fail: { cls: 'bg-[#C87967]/15 text-[#C87967] border-[#C87967]/40',   Icon: XCircle },
    idle: { cls: 'bg-[#F3F4F1] text-[#6B7280] border-[#E2E4E0]',          Icon: Loader2 },
  }[state] || { cls: 'bg-[#F3F4F1] text-[#6B7280] border-[#E2E4E0]', Icon: Loader2 };
  return (
    <Badge className={`border ${cfg.cls} rounded-full px-2 py-0.5 text-[10px] font-medium inline-flex items-center gap-1 shrink-0`}>
      <cfg.Icon className={`w-3 h-3 ${state === 'idle' ? 'animate-spin' : ''}`} />
      {label || state.toUpperCase()}
    </Badge>
  );
};

const Row = ({ title, state, detail }) => (
  <div className="py-2.5 border-b border-[#E2E4E0] last:border-b-0" data-testid={`shared-diag-${title.replace(/\s+/g, '-').toLowerCase()}`}>
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-[#1C1F1D]">{title}</div>
        {detail && <div className="text-[11px] text-[#6B7280] mt-0.5 font-mono break-all">{detail}</div>}
      </div>
      <StatusPill state={state} />
    </div>
  </div>
);

export default function DiagSharedPage() {
  const { t } = useLanguage();
  const { token } = useParams();
  const [meta, setMeta] = useState({ loading: true });
  const [name, setName] = useState('');
  const [logs, setLogs] = useState([]);

  const [env, setEnv] = useState({
    secureCtx: null, network: { state: 'idle', detail: '—' },
    ua: navigator.userAgent,
  });
  const [cam, setCam] = useState({ state: 'idle', detail: '—' });
  const [mic, setMic] = useState({ state: 'idle', detail: '—' });
  const [screen, setScreen] = useState({ state: 'idle', detail: 'Nicht getestet' });
  const [webrtc, setWebrtc] = useState({ state: 'idle', detail: 'Nicht getestet' });
  const [push, setPush] = useState({ state: 'idle', detail: '—' });

  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');

  const log = (msg) => setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString('de-DE', { hour12: false })}] ${msg}`].slice(-30));

  // 1) Resolve token on mount
  useEffect(() => {
    api.get(`/diag/shared/${token}`)
      .then(({ data }) => {
        setMeta({ loading: false, ...data });
        log('Link gültig');
      })
      .catch((e) => {
        setMeta({ loading: false, invalid: true, detail: e?.response?.data?.detail || 'Link ungültig' });
      });

    const sec = window.isSecureContext;
    const conn = navigator.connection || {};
    const online = navigator.onLine;
    setEnv((p) => ({
      ...p,
      secureCtx: sec,
      network: { state: online ? 'ok' : 'fail', detail: online
        ? `online · ${conn.effectiveType || 'unknown'}${conn.downlink ? ` · ${conn.downlink} Mbit/s` : ''}`
        : 'offline' },
    }));
    setPush({
      state: !('Notification' in window) ? 'fail'
        : Notification.permission === 'granted' ? 'ok'
        : Notification.permission === 'denied' ? 'fail' : 'warn',
      detail: 'Notification' in window ? `permission: ${Notification.permission}` : 'Notification API nicht verfügbar',
    });
  }, [token]);

  // 2) Auto-run the non-invasive checks after a short delay
  useEffect(() => {
    if (meta.loading || meta.invalid) return;
    (async () => {
      await new Promise((r) => setTimeout(r, 500));
      // WebRTC ICE probe
      try {
        const pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
        const cands = [];
        await new Promise((resolve) => {
          pc.onicecandidate = (e) => { if (e.candidate) cands.push(e.candidate.candidate); if (!e.candidate) resolve(); };
          pc.createDataChannel('diag');
          pc.createOffer().then((o) => pc.setLocalDescription(o));
          setTimeout(resolve, 4000);
        });
        pc.close();
        setWebrtc({ state: cands.length > 0 ? 'ok' : 'fail',
          detail: cands.length > 0 ? `${cands.length} ICE-Kandidaten` : 'Keine ICE-Kandidaten (Firewall?)' });
        log(`WebRTC ICE: ${cands.length} Kandidaten`);
      } catch (e) {
        setWebrtc({ state: 'fail', detail: e.message });
      }
    })();
  }, [meta.loading, meta.invalid]);

  const testMedia = async () => {
    setCam({ state: 'idle', detail: 'Frage an …' });
    setMic({ state: 'idle', detail: 'Frage an …' });
    log('getUserMedia(audio+video) angefordert');
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
      const v = s.getVideoTracks()[0];
      const a = s.getAudioTracks()[0];
      setCam(v ? { state: 'ok', detail: `${v.label || 'unnamed'} · ${v.getSettings?.().width || '?'}×${v.getSettings?.().height || '?'}` }
             : { state: 'fail', detail: 'Kein Video-Track' });
      setMic(a ? { state: 'ok', detail: a.label || 'unnamed' } : { state: 'fail', detail: 'Kein Audio-Track' });
      s.getTracks().forEach((t) => t.stop());
      log('✓ Kamera & Mikrofon OK');
    } catch (e) {
      setCam({ state: 'fail', detail: `${e.name}: ${e.message}` });
      setMic({ state: 'fail', detail: `${e.name}: ${e.message}` });
      log(`✗ getUserMedia failed: ${e.name}`);
    }
  };

  const testScreen = async () => {
    try {
      if (!navigator.mediaDevices?.getDisplayMedia) {
        setScreen({ state: 'fail', detail: 'getDisplayMedia nicht unterstuetzt' });
        log('✗ getDisplayMedia fehlt (typisch iOS Safari)');
        return;
      }
      const s = await navigator.mediaDevices.getDisplayMedia({ video: true });
      setScreen({ state: 'ok', detail: 'Bildschirm OK' });
      s.getTracks().forEach((t) => t.stop());
    } catch (e) {
      setScreen({ state: 'fail', detail: e.message });
    }
  };

  const submit = async () => {
    setSubmitting(true);
    setError('');
    try {
      await api.post(`/diag/shared/${token}/submit`, {
        reporter_name: name || 'Anonym',
        user_agent: env.ua,
        results: {
          secureCtx: { state: env.secureCtx ? 'ok' : 'fail' },
          network: env.network,
          cam, mic, screen, webrtc, push,
        },
        logs,
      });
      setSubmitted(true);
      log('✓ Diagnose übertragen');
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setSubmitting(false);
    }
  };

  // ---- render ----

  if (meta.loading) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex items-center justify-center">
        <div className="text-sm text-[#6B7280] flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Prüfe Link …
        </div>
      </div>
    );
  }

  if (meta.invalid) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex items-center justify-center px-6">
        <Card className="max-w-md p-6 text-center bg-white border-[#E2E4E0]">
          <XCircle className="w-10 h-10 text-[#C87967] mx-auto mb-3" />
          <h1 className="text-lg font-semibold text-[#1C1F1D] mb-1">{t('linkInvalid')}</h1>
          <p className="text-sm text-[#6B7280]">{meta.detail}</p>
        </Card>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex items-center justify-center px-6">
        <Card className="max-w-md p-6 text-center bg-white border-[#E2E4E0]">
          <div className="w-14 h-14 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center mx-auto mb-3">
            <Heart className="w-7 h-7 text-[#4A5D4E]" />
          </div>
          <h1 className="text-lg font-semibold text-[#1C1F1D] mb-1">Vielen Dank!</h1>
          <p className="text-sm text-[#6B7280]">Die Diagnose wurde an {meta.created_by_name || 'den Admin'} übertragen. Du kannst das Fenster schließen.</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAF8] pb-24" data-testid="shared-diag-page">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 pt-6">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-full bg-[#4A5D4E]/10 flex items-center justify-center">
            <Smartphone className="w-5 h-5 text-[#4A5D4E]" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-[#1C1F1D]">{t('deviceDiagnostics')}</h1>
            <p className="text-xs text-[#6B7280] mt-0.5">
              Für <strong>{meta.created_by_name || 'Admin'}</strong>
              {meta.note && <> · „{meta.note}"</>}
            </p>
          </div>
        </div>

        <Card className="p-4 mb-4 bg-white border-[#E2E4E0]">
          <div className="flex items-center gap-2 mb-2">
            <Globe className="w-4 h-4 text-[#6B7280]" />
            <h2 className="text-sm font-semibold text-[#1C1F1D]">Umgebung</h2>
          </div>
          <Row title="HTTPS" state={env.secureCtx ? 'ok' : 'fail'} detail={env.secureCtx ? 'Sicher' : 'Unsicher'} />
          <Row title="Netzwerk" state={env.network.state} detail={env.network.detail} />
          <Row title="Gerät" state={/iPhone|iPad|Android/.test(env.ua) ? 'ok' : 'warn'} detail={env.ua} />
        </Card>

        <Card className="p-4 mb-4 bg-white border-[#E2E4E0]">
          <div className="flex items-center gap-2 mb-2">
            <Camera className="w-4 h-4 text-[#6B7280]" />
            <h2 className="text-sm font-semibold text-[#1C1F1D]">Kamera, Mikrofon &amp; WebRTC</h2>
          </div>
          <Row title="Kamera" state={cam.state} detail={cam.detail} />
          <Row title="Mikrofon" state={mic.state} detail={mic.detail} />
          <Row title="Bildschirm" state={screen.state} detail={screen.detail} />
          <Row title="WebRTC" state={webrtc.state} detail={webrtc.detail} />
          <div className="mt-3 flex gap-2 flex-wrap">
            <Button onClick={testMedia} size="sm" className="bg-[#4A5D4E] hover:bg-[#3A4A3E] text-white rounded-full" data-testid="shared-test-media">
              <Camera className="w-4 h-4 mr-1.5" /> Cam &amp; Mic testen
            </Button>
            <Button onClick={testScreen} size="sm" variant="outline" className="rounded-full" data-testid="shared-test-screen">
              <Monitor className="w-4 h-4 mr-1.5" /> Bildschirm testen
            </Button>
          </div>
        </Card>

        <Card className="p-4 mb-4 bg-white border-[#E2E4E0]">
          <div className="flex items-center gap-2 mb-2">
            <Bell className="w-4 h-4 text-[#6B7280]" />
            <h2 className="text-sm font-semibold text-[#1C1F1D]">Benachrichtigungen</h2>
          </div>
          <Row title="Notification-Permission" state={push.state} detail={push.detail} />
        </Card>

        <Card className="p-4 bg-white border-[#E2E4E0]">
          <h2 className="text-sm font-semibold text-[#1C1F1D] mb-2">{t('sendDiagnostics')}</h2>
          <p className="text-xs text-[#6B7280] mb-3">
            Dein Name (optional) hilft dem Admin dich zuzuordnen. Ergebnisse werden als anonymisierter
            technischer Bericht übertragen.
          </p>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('yourNameOptional')}
            className="mb-3"
            data-testid="shared-diag-name"
          />
          {error && (
            <div className="text-xs text-[#C87967] bg-[#C87967]/10 rounded-md p-2 mb-3 border border-[#C87967]/30">
              {error}
            </div>
          )}
          <Button
            onClick={submit}
            disabled={submitting}
            className="w-full bg-[#4A5D4E] hover:bg-[#3A4A3E] text-white rounded-full"
            data-testid="shared-diag-submit"
          >
            {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
            Diagnose an Admin senden
          </Button>
          {/iPhone|iPad|iPod/.test(env.ua) && (
            <div className="mt-3 text-[10px] text-[#8B6F47] bg-[#FAF7F2] border border-[#D4A574]/30 rounded-md p-2 flex items-start gap-1.5">
              <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
              <span>iOS Tipp: Für vollen Kamera-Zugriff bitte in Safari öffnen (nicht In-App-Browser).</span>
            </div>
          )}
        </Card>

        <p className="text-[10px] text-[#9CA3AF] text-center mt-3">MeetFlow · Shared Diag</p>
      </div>
    </div>
  );
}
