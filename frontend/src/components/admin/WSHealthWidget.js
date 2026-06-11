import { useEffect, useState, useCallback } from 'react';
import { Radio, RefreshCw, AlertTriangle, CheckCircle2, ShieldAlert, User, Clock } from 'lucide-react';
import api from '../../lib/api';

/**
 * WebSocket-Auth Health Widget. Polls /api/admin/health/ws every 30 s and
 * surfaces the rolling 5-minute accept/reject ratio so operators spot
 * regressions like the iter-106 cookie-on-upgrade issue.
 */
const STATUS_CFG = {
  ok:   { label: 'Gesund',  color: 'bg-[#6B8E23]/10 text-[#6B8E23] border-[#6B8E23]/20', Icon: CheckCircle2 },
  warn: { label: 'Warnung', color: 'bg-[#D4A373]/10 text-[#D4A373] border-[#D4A373]/30', Icon: AlertTriangle },
  fail: { label: 'Kritisch', color: 'bg-[#C87967]/10 text-[#C87967] border-[#C87967]/30', Icon: ShieldAlert },
  idle: { label: 'Keine Aktivität', color: 'bg-[#F3F4F1] text-[#6B7280] border-[#E2E4E0]', Icon: Radio },
};

const EVENT_LABEL = {
  accept: 'Erfolgreich',
  reject_no_token: 'Kein Token',
  reject_invalid: 'Token ungültig',
  reject_spoof: 'Impersonation',
  reject_stale_tv: 'Alte Session',
  reject_user_missing: 'User gelöscht',
};

function formatAgo(ts) {
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${Math.floor(sec / 3600)}h`;
}

export default function WSHealthWidget() {
  const [data, setData] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchWs = useCallback(async () => {
    setRefreshing(true);
    try {
      const { data } = await api.get('/admin/health/ws');
      setData(data);
    } catch { /* noop */ }
    finally { setRefreshing(false); }
  }, []);

  useEffect(() => {
    fetchWs();
    const id = setInterval(fetchWs, 30000);
    return () => clearInterval(id);
  }, [fetchWs]);

  if (!data) {
    return (
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-4" data-testid="ws-health-widget">
        <div className="text-xs text-[#9CA3AF]">Lade WebSocket-Metriken…</div>
      </div>
    );
  }

  const cfg = STATUS_CFG[data.status] || STATUS_CFG.idle;
  const StatusIcon = cfg.Icon;
  const rejectRatePct = Math.round((data.last_5min.reject_rate || 0) * 100);
  const byEvent = data.last_5min.by_event || {};

  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden" data-testid="ws-health-widget">
      <div className={`border-b px-4 py-3 flex items-center justify-between ${cfg.color}`}>
        <div className="flex items-center gap-2 min-w-0">
          <Radio className="w-4 h-4 flex-shrink-0" />
          <span className="text-[11px] font-bold uppercase tracking-[0.15em]">WebSocket-Auth</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold">
            <StatusIcon className="w-3.5 h-3.5" /> {cfg.label}
          </span>
          <button
            onClick={fetchWs}
            className="p-1 rounded hover:bg-black/5 transition-colors"
            title="Aktualisieren"
            data-testid="ws-health-refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-[#9CA3AF]">5-Min Total</div>
          <div className="text-2xl font-light mt-1 text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>
            {data.last_5min.total}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-[#6B8E23]">Accepts</div>
          <div className="text-2xl font-light mt-1 text-[#6B8E23]" style={{ fontFamily: 'Manrope' }}>
            {data.last_5min.accepts}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-[#C87967]">Rejects</div>
          <div className="text-2xl font-light mt-1 text-[#C87967]" style={{ fontFamily: 'Manrope' }}>
            {data.last_5min.rejects}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-[#9CA3AF]">Reject-Rate</div>
          <div className={`text-2xl font-light mt-1 ${rejectRatePct >= 50 ? 'text-[#C87967]' : rejectRatePct >= 20 ? 'text-[#D4A373]' : 'text-[#1C1F1D]'}`} style={{ fontFamily: 'Manrope' }}>
            {rejectRatePct}%
          </div>
        </div>
      </div>

      {/* Breakdown */}
      {Object.keys(byEvent).length > 0 && (
        <div className="border-t border-[#E2E4E0] px-4 py-2 flex flex-wrap gap-1.5" data-testid="ws-health-breakdown">
          {Object.entries(byEvent).map(([key, count]) => {
            const bad = key !== 'accept';
            return (
              <span
                key={key}
                className={`text-[10px] px-2 py-0.5 rounded-full ${bad ? 'bg-[#C87967]/15 text-[#C87967]' : 'bg-[#6B8E23]/15 text-[#6B8E23]'}`}
              >
                {EVENT_LABEL[key] || key}: {count}
              </span>
            );
          })}
        </div>
      )}

      {/* Recent events */}
      {data.recent?.length > 0 && (
        <div className="border-t border-[#E2E4E0] max-h-52 overflow-y-auto scrollbar-thin">
          <div className="px-4 py-2 text-[10px] uppercase tracking-[0.15em] font-bold text-[#9CA3AF] sticky top-0 bg-white/95 backdrop-blur">
            Letzte Ereignisse
          </div>
          <div className="divide-y divide-[#F3F4F1]">
            {data.recent.slice(0, 15).map((e, i) => {
              const bad = e.event !== 'accept';
              return (
                <div
                  key={i}
                  className="flex items-center gap-2 px-4 py-1.5 text-xs"
                  data-testid={`ws-health-event-${i}`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${bad ? 'bg-[#C87967]' : 'bg-[#6B8E23]'}`} />
                  <span className={`text-[11px] font-medium w-28 truncate ${bad ? 'text-[#C87967]' : 'text-[#6B8E23]'}`}>
                    {EVENT_LABEL[e.event] || e.event}
                  </span>
                  <User className="w-3 h-3 text-[#9CA3AF] flex-shrink-0" />
                  <span className="text-[10px] text-[#6B7280] font-mono truncate flex-1">{e.user_id || '—'}</span>
                  <Clock className="w-3 h-3 text-[#9CA3AF] flex-shrink-0" />
                  <span className="text-[10px] text-[#9CA3AF] tabular-nums w-10 text-right">{formatAgo(e.ts)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Help note */}
      <div className="border-t border-[#E2E4E0] px-4 py-2 bg-[#FAFBF9] text-[10px] text-[#9CA3AF]">
        Warnung bei &ge;20% Reject-Rate, Kritisch ab 50%. Hilft beim frühzeitigen Erkennen von Cookie/Token-Regressionen (z.B. Safari-WSS-Upgrade-Bug).
      </div>
    </div>
  );
}
