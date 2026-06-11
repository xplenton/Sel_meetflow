import { useEffect, useState } from 'react';
import api from '../lib/api';
import { Stethoscope, CheckCircle, AlertTriangle, RefreshCw, Clock, Users, ChevronDown, ChevronRight } from 'lucide-react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';

import { useLanguage } from '../contexts/LanguageContext';
function ResultBadge({ state }) {
  if (state === 'ok') return <Badge className="text-[10px] bg-[#6B8E23]/15 text-[#6B8E23] hover:bg-[#6B8E23]/15"><CheckCircle className="w-3 h-3 mr-1" />ok</Badge>;
  if (state === 'fail') return <Badge className="text-[10px] bg-[#C87967]/15 text-[#C87967] hover:bg-[#C87967]/15"><AlertTriangle className="w-3 h-3 mr-1" />fail</Badge>;
  if (state === 'warn') return <Badge className="text-[10px] bg-[#D4A373]/15 text-[#D4A373] hover:bg-[#D4A373]/15">warn</Badge>;
  return <Badge className="text-[10px] bg-[#E8EAE6] text-[#6B7280]">{state || '—'}</Badge>;
}

function formatDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
}

function isExpired(iso) {
  if (!iso) return false;
  try { return new Date(iso) < new Date(); } catch { return false; }
}

export default function QuickScansPanel() {
  const { t } = useLanguage();
  const [data, setData] = useState({ tokens: [], stats: { total: 0, submitted: 0, pending: 0, with_failures: 0 } });
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/quick-scans');
      setData(res.data || { tokens: [], stats: {} });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = (token) => setExpanded(prev => ({ ...prev, [token]: !prev[token] }));

  const statCards = [
    { label: 'Gesamt', value: data.stats?.total ?? 0, color: 'text-[#4A5D4E]' },
    { label: 'Eingereicht', value: data.stats?.submitted ?? 0, color: 'text-[#6B8E23]' },
    { label: 'Ausstehend', value: data.stats?.pending ?? 0, color: 'text-[#D4A373]' },
    { label: 'Mit Fehlern', value: data.stats?.with_failures ?? 0, color: 'text-[#C87967]' },
  ];

  return (
    <div className="space-y-5" data-testid="quick-scans-panel">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-[#1C1F1D] flex items-center gap-2">
            <Stethoscope className="w-4 h-4 text-[#4A5D4E]" />
            Quick-Scans
          </h3>
          <p className="text-xs text-[#6B7280] mt-0.5">{t('quickScanDescription')}</p>
        </div>
        <Button onClick={load} variant="outline" size="sm" className="gap-1.5" data-testid="quick-scans-refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Aktualisieren
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {statCards.map((s, i) => (
          <div key={i} className="bg-white border border-[#E2E4E0] rounded-xl p-4" data-testid={`quick-scans-stat-${i}`}>
            <div className="text-[10px] uppercase tracking-wider font-bold text-[#6B7280]">{s.label}</div>
            <div className={`text-2xl font-light mt-1 ${s.color}`} style={{ fontFamily: 'Manrope' }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Token list */}
      {loading && data.tokens.length === 0 && (
        <div className="text-sm text-[#9CA3AF] py-8 text-center">Lade Quick-Scans …</div>
      )}

      {!loading && data.tokens.length === 0 && (
        <div className="bg-[#F8F9F7] border border-dashed border-[#E2E4E0] rounded-xl p-10 text-center">
          <Stethoscope className="w-8 h-8 text-[#9CA3AF] mx-auto mb-2" />
          <p className="text-sm text-[#6B7280]">{t('noQuickScansYet')}</p>
          <p className="text-xs text-[#9CA3AF] mt-1">{t('quickScanHostHint')}</p>
        </div>
      )}

      <div className="space-y-2">
        {data.tokens.map(tok => {
          const submissions = tok.submissions || [];
          const expired = isExpired(tok.expires_at);
          const hasFail = submissions.some(s => Object.values(s.results || {}).some(v => v?.state === 'fail'));
          const statusBadge = submissions.length > 0
            ? (hasFail
                ? <Badge className="text-[10px] bg-[#C87967]/15 text-[#C87967] hover:bg-[#C87967]/15">{t('errorsDetected')}</Badge>
                : <Badge className="text-[10px] bg-[#6B8E23]/15 text-[#6B8E23] hover:bg-[#6B8E23]/15">{t('allGreen')}</Badge>)
            : (expired
                ? <Badge className="text-[10px] bg-[#9CA3AF]/15 text-[#6B7280]">abgelaufen</Badge>
                : <Badge className="text-[10px] bg-[#D4A373]/15 text-[#D4A373] hover:bg-[#D4A373]/15">wartet</Badge>);

          const isOpen = !!expanded[tok.token];

          return (
            <div
              key={tok.token}
              className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden"
              data-testid={`quick-scan-row-${tok.token}`}
            >
              <button
                onClick={() => toggle(tok.token)}
                className="w-full flex items-center gap-3 p-4 hover:bg-[#F8F9F7] transition text-left"
                data-testid={`quick-scan-row-toggle-${tok.token}`}
              >
                {isOpen ? <ChevronDown className="w-4 h-4 text-[#9CA3AF] flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-[#9CA3AF] flex-shrink-0" />}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-[#1C1F1D] truncate">
                      {tok.meeting_title || tok.meeting_id || 'Kein Meeting-Titel'}
                    </span>
                    {statusBadge}
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-[11px] text-[#6B7280]">
                    <span className="flex items-center gap-1"><Users className="w-3 h-3" />{tok.created_by_name || '—'} → {tok.target_user_name || tok.target_user_id || '—'}</span>
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{formatDate(tok.created_at)}</span>
                  </div>
                </div>
                <Badge className="text-[10px] bg-[#F3F4F1] text-[#6B7280] flex-shrink-0">{submissions.length} Submissions</Badge>
              </button>

              {isOpen && (
                <div className="border-t border-[#E2E4E0] bg-[#FAFBF9] p-4 space-y-3">
                  {submissions.length === 0 && (
                    <div className="text-xs text-[#9CA3AF] italic">Noch keine Einreichung. Gültig bis {formatDate(tok.expires_at)}.</div>
                  )}
                  {submissions.map((s, idx) => {
                    const keys = ['cam', 'mic', 'screen', 'webrtc', 'push', 'secureCtx', 'vapid'];
                    return (
                      <div key={idx} className="bg-white rounded-lg p-3 border border-[#E8EAE6]" data-testid={`quick-scan-submission-${tok.token}-${idx}`}>
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <span className="text-xs font-medium text-[#1C1F1D]">{s.reporter_name || 'Anonym'}</span>
                          <span className="text-[10px] text-[#9CA3AF]">{formatDate(s.submitted_at)}</span>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                          {keys.map(k => {
                            const v = s.results?.[k];
                            if (!v) return null;
                            return (
                              <div key={k} className="flex items-center justify-between gap-2 px-2 py-1 rounded bg-[#F8F9F7]">
                                <span className="text-[11px] text-[#6B7280] capitalize">{k}</span>
                                <ResultBadge state={v.state} />
                              </div>
                            );
                          })}
                        </div>
                        {s.user_agent && (
                          <div className="text-[10px] text-[#9CA3AF] mt-2 truncate" title={s.user_agent}>UA: {s.user_agent}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
