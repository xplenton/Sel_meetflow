import { useState, useRef, useEffect } from 'react';
import { useStatus, STATUS_CFG } from '../contexts/StatusContext';
import { useLanguage } from '../contexts/LanguageContext';
import { subscribeConnectionState, getConnectionState, CONN_STATE } from '../lib/wsConnectionState';
import StatusDot from './chat/StatusDot';
import { ChevronDown, Clock, WifiOff, Wifi, Loader2 } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

/**
 * Global status picker for the Sidebar.
 *
 * iter 128: merged the former `ConnectionStatusIndicator` pill into this
 * picker. Rationale: showing two separate pills ("Online" + "Erreichbar")
 * was confusing — users couldn't tell what the difference was. Now:
 *
 *   - If WebSocket is OPEN → show the presence state verbatim (Online /
 *     Away / DnD / Offline) — no extra clutter.
 *   - If WebSocket is RECONNECTING/CONNECTING → show a spinner pulse +
 *     "Verbinde..." appended. User knows they may briefly miss events.
 *   - If WebSocket is OFFLINE → status label gets greyed out + WifiOff icon,
 *     hovering shows a tooltip explaining anrufe/nachrichten kommen nicht an.
 */
const STATUS_KEY_MAP = {
  online: 'statusOnline',
  away: 'statusAway',
  dnd: 'statusDnd',
  offline: 'statusOffline',
};

