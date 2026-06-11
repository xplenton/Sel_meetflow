import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useLanguage } from '../contexts/LanguageContext';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs';
import { Flag, Bell, Trash2, CheckCircle2, XCircle, Eye, AlertTriangle, Send, BarChart3, Users, MessageCircle, ThumbsUp, TrendingUp, HelpCircle, ClipboardList, Download } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'sonner';

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const REPORT_STATUS_CFG = {
  pending: { label: 'Offen', color: '#D4A373', bg: 'bg-[#D4A373]/10' },
  reviewed: { label: 'Bearbeitet', color: '#6B8E23', bg: 'bg-[#6B8E23]/10' },
  dismissed: { label: 'Verworfen', color: '#9CA3AF', bg: 'bg-[#9CA3AF]/10' },
};

const CONTENT_TYPE_LABEL = {
  post: 'Beitrag',
  comment: 'Kommentar',
  question: 'Frage',
};

export default function NewsModerationPanel() {
  const { t } = useLanguage();
  return (
    <Tabs defaultValue="stats">
      <TabsList className="bg-[#F3F4F1] mb-5 rounded-lg">
        <TabsTrigger value="stats" data-testid="moderation-tab-stats" className="rounded-lg text-xs">
          <BarChart3 className="w-3.5 h-3.5 mr-1.5" /> Interaktions-Dashboard
        </TabsTrigger>
        <TabsTrigger value="reports" data-testid="moderation-tab-reports" className="rounded-lg text-xs">
          <Flag className="w-3.5 h-3.5 mr-1.5" /> Meldungen
        </TabsTrigger>
        <TabsTrigger value="push" data-testid="moderation-tab-push" className="rounded-lg text-xs">
          <Bell className="w-3.5 h-3.5 mr-1.5" /> Push-Versand-Log
        </TabsTrigger>
      </TabsList>
      <TabsContent value="stats"><StatsPanel /></TabsContent>
      <TabsContent value="reports"><ReportsPanel /></TabsContent>
      <TabsContent value="push"><PushLogPanel /></TabsContent>
    </Tabs>
  );
}