export default function StatusPicker() {
  const { t, language } = useLanguage();
  const { myStatus, setStatus } = useStatus();
  const [open, setOpen] = useState(false);
  const [dndUntil, setDndUntil] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [customTime, setCustomTime] = useState('');
  const [connState, setConnState] = useState(getConnectionState());
  const ref = useRef(null);

  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  useEffect(() => subscribeConnectionState(setConnState), []);

  useEffect(() => {
    let cancelled = false;
    if (myStatus === 'dnd') {
      api.get('/chat/my-status')
        .then(({ data }) => { if (!cancelled) setDndUntil(data?.dnd_until || null); })
        .catch(() => {});
    } else if (dndUntil) { setDndUntil(null); }
    const tick = setInterval(() => setNow(Date.now()), 30000);
    return () => { cancelled = true; clearInterval(tick); };
  }, [myStatus, dndUntil]);

  const cfg = STATUS_CFG[myStatus] || STATUS_CFG.offline;
  const statusLabel = t(STATUS_KEY_MAP[myStatus] || 'statusOffline');
  const isConnecting = connState === CONN_STATE.CONNECTING || connState === CONN_STATE.RECONNECTING;
  const isOffline = connState === CONN_STATE.OFFLINE;

  const applyDndFor = async (minutes) => {
    const until = new Date(Date.now() + minutes * 60 * 1000).toISOString();
    try {
      await api.put('/chat/my-status', { status_mode: 'dnd', dnd_until: until });
      setDndUntil(until); setOpen(false);
      const label = minutes === 30
        ? t('dndFor30Min') : minutes === 60
        ? t('dndFor1Hr') : t('dndForNHours').replace('{n}', Math.round(minutes / 60));
      toast.success(label);
      window.dispatchEvent(new Event('status:refresh'));
    } catch { toast.error(t('error')); }
  };

  const applyDndUntilCustom = async () => {
    if (!customTime) return;
    const [hh, mm] = customTime.split(':').map(Number);
    const target = new Date(); target.setHours(hh, mm, 0, 0);
    if (target.getTime() <= Date.now()) target.setDate(target.getDate() + 1);
    const until = target.toISOString();
    try {
      await api.put('/chat/my-status', { status_mode: 'dnd', dnd_until: until });
      setDndUntil(until); setOpen(false); setCustomTime('');
      const label = target.toLocaleTimeString(language === 'de' ? 'de-DE' : 'en-US', { hour: '2-digit', minute: '2-digit' });
      toast.success(`${t('dndUntil')} ${label}`);
      window.dispatchEvent(new Event('status:refresh'));
    } catch { toast.error(t('error')); }
  };

  const remainingLabel = () => {
    if (myStatus !== 'dnd' || !dndUntil) return null;
    const ms = new Date(dndUntil).getTime() - now;
    if (ms <= 0) return null;
    const min = Math.ceil(ms / 60000);
    if (min < 60) return `${t('remaining')} ${min} ${t('minShort')}`;
    return `${t('remaining')} ${Math.round(min / 60 * 10) / 10} ${t('hrShort')}`;
  };
  const rem = remainingLabel();

  // Tooltip for the whole trigger — explains the connection health when
  // it's not OPEN, so users understand why we grey out / pulse.
  const triggerTitle = isOffline
    ? t('wsOfflineTip')
    : isConnecting
    ? t('wsConnectingTip')
    : undefined;

  return (
    <div className="relative" ref={ref} data-testid="status-picker">
      <button
        onClick={() => setOpen(o => !o)}
        title={triggerTitle}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[#F3F4F1] transition-colors"
        data-testid="status-picker-trigger"
        data-conn-state={connState}
      >
        <span className="relative inline-block w-2.5 h-2.5 flex-shrink-0">
          <StatusDot status={myStatus} size="md" absolute={false} border={false} />
          {/* Pulsing ring overlay when WS is reconnecting */}
          {isConnecting && (
            <span
              className="absolute -inset-1 rounded-full ring-2 ring-[#D4A373]/60 animate-ping"
              style={{ animationDuration: '1.4s' }}
              aria-hidden
            />
          )}
        </span>
        <span className={`text-xs font-medium flex-1 text-left truncate ${isOffline ? 'text-[#9CA3AF] italic' : 'text-[#1C1F1D]'}`}>
          {statusLabel}
          {rem ? ` · ${rem}` : ''}
          {isConnecting && <span className="text-[#D4A373] ml-1">· {t('wsConnecting')}</span>}
          {isOffline && <span className="text-[#C87967] ml-1">· {t('wsOffline')}</span>}
        </span>
        {isOffline
          ? <WifiOff className="w-3.5 h-3.5 text-[#C87967] flex-shrink-0" aria-hidden />
          : isConnecting
          ? <Loader2 className="w-3.5 h-3.5 text-[#D4A373] flex-shrink-0 animate-spin" aria-hidden />
          : <Wifi className="w-3 h-3 text-[#9CA3AF] flex-shrink-0 opacity-50" aria-hidden />}
        <ChevronDown className={`w-3.5 h-3.5 text-[#9CA3AF] transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute bottom-full left-0 right-0 mb-2 bg-white border border-[#E2E4E0] rounded-lg shadow-lg py-1 z-50"
          data-testid="status-picker-menu">
          {Object.keys(STATUS_CFG).map((key) => (
            <button key={key} onClick={() => { setStatus(key); setOpen(false); }}
              className={`w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-[#F3F4F1] ${myStatus === key ? 'bg-[#F9F9F8]' : ''}`}
              data-testid={`status-option-${key}`}>
              <span className="relative inline-block w-2.5 h-2.5 flex-shrink-0">
                <StatusDot status={key} size="md" absolute={false} border={false} />
              </span>
              <span className="flex-1 text-left text-[#1C1F1D]">{t(STATUS_KEY_MAP[key])}</span>
              {myStatus === key && <span className="text-[#4A5D4E] text-[10px]">●</span>}
            </button>
          ))}
          <div className="border-t border-[#E2E4E0] mt-1 pt-1 px-2">
            <p className="text-[9px] font-bold text-[#6B7280] uppercase tracking-wider px-1 py-1 flex items-center gap-1">
              <Clock className="w-3 h-3" /> {t('dndForDots')}
            </p>
            <div className="grid grid-cols-3 gap-1 pb-1">
              <button onClick={() => applyDndFor(30)} className="text-[10px] px-2 py-1 rounded bg-[#C87967]/10 hover:bg-[#C87967]/20 text-[#C87967] font-medium" data-testid="dnd-30min">30 {t('minShort')}</button>
              <button onClick={() => applyDndFor(60)} className="text-[10px] px-2 py-1 rounded bg-[#C87967]/10 hover:bg-[#C87967]/20 text-[#C87967] font-medium" data-testid="dnd-1h">1 {t('hrShort')}</button>
              <button onClick={() => applyDndFor(120)} className="text-[10px] px-2 py-1 rounded bg-[#C87967]/10 hover:bg-[#C87967]/20 text-[#C87967] font-medium" data-testid="dnd-2h">2 {t('hrShort')}</button>
            </div>
            <div className="flex items-center gap-1 pb-1">
              <span className="text-[10px] text-[#6B7280]">{t('until')}</span>
              <input type="time" value={customTime} onChange={e => setCustomTime(e.target.value)}
                className="flex-1 text-[10px] h-6 px-1.5 border border-[#E2E4E0] rounded focus:outline-none focus:border-[#4A5D4E]"
                data-testid="dnd-custom-time" />
              <button onClick={applyDndUntilCustom} disabled={!customTime}
                className="text-[10px] px-2 py-1 rounded bg-[#4A5D4E] hover:bg-[#3E4E42] text-white font-medium disabled:opacity-50"
                data-testid="dnd-apply-custom">{t('apply')}</button>
            </div>
          </div>
          <div className="px-3 py-1.5 border-t border-[#E2E4E0]">
            <p className="text-[9px] text-[#9CA3AF] leading-tight">{t('idleAutoAwayHint')}</p>
          </div>
        </div>
      )}
    </div>
  );
}