function StatCard({ icon: Icon, label, value, sub, color = '#4A5D4E', testId }) {
  return (
    <div className="bg-white border border-[#E2E4E0] rounded-xl p-4" data-testid={testId}>
      <div className="flex items-center justify-between mb-2">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${color}15` }}>
          <Icon className="w-4.5 h-4.5" style={{ color }} />
        </div>
      </div>
      <p className="text-2xl font-medium text-[#1C1F1D]" style={{ fontFamily: 'Manrope' }}>{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-[#6B7280] font-bold mt-0.5">{label}</p>
      {sub && <p className="text-[11px] text-[#9CA3AF] mt-1">{sub}</p>}
    </div>
  );
}

function StatsPanel() {
  const { t } = useLanguage();
  // Auto-refresh interaction stats every 30 s so "live" dashboards feel
  // alive without needing manual refresh (iter 118).
  const statsQ = useQuery({
    queryKey: ['news', 'interaction-stats'],
    queryFn: async () => (await api.get('/news/interaction-stats')).data,
    refetchInterval: 30_000,
  });
  const stats = statsQ.data;
  const loading = statsQ.isLoading;

  if (loading) return <div className="text-center py-12 text-[#9CA3AF] text-sm">{t('loading')}</div>;
  if (!stats) return <div className="text-center py-12 text-[#9CA3AF] text-sm">{t('noData')}</div>;

  const commentRate = stats.total_active_users ? Math.round((stats.comments.total / stats.total_active_users) * 100) / 100 : 0;

  return (
    <div className="space-y-5" data-testid="interaction-stats-panel">
      {/* Export buttons */}
      <div className="flex items-center justify-end gap-2">
        <a href={`${process.env.REACT_APP_BACKEND_URL}/api/exports/interactions/csv`}
          target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-[#4A5D4E] hover:text-[#3E4E42] border border-[#E2E4E0] rounded-lg px-3 py-1.5 hover:bg-[#F3F4F1]"
          data-testid="export-interactions-csv">
          <Download className="w-3.5 h-3.5" /> CSV
        </a>
        <a href={`${process.env.REACT_APP_BACKEND_URL}/api/exports/interactions/pdf`}
          target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-white bg-[#4A5D4E] hover:bg-[#3E4E42] rounded-lg px-3 py-1.5"
          data-testid="export-interactions-pdf">
          <Download className="w-3.5 h-3.5" /> PDF-Report
        </a>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard icon={TrendingUp} label="Aktive Nutzer" value={stats.total_active_users}
          sub="im System" color="#4A5D4E" testId="stat-active-users" />
        <StatCard icon={MessageCircle} label="Kommentare" value={stats.comments.total}
          sub={`⌀ ${commentRate} pro Nutzer`} color="#6B8E23" testId="stat-comments" />
        <StatCard icon={ThumbsUp} label="Reaktionen" value={stats.reactions.total}
          sub={`${stats.reactions.rate}% Beteiligung`} color="#D4A373" testId="stat-reactions" />
        <StatCard icon={Flag} label={t('openReports')} value={stats.reports.open}
          sub={`${stats.reports.total} gesamt`} color="#C87967" testId="stat-reports" />
        <StatCard icon={HelpCircle} label="Q&A" value={`${stats.questions.answered}/${stats.questions.total}`}
          sub={`${stats.questions.answer_rate}% beantwortet`} color="#4A5D4E" testId="stat-qa" />
        <StatCard icon={ClipboardList} label="Umfragen" value={stats.surveys.published}
          sub={`${stats.surveys.total_responses} Antworten`} color="#D4A373" testId="stat-surveys" />
        <StatCard icon={Users} label={t('uniqueReactors')} value={stats.reactions.unique_users}
          sub={`${stats.reactions.rate}% aller Nutzer`} color="#6B8E23" testId="stat-reactors" />
        <StatCard icon={AlertTriangle} label={t('mandatoryNews')} value={stats.mandatory?.length || 0}
          sub="Posts mit Pflichtlese" color="#C87967" testId="stat-mandatory" />
      </div>

      {/* Mandatory reads */}
      {stats.mandatory?.length > 0 && (
        <div className="bg-white border border-[#E2E4E0] rounded-xl p-4">
          <h4 className="text-xs font-bold uppercase tracking-wider text-[#6B7280] mb-3">Pflicht-Lesebestätigungsraten</h4>
          <div className="space-y-2">
            {stats.mandatory.slice(0, 10).map((m, i) => (
              <div key={i} className="flex items-center gap-3" data-testid={`mandatory-row-${i}`}>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-[#1C1F1D] truncate">{m.title}</p>
                </div>
                <div className="w-40 h-2 bg-[#F3F4F1] rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all" style={{ width: `${m.rate}%`, backgroundColor: m.rate >= 80 ? '#6B8E23' : m.rate >= 50 ? '#D4A373' : '#C87967' }} />
                </div>
                <span className="text-xs font-medium text-[#4A5D4E] w-16 text-right">{m.rate}%</span>
                <span className="text-[10px] text-[#9CA3AF] w-20 text-right">{m.read_count}/{m.total_users}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top engaged + popular tags */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {stats.top_posts?.length > 0 && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-4" data-testid="top-posts">
            <h4 className="text-xs font-bold uppercase tracking-wider text-[#6B7280] mb-3">Top Engagement</h4>
            <div className="space-y-2">
              {stats.top_posts.map((p, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-[10px] w-5 text-center font-bold text-[#4A5D4E]">#{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-[#1C1F1D] truncate">{p.title}</p>
                    <p className="text-[10px] text-[#9CA3AF]">{p.comment_count} Kommentare · {p.reaction_count} Reaktionen</p>
                  </div>
                  <span className="text-xs font-medium text-[#4A5D4E]">{p.engagement}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {stats.popular_tags?.length > 0 && (
          <div className="bg-white border border-[#E2E4E0] rounded-xl p-4" data-testid="popular-tags">
            <h4 className="text-xs font-bold uppercase tracking-wider text-[#6B7280] mb-3">Beliebte Tags</h4>
            <div className="flex flex-wrap gap-1.5">
              {stats.popular_tags.map((t, i) => (
                <span key={i} className="text-xs px-2 py-1 rounded-full bg-[#4A5D4E]/10 text-[#4A5D4E]">
                  #{t.tag} <span className="text-[#9CA3AF]">{t.count}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ReportsPanel() {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [filter, setFilter] = useState('all');
  const [busyId, setBusyId] = useState(null);

  const reportsQ = useQuery({
    queryKey: ['news', 'reports'],
    queryFn: async () => (await api.get('/news/reports')).data || [],
  });
  const reports = reportsQ.data || [];
  const loading = reportsQ.isLoading;

  const actionMutation = useMutation({
    mutationFn: ({ report_id, status, action }) => api.put(`/news/reports/${report_id}`, { status, action }),
    onMutate: ({ report_id }) => setBusyId(report_id),
    onSettled: () => setBusyId(null),
    onSuccess: (_r, { action }) => {
      toast.success(action === 'delete_content' ? 'Inhalt gelöscht' : action === 'dismiss' ? 'Meldung verworfen' : 'Meldung bearbeitet');
      qc.invalidateQueries({ queryKey: ['news', 'reports'] });
      qc.invalidateQueries({ queryKey: ['news', 'interaction-stats'] });
    },
    onError: (err) => toast.error(err.response?.data?.detail || t('error')),
  });

  const handleAction = (r, action) => actionMutation.mutate({
    report_id: r.report_id,
    status: action === 'dismiss' ? 'dismissed' : 'reviewed',
    action,
  });

  const filtered = reports.filter(r => filter === 'all' || r.status === filter);
  const counts = {
    all: reports.length,
    pending: reports.filter(r => r.status === 'pending').length,
    reviewed: reports.filter(r => r.status === 'reviewed').length,
    dismissed: reports.filter(r => r.status === 'dismissed').length,
  };

  return (
    <div data-testid="reports-panel">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          {[
            { k: 'all', label: 'Alle' },
            { k: 'pending', label: 'Offen' },
            { k: 'reviewed', label: 'Bearbeitet' },
            { k: 'dismissed', label: 'Verworfen' },
          ].map(f => (
            <button key={f.k} onClick={() => setFilter(f.k)} data-testid={`reports-filter-${f.k}`}
              className={`px-3 py-1 rounded-full text-xs transition-colors ${filter === f.k ? 'bg-[#4A5D4E] text-white' : 'bg-[#F3F4F1] text-[#6B7280] hover:bg-[#E2E4E0]'}`}>
              {f.label} <span className="opacity-70 ml-1">({counts[f.k]})</span>
            </button>
          ))}
        </div>
        <Button variant="outline" size="sm" onClick={() => reportsQ.refetch()} className="rounded-full text-xs h-8 border-[#E2E4E0]">
          {t('refresh')}
        </Button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-[#9CA3AF] text-sm">{t('loading')}</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 bg-white border border-[#E2E4E0] rounded-xl">
          <Flag className="w-10 h-10 text-[#E2E4E0] mx-auto mb-3" />
          <p className="text-sm text-[#9CA3AF]">Keine Meldungen in dieser Kategorie</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(r => {
            const cfg = REPORT_STATUS_CFG[r.status] || REPORT_STATUS_CFG.pending;
            return (
              <div key={r.report_id} className="bg-white border border-[#E2E4E0] rounded-xl p-4" data-testid={`report-${r.report_id}`}>
                <div className="flex items-start gap-3">
                  <div className={`w-8 h-8 rounded-lg ${cfg.bg} flex items-center justify-center flex-shrink-0`}>
                    <AlertTriangle className="w-4 h-4" style={{ color: cfg.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge className="text-[10px] border-0" style={{ backgroundColor: `${cfg.color}20`, color: cfg.color }}>
                        {cfg.label}
                      </Badge>
                      <Badge className="text-[10px] bg-[#F3F4F1] text-[#6B7280] border-0">
                        {CONTENT_TYPE_LABEL[r.content_type] || r.content_type}
                      </Badge>
                      <span className="text-[10px] text-[#9CA3AF]">von {r.reporter_name || 'Unbekannt'}</span>
                      <span className="text-[10px] text-[#9CA3AF] ml-auto">{formatDate(r.created_at)}</span>
                    </div>
                    <p className="text-sm text-[#1C1F1D] mt-1.5 break-words">
                      {r.reason || <span className="italic text-[#9CA3AF]">{t('noReasonGiven')}</span>}
                    </p>
                    <p className="text-[10px] text-[#9CA3AF] mt-1">ID: {r.content_id}</p>
                    {r.reviewed_by && (
                      <p className="text-[10px] text-[#6B8E23] mt-1">
                        ✓ Bearbeitet von {r.reviewed_by}
                        {r.action ? ` (${r.action === 'delete_content' ? 'Inhalt gelöscht' : r.action})` : ''}
                        {r.reviewed_at ? ` · ${formatDate(r.reviewed_at)}` : ''}
                      </p>
                    )}
                  </div>
                </div>
                {r.status === 'pending' && (
                  <div className="flex gap-2 mt-3 justify-end flex-wrap">
                    {r.content_type !== 'post' && (
                      <Button size="sm" variant="outline" disabled={busyId === r.report_id}
                        onClick={() => handleAction(r, 'delete_content')}
                        className="rounded-full text-xs h-7 border-[#C87967] text-[#C87967] hover:bg-[#C87967]/10"
                        data-testid={`action-delete-${r.report_id}`}>
                        <Trash2 className="w-3 h-3 mr-1" /> {t('deleteContent')}
                      </Button>
                    )}
                    <Button size="sm" variant="outline" disabled={busyId === r.report_id}
                      onClick={() => handleAction(r, 'reviewed')}
                      className="rounded-full text-xs h-7 border-[#E2E4E0]"
                      data-testid={`action-review-${r.report_id}`}>
                      <CheckCircle2 className="w-3 h-3 mr-1" /> Als bearbeitet markieren
                    </Button>
                    <Button size="sm" variant="ghost" disabled={busyId === r.report_id}
                      onClick={() => handleAction(r, 'dismiss')}
                      className="rounded-full text-xs h-7 text-[#9CA3AF]"
                      data-testid={`action-dismiss-${r.report_id}`}>
                      <XCircle className="w-3 h-3 mr-1" /> Verwerfen
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function PushLogPanel() {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [sending, setSending] = useState('');

  const notifsQ = useQuery({
    queryKey: ['news', 'push', 'notifications'],
    queryFn: async () => (await api.get('/news/push/notifications')).data || [],
  });
  const postsQ = useQuery({
    queryKey: ['news', 'feed', 'moderation'],
    queryFn: async () => {
      const { data } = await api.get('/news/feed?limit=30');
      return (data && data.posts) || [];
    },
  });
  const notifs = notifsQ.data || [];
  const posts = postsQ.data || [];
  const loading = notifsQ.isLoading || postsQ.isLoading;

  const resendMutation = useMutation({
    mutationFn: (post_id) => api.post('/news/push/send', { post_id }),
    onMutate: (post_id) => setSending(post_id),
    onSettled: () => setSending(''),
    onSuccess: ({ data }) => {
      toast.success(`Push gesendet: ${data.sent || 0}/${data.target || 0} Empfänger`);
      qc.invalidateQueries({ queryKey: ['news', 'push', 'notifications'] });
    },
    onError: (err) => toast.error(err.response?.data?.detail || t('error')),
  });

  const resendPush = (postId) => resendMutation.mutate(postId);

  return (
    <div data-testid="push-log-panel">
      <div className="bg-white border border-[#E2E4E0] rounded-xl p-4 mb-4">
        <h4 className="text-xs font-bold uppercase tracking-wider text-[#6B7280] mb-3">
          {t('resendPushForPost')}
        </h4>
        {posts.length === 0 ? (
          <p className="text-xs text-[#9CA3AF]">{t('noPostsFound')}</p>
        ) : (
          <div className="flex flex-wrap gap-2 max-h-48 overflow-y-auto">
            {posts.slice(0, 20).map(p => (
              <Button key={p.post_id} size="sm" variant="outline" disabled={sending === p.post_id}
                onClick={() => resendPush(p.post_id)}
                className="rounded-full text-xs h-7 border-[#E2E4E0] max-w-[260px] truncate"
                data-testid={`resend-push-${p.post_id}`} title={p.title}>
                <Send className="w-3 h-3 mr-1 flex-shrink-0" />
                <span className="truncate">{p.title}</span>
              </Button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-center py-12 text-[#9CA3AF] text-sm">{t('loading')}</div>
      ) : notifs.length === 0 ? (
        <div className="text-center py-16 bg-white border border-[#E2E4E0] rounded-xl">
          <Bell className="w-10 h-10 text-[#E2E4E0] mx-auto mb-3" />
          <p className="text-sm text-[#9CA3AF]">{t('noPushSentYet')}</p>
        </div>
      ) : (
        <div className="bg-white border border-[#E2E4E0] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[#F3F4F1]">
              <tr>
                <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Titel</th>
                <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">{t('priority')}</th>
                <th className="text-right px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Ziel</th>
                <th className="text-right px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Gesendet</th>
                <th className="text-right px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Fehler</th>
                <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Von</th>
                <th className="text-left px-4 py-2 text-[10px] uppercase tracking-wider text-[#6B7280] font-bold">Zeitpunkt</th>
              </tr>
            </thead>
            <tbody>
              {notifs.map((n, i) => (
                <tr key={n.notification_id} className={i % 2 ? 'bg-[#F9F9F8]' : 'bg-white'} data-testid={`push-row-${n.notification_id}`}>
                  <td className="px-4 py-2 text-xs text-[#1C1F1D] max-w-[260px] truncate" title={n.title}>{n.title}</td>
                  <td className="px-4 py-2">
                    <Badge className="text-[10px] border-0" style={{
                      backgroundColor: n.priority === 'critical' ? '#C8796720' : n.priority === 'important' ? '#D4A37320' : '#9CA3AF20',
                      color: n.priority === 'critical' ? '#C87967' : n.priority === 'important' ? '#D4A373' : '#6B7280',
                    }}>
                      {n.priority === 'critical' ? 'Kritisch' : n.priority === 'important' ? 'Wichtig' : 'Normal'}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-xs text-right text-[#6B7280]">{n.target_count ?? n.sent_to ?? 0}</td>
                  <td className="px-4 py-2 text-xs text-right font-medium text-[#6B8E23]">{n.sent ?? '-'}</td>
                  <td className="px-4 py-2 text-xs text-right text-[#C87967]">{(n.errors || 0) + (n.expired || 0)}</td>
                  <td className="px-4 py-2 text-xs text-[#6B7280]">{n.sent_by || 'System'}</td>
                  <td className="px-4 py-2 text-xs text-[#9CA3AF]">{formatDate(n.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
